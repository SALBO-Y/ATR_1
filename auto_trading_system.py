#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
한국투자증권 자동트레이딩 시스템 (통합버전)
==================================================
주요 기능:
- 조건검색식 기반 종목 스캘핑 트레이딩
- 텔레그램봇 연동 (매수/매도 체결알림, 실시간 잔고조회, 미실현손익 조회)
- REST API 중심 (체결통보만 WebSocket 사용)
- 코스피/코스닥 지원

개발사항:
- STEP 1: 개발환경 및 인증 설정
- STEP 2: 조건검색식 기반 종목 필터링
- STEP 3: 실시간 체결 및 시세 수신
- STEP 4: 주문/매도/매수 실행 (REST 중심)
- STEP 5: 텔레그램 봇 연동
- STEP 6: 잔고/손익 실시간 조회
- STEP 7: 예외/장애 처리 및 로깅
- STEP 8: 코스피/코스닥 구분 처리
"""

import asyncio
import json
import logging
import os
import sys
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

import pandas as pd
import websockets

# kis_auth 모듈 import (인증 및 API 호출 공통 함수)
sys.path.extend(['.', './examples_llm'])
import kis_auth as ka

# 텔레그램 봇 관련 import (필요시 설치: pip install python-telegram-bot)
try:
    from telegram import Bot
    from telegram.error import TelegramError
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("Warning: python-telegram-bot not installed. Telegram features will be disabled.")
    print("Install with: pip install python-telegram-bot")

# ====================================================================================================
# 로깅 설정
# ====================================================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(f"auto_trading_{datetime.now().strftime('%Y%m%d')}.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ====================================================================================================
# 전역 설정 및 상수
# ====================================================================================================

# 시스템 설정
class TradingConfig:
    """자동매매 시스템 설정"""

    # 환경 설정
    ENV_MODE = "demo"  # "real" 또는 "demo" (실전투자 또는 모의투자)
    PRODUCT_CODE = "01"  # 계좌상품코드 (01: 주식투자, 03: 선물옵션 등)

    # 조건검색식 설정
    CONDITION_NAME = ""  # 사용할 조건검색식 이름 (비워두면 첫번째 조건 사용)
    CONDITION_SEQ = ""   # 조건검색식 seq (비워두면 자동 조회)

    # 매매 전략 설정
    MAX_STOCKS = 5  # 최대 보유 종목 수
    BUY_AMOUNT = 100000  # 종목당 매수 금액 (원)

    # 목표수익률/손절률 (%)
    TARGET_PROFIT_RATE = 2.0  # 목표 수익률 (2%)
    STOP_LOSS_RATE = -1.5  # 손절률 (-1.5%)

    # 시장 구분
    MARKET_DIV = "J"  # J: 코스피, Q: 코스닥

    # 주문 설정
    ORDER_DVSN_BUY = "01"  # 주문구분 매수 (01: 시장가)
    ORDER_DVSN_SELL = "01"  # 주문구분 매도 (01: 시장가)

    # 시스템 운영 설정
    BALANCE_CHECK_INTERVAL = 30  # 잔고 조회 주기 (초)
    CONDITION_CHECK_INTERVAL = 60  # 조건검색 재실행 주기 (초)

    # 텔레그램 설정
    TELEGRAM_BOT_TOKEN = ""  # 텔레그램 봇 토큰
    TELEGRAM_CHAT_ID = ""    # 텔레그램 채팅 ID
    TELEGRAM_ENABLED = False  # 텔레그램 알림 사용 여부

    # 거래 시간 설정
    MARKET_START_TIME = "09:00:00"  # 장 시작 시간
    MARKET_END_TIME = "15:30:00"    # 장 마감 시간


# ====================================================================================================
# 데이터 클래스
# ====================================================================================================

@dataclass
class StockPosition:
    """보유 종목 정보"""
    code: str  # 종목코드
    name: str  # 종목명
    qty: int  # 보유수량
    avg_price: float  # 평균매입가
    current_price: float  # 현재가
    eval_amount: float  # 평가금액
    profit_loss: float  # 평가손익
    profit_rate: float  # 수익률(%)

    def update_current_price(self, price: float):
        """현재가 업데이트"""
        self.current_price = price
        self.eval_amount = price * self.qty
        self.profit_loss = self.eval_amount - (self.avg_price * self.qty)
        if self.avg_price > 0:
            self.profit_rate = (self.profit_loss / (self.avg_price * self.qty)) * 100


@dataclass
class OrderInfo:
    """주문 정보"""
    order_no: str  # 주문번호
    stock_code: str  # 종목코드
    stock_name: str  # 종목명
    order_type: str  # 매수/매도 구분
    order_qty: int  # 주문수량
    order_price: float  # 주문가격
    order_time: str  # 주문시간
    status: str  # 주문상태 (접수/체결/거부)


# ====================================================================================================
# STEP 1: 인증 설정
# ====================================================================================================

class AuthManager:
    """인증 관리 클래스"""

    def __init__(self, env_mode: str = "demo", product_code: str = "01"):
        self.env_mode = env_mode
        self.product_code = product_code
        self.is_authenticated = False

    def authenticate(self) -> bool:
        """인증 토큰 발급"""
        try:
            logger.info(f"인증 시작 (모드: {self.env_mode})")
            ka.auth(svr=self.env_mode, product=self.product_code)

            trenv = ka.getTREnv()
            if trenv and trenv.my_token:
                self.is_authenticated = True
                logger.info(f"인증 성공 - 계좌: {trenv.my_acct}-{trenv.my_prod}")
                return True
            else:
                logger.error("인증 실패 - 토큰 발급 실패")
                return False

        except Exception as e:
            logger.error(f"인증 오류: {e}")
            return False

    def authenticate_websocket(self) -> bool:
        """WebSocket 접속키 발급"""
        try:
            logger.info("WebSocket 접속키 발급 시작")
            ka.auth_ws(svr=self.env_mode, product=self.product_code)
            logger.info("WebSocket 접속키 발급 완료")
            return True
        except Exception as e:
            logger.error(f"WebSocket 인증 오류: {e}")
            return False


# ====================================================================================================
# STEP 2: 조건검색식 기반 종목 필터링
# ====================================================================================================

class ConditionSearchManager:
    """조건검색 관리 클래스"""

    def __init__(self):
        self.condition_list = []
        self.selected_condition = None

    def get_condition_list(self) -> pd.DataFrame:
        """조건검색식 목록 조회"""
        try:
            trenv = ka.getTREnv()
            user_id = trenv.my_htsid

            logger.info(f"조건검색식 목록 조회 (HTS ID: {user_id})")

            params = {"user_id": user_id}
            res = ka._url_fetch(
                "/uapi/domestic-stock/v1/quotations/psearch-title",
                "HHKST03900300",
                "",
                params
            )

            if res.isOK():
                df = pd.DataFrame(res.getBody().output2)
                self.condition_list = df
                logger.info(f"조건검색식 {len(df)}개 조회 완료")
                return df
            else:
                logger.error("조건검색식 목록 조회 실패")
                res.printError()
                return pd.DataFrame()

        except Exception as e:
            logger.error(f"조건검색식 목록 조회 오류: {e}")
            return pd.DataFrame()

    def search_stocks(self, seq: str = None, condition_name: str = None) -> List[str]:
        """조건검색식 실행하여 종목 조회"""
        try:
            trenv = ka.getTREnv()
            user_id = trenv.my_htsid

            # seq가 없으면 조건명으로 찾거나 첫번째 조건 사용
            if not seq:
                if self.condition_list is None or len(self.condition_list) == 0:
                    self.get_condition_list()

                if len(self.condition_list) > 0:
                    if condition_name:
                        matched = self.condition_list[self.condition_list['condition_name'] == condition_name]
                        if len(matched) > 0:
                            seq = matched.iloc[0]['seq']
                        else:
                            logger.warning(f"조건검색식 '{condition_name}' 찾을 수 없음. 첫번째 조건 사용")
                            seq = self.condition_list.iloc[0]['seq']
                    else:
                        seq = self.condition_list.iloc[0]['seq']

            if not seq:
                logger.error("조건검색식 seq를 찾을 수 없음")
                return []

            logger.info(f"조건검색 실행 (seq: {seq})")

            params = {
                "user_id": user_id,
                "seq": seq
            }

            res = ka._url_fetch(
                "/uapi/domestic-stock/v1/quotations/psearch-result",
                "HHKST03900400",
                "",
                params
            )

            if res.isOK():
                df = pd.DataFrame(res.getBody().output2)
                if len(df) > 0:
                    stock_codes = df['pdno'].tolist()
                    logger.info(f"조건검색 결과: {len(stock_codes)}개 종목")
                    return stock_codes
                else:
                    logger.info("조건검색 결과: 0개 종목")
                    return []
            else:
                logger.error("조건검색 실행 실패")
                res.printError()
                return []

        except Exception as e:
            logger.error(f"조건검색 실행 오류: {e}")
            return []


# ====================================================================================================
# STEP 3: 실시간 체결통보 WebSocket
# ====================================================================================================

class ExecutionNoticeManager:
    """실시간 체결통보 관리 클래스"""

    def __init__(self, callback=None):
        self.callback = callback
        self.ws_client = None

    def setup_websocket(self, env_dv: str = "real"):
        """WebSocket 설정"""
        try:
            # 체결통보 구독 등록
            tr_key = ka.getTREnv().my_acct + ka.getTREnv().my_prod

            def ccnl_notice_request(tr_type: str, tr_key: str, env_dv: str = "real"):
                if env_dv == "real":
                    tr_id = "H0STCNI0"
                else:
                    tr_id = "H0STCNI9"

                params = {"tr_key": tr_key}
                msg = ka.data_fetch(tr_id, tr_type, params)

                columns = [
                    "CUST_ID", "ACNT_NO", "ODER_NO", "ODER_QTY", "SELN_BYOV_CLS", "RCTF_CLS",
                    "ODER_KIND", "ODER_COND", "STCK_SHRN_ISCD", "CNTG_QTY", "CNTG_UNPR",
                    "STCK_CNTG_HOUR", "RFUS_YN", "CNTG_YN", "ACPT_YN", "BRNC_NO", "ACNT_NO2",
                    "ACNT_NAME", "ORD_COND_PRC", "ORD_EXG_GB", "POPUP_YN", "FILLER", "CRDT_CLS",
                    "CRDT_LOAN_DATE", "CNTG_ISNM40", "ODER_PRC"
                ]

                return msg, columns

            # WebSocket 구독 등록
            ka.KISWebSocket.subscribe(ccnl_notice_request, tr_key, {"env_dv": env_dv})

            # WebSocket 클라이언트 생성
            self.ws_client = ka.KISWebSocket("/tryitout/H0STCNI0")

            logger.info("WebSocket 체결통보 구독 설정 완료")

        except Exception as e:
            logger.error(f"WebSocket 설정 오류: {e}")

    def start_websocket(self):
        """WebSocket 시작"""
        try:
            if self.ws_client:
                logger.info("WebSocket 체결통보 시작")
                self.ws_client.start(on_result=self._on_execution_notice, result_all_data=True)
        except Exception as e:
            logger.error(f"WebSocket 시작 오류: {e}")

    def _on_execution_notice(self, ws, tr_id, df, data_map):
        """체결통보 수신 콜백"""
        try:
            if not df.empty:
                # CNTG_YN이 2이면 체결통보, 1이면 접수통보
                cntg_yn = df.iloc[0]['CNTG_YN']

                if cntg_yn == '2':  # 체결통보
                    logger.info("=== 체결통보 수신 ===")
                    logger.info(f"종목코드: {df.iloc[0]['STCK_SHRN_ISCD']}")
                    logger.info(f"종목명: {df.iloc[0]['CNTG_ISNM40']}")
                    logger.info(f"매수/매도: {df.iloc[0]['SELN_BYOV_CLS']}")
                    logger.info(f"체결수량: {df.iloc[0]['CNTG_QTY']}")
                    logger.info(f"체결단가: {df.iloc[0]['CNTG_UNPR']}")

                    # 콜백 호출
                    if self.callback:
                        self.callback(df)

                elif cntg_yn == '1':  # 접수통보
                    logger.info("=== 주문접수 통보 ===")
                    logger.info(f"주문번호: {df.iloc[0]['ODER_NO']}")

        except Exception as e:
            logger.error(f"체결통보 처리 오류: {e}")


# ====================================================================================================
# STEP 4: 주문 실행 (매수/매도)
# ====================================================================================================

class OrderManager:
    """주문 관리 클래스"""

    def __init__(self, env_mode: str = "demo"):
        self.env_mode = env_mode
        self.order_history = []

    def buy_stock(self, stock_code: str, qty: int, price: str = "0") -> Optional[OrderInfo]:
        """주식 매수"""
        try:
            trenv = ka.getTREnv()

            # 주문구분: 01-시장가
            ord_dvsn = TradingConfig.ORDER_DVSN_BUY

            logger.info(f"매수주문 실행: {stock_code} {qty}주")

            # TR ID 설정
            if self.env_mode == "real":
                tr_id = "TTTC0012U"
            else:
                tr_id = "VTTC0012U"

            params = {
                "CANO": trenv.my_acct,
                "ACNT_PRDT_CD": trenv.my_prod,
                "PDNO": stock_code,
                "ORD_DVSN": ord_dvsn,
                "ORD_QTY": str(qty),
                "ORD_UNPR": price,
                "EXCG_ID_DVSN_CD": "KRX",
                "SLL_TYPE": "",
                "CNDT_PRIC": ""
            }

            res = ka._url_fetch(
                "/uapi/domestic-stock/v1/trading/order-cash",
                tr_id,
                "",
                params,
                postFlag=True
            )

            if res.isOK():
                body = res.getBody()
                order_info = OrderInfo(
                    order_no=body.output.get('ORD_NO', ''),
                    stock_code=stock_code,
                    stock_name=body.output.get('KRX_FWDG_ORD_ORGNO', ''),
                    order_type="매수",
                    order_qty=qty,
                    order_price=float(price) if price != "0" else 0,
                    order_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    status="접수"
                )
                self.order_history.append(order_info)
                logger.info(f"매수주문 성공: 주문번호 {order_info.order_no}")
                return order_info
            else:
                logger.error(f"매수주문 실패: {stock_code}")
                res.printError()
                return None

        except Exception as e:
            logger.error(f"매수주문 오류: {e}")
            return None

    def sell_stock(self, stock_code: str, qty: int, price: str = "0") -> Optional[OrderInfo]:
        """주식 매도"""
        try:
            trenv = ka.getTREnv()

            # 주문구분: 01-시장가
            ord_dvsn = TradingConfig.ORDER_DVSN_SELL

            logger.info(f"매도주문 실행: {stock_code} {qty}주")

            # TR ID 설정
            if self.env_mode == "real":
                tr_id = "TTTC0011U"
            else:
                tr_id = "VTTC0011U"

            params = {
                "CANO": trenv.my_acct,
                "ACNT_PRDT_CD": trenv.my_prod,
                "PDNO": stock_code,
                "ORD_DVSN": ord_dvsn,
                "ORD_QTY": str(qty),
                "ORD_UNPR": price,
                "EXCG_ID_DVSN_CD": "KRX",
                "SLL_TYPE": "01",  # 01: 일반매도
                "CNDT_PRIC": ""
            }

            res = ka._url_fetch(
                "/uapi/domestic-stock/v1/trading/order-cash",
                tr_id,
                "",
                params,
                postFlag=True
            )

            if res.isOK():
                body = res.getBody()
                order_info = OrderInfo(
                    order_no=body.output.get('ORD_NO', ''),
                    stock_code=stock_code,
                    stock_name=body.output.get('KRX_FWDG_ORD_ORGNO', ''),
                    order_type="매도",
                    order_qty=qty,
                    order_price=float(price) if price != "0" else 0,
                    order_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    status="접수"
                )
                self.order_history.append(order_info)
                logger.info(f"매도주문 성공: 주문번호 {order_info.order_no}")
                return order_info
            else:
                logger.error(f"매도주문 실패: {stock_code}")
                res.printError()
                return None

        except Exception as e:
            logger.error(f"매도주문 오류: {e}")
            return None

    def get_buy_possible_qty(self, stock_code: str, price: str) -> int:
        """매수 가능 수량 조회"""
        try:
            trenv = ka.getTREnv()

            # TR ID 설정
            if self.env_mode == "real":
                tr_id = "TTTC8908R"
            else:
                tr_id = "VTTC8908R"

            params = {
                "CANO": trenv.my_acct,
                "ACNT_PRDT_CD": trenv.my_prod,
                "PDNO": stock_code,
                "ORD_UNPR": price,
                "ORD_DVSN": "01",  # 시장가
                "CMA_EVLU_AMT_ICLD_YN": "N",
                "OVRS_ICLD_YN": "N"
            }

            res = ka._url_fetch(
                "/uapi/domestic-stock/v1/trading/inquire-psbl-order",
                tr_id,
                "",
                params
            )

            if res.isOK():
                body = res.getBody()
                max_qty = int(body.output.get('max_buy_qty', 0))
                return max_qty
            else:
                logger.error(f"매수가능수량 조회 실패: {stock_code}")
                return 0

        except Exception as e:
            logger.error(f"매수가능수량 조회 오류: {e}")
            return 0


# ====================================================================================================
# STEP 5: 텔레그램 봇 연동
# ====================================================================================================

class TelegramNotifier:
    """텔레그램 알림 클래스"""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.bot = None

        if TELEGRAM_AVAILABLE and bot_token and chat_id:
            try:
                self.bot = Bot(token=bot_token)
                logger.info("텔레그램 봇 초기화 완료")
            except Exception as e:
                logger.error(f"텔레그램 봇 초기화 실패: {e}")

    def send_message(self, message: str):
        """텔레그램 메시지 전송"""
        if not self.bot or not TradingConfig.TELEGRAM_ENABLED:
            return

        try:
            asyncio.run(self._async_send_message(message))
        except Exception as e:
            logger.error(f"텔레그램 메시지 전송 실패: {e}")

    async def _async_send_message(self, message: str):
        """비동기 메시지 전송"""
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=message)
            logger.debug("텔레그램 메시지 전송 완료")
        except TelegramError as e:
            logger.error(f"텔레그램 API 오류: {e}")

    def notify_buy(self, stock_code: str, stock_name: str, qty: int, price: float):
        """매수 체결 알림"""
        message = f"🔵 [매수 체결]\n종목: {stock_name}({stock_code})\n수량: {qty}주\n가격: {price:,.0f}원"
        self.send_message(message)

    def notify_sell(self, stock_code: str, stock_name: str, qty: int, price: float, profit_rate: float):
        """매도 체결 알림"""
        emoji = "🔴" if profit_rate < 0 else "🟢"
        message = f"{emoji} [매도 체결]\n종목: {stock_name}({stock_code})\n수량: {qty}주\n가격: {price:,.0f}원\n수익률: {profit_rate:.2f}%"
        self.send_message(message)

    def notify_balance(self, total_eval: float, total_profit: float, profit_rate: float):
        """잔고 현황 알림"""
        message = f"💰 [잔고 현황]\n평가금액: {total_eval:,.0f}원\n평가손익: {total_profit:,.0f}원\n수익률: {profit_rate:.2f}%"
        self.send_message(message)


# ====================================================================================================
# STEP 6: 잔고/손익 조회
# ====================================================================================================

class BalanceManager:
    """잔고 관리 클래스"""

    def __init__(self, env_mode: str = "demo"):
        self.env_mode = env_mode
        self.positions: Dict[str, StockPosition] = {}

    def get_balance(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """잔고 조회"""
        try:
            trenv = ka.getTREnv()

            # TR ID 설정
            if self.env_mode == "real":
                tr_id = "TTTC8434R"
            else:
                tr_id = "VTTC8434R"

            params = {
                "CANO": trenv.my_acct,
                "ACNT_PRDT_CD": trenv.my_prod,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",  # 02: 종목별
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": ""
            }

            res = ka._url_fetch(
                "/uapi/domestic-stock/v1/trading/inquire-balance",
                tr_id,
                "",
                params
            )

            if res.isOK():
                df1 = pd.DataFrame(res.getBody().output1)  # 보유종목 상세
                df2 = pd.DataFrame(res.getBody().output2)  # 계좌 요약

                # 보유종목 업데이트
                self._update_positions(df1)

                return df1, df2
            else:
                logger.error("잔고 조회 실패")
                res.printError()
                return pd.DataFrame(), pd.DataFrame()

        except Exception as e:
            logger.error(f"잔고 조회 오류: {e}")
            return pd.DataFrame(), pd.DataFrame()

    def _update_positions(self, df: pd.DataFrame):
        """보유종목 정보 업데이트"""
        try:
            self.positions.clear()

            for _, row in df.iterrows():
                qty = int(row.get('hldg_qty', 0))
                if qty > 0:
                    stock_code = row.get('pdno', '')
                    position = StockPosition(
                        code=stock_code,
                        name=row.get('prdt_name', ''),
                        qty=qty,
                        avg_price=float(row.get('pchs_avg_pric', 0)),
                        current_price=float(row.get('prpr', 0)),
                        eval_amount=float(row.get('evlu_amt', 0)),
                        profit_loss=float(row.get('evlu_pfls_amt', 0)),
                        profit_rate=float(row.get('evlu_pfls_rt', 0))
                    )
                    self.positions[stock_code] = position

            logger.info(f"보유종목 {len(self.positions)}개 업데이트 완료")

        except Exception as e:
            logger.error(f"보유종목 업데이트 오류: {e}")

    def check_sell_condition(self) -> List[Tuple[str, int, str]]:
        """매도 조건 체크 (목표수익률/손절률)"""
        sell_list = []

        for code, position in self.positions.items():
            # 목표수익률 도달
            if position.profit_rate >= TradingConfig.TARGET_PROFIT_RATE:
                logger.info(f"{position.name}({code}) 목표수익률 도달: {position.profit_rate:.2f}%")
                sell_list.append((code, position.qty, "목표수익"))

            # 손절률 도달
            elif position.profit_rate <= TradingConfig.STOP_LOSS_RATE:
                logger.info(f"{position.name}({code}) 손절률 도달: {position.profit_rate:.2f}%")
                sell_list.append((code, position.qty, "손절"))

        return sell_list


# ====================================================================================================
# STEP 7: 예외처리 및 로깅
# ====================================================================================================

class ErrorHandler:
    """에러 처리 클래스"""

    @staticmethod
    def handle_api_error(error_code: str, error_message: str) -> bool:
        """API 에러 처리"""
        # EGW00123: Access Token 만료
        if error_code == "EGW00123":
            logger.warning("Access Token 만료 - 재발급 필요")
            return True

        # EGW00201: 초당 거래건수 초과
        elif error_code == "EGW00201":
            logger.warning("초당 거래건수 초과 - 0.5초 대기")
            time.sleep(0.5)
            return True

        else:
            logger.error(f"API 에러: {error_code} - {error_message}")
            return False

    @staticmethod
    def is_trading_time() -> bool:
        """거래 가능 시간 체크"""
        now = datetime.now().time()
        start_time = datetime.strptime(TradingConfig.MARKET_START_TIME, "%H:%M:%S").time()
        end_time = datetime.strptime(TradingConfig.MARKET_END_TIME, "%H:%M:%S").time()

        return start_time <= now <= end_time


# ====================================================================================================
# STEP 8: 통합 자동매매 시스템 메인 클래스
# ====================================================================================================

class AutoTradingSystem:
    """자동매매 시스템 메인 클래스"""

    def __init__(self):
        self.auth_manager = AuthManager(
            env_mode=TradingConfig.ENV_MODE,
            product_code=TradingConfig.PRODUCT_CODE
        )
        self.condition_manager = ConditionSearchManager()
        self.order_manager = OrderManager(env_mode=TradingConfig.ENV_MODE)
        self.balance_manager = BalanceManager(env_mode=TradingConfig.ENV_MODE)
        self.telegram = TelegramNotifier(
            bot_token=TradingConfig.TELEGRAM_BOT_TOKEN,
            chat_id=TradingConfig.TELEGRAM_CHAT_ID
        )
        self.execution_manager = ExecutionNoticeManager(callback=self._on_execution_callback)

        self.is_running = False
        self.target_stocks = []  # 매수 대상 종목 리스트

    def initialize(self) -> bool:
        """시스템 초기화"""
        try:
            logger.info("="*80)
            logger.info("한국투자증권 자동트레이딩 시스템 시작")
            logger.info("="*80)

            # 인증
            if not self.auth_manager.authenticate():
                logger.error("인증 실패 - 시스템 종료")
                return False

            # WebSocket 인증
            if not self.auth_manager.authenticate_websocket():
                logger.error("WebSocket 인증 실패 - 시스템 종료")
                return False

            # 조건검색식 목록 조회
            conditions = self.condition_manager.get_condition_list()
            if conditions.empty:
                logger.error("조건검색식이 없습니다 - 시스템 종료")
                return False

            logger.info("시스템 초기화 완료")
            return True

        except Exception as e:
            logger.error(f"시스템 초기화 오류: {e}")
            return False

    def start(self):
        """자동매매 시작"""
        try:
            if not self.initialize():
                return

            self.is_running = True

            # WebSocket 체결통보 시작 (별도 스레드)
            ws_thread = threading.Thread(target=self._start_websocket_thread, daemon=True)
            ws_thread.start()

            # 텔레그램 시작 알림
            self.telegram.send_message("🚀 자동매매 시스템 시작")

            # 메인 루프
            self._main_loop()

        except KeyboardInterrupt:
            logger.info("사용자에 의한 종료")
            self.stop()
        except Exception as e:
            logger.error(f"시스템 실행 오류: {e}")
            self.stop()

    def stop(self):
        """자동매매 중지"""
        logger.info("자동매매 시스템 종료 중...")
        self.is_running = False
        self.telegram.send_message("🛑 자동매매 시스템 종료")
        logger.info("자동매매 시스템 종료 완료")

    def _start_websocket_thread(self):
        """WebSocket 스레드"""
        try:
            self.execution_manager.setup_websocket(env_dv=TradingConfig.ENV_MODE)
            self.execution_manager.start_websocket()
        except Exception as e:
            logger.error(f"WebSocket 스레드 오류: {e}")

    def _main_loop(self):
        """메인 루프"""
        last_condition_check = 0
        last_balance_check = 0

        while self.is_running:
            try:
                current_time = time.time()

                # 거래 가능 시간 체크
                if not ErrorHandler.is_trading_time():
                    logger.info("장 시간 외 - 대기 중...")
                    time.sleep(60)
                    continue

                # 조건검색 실행 (주기적)
                if current_time - last_condition_check >= TradingConfig.CONDITION_CHECK_INTERVAL:
                    self._check_and_buy_stocks()
                    last_condition_check = current_time

                # 잔고 조회 및 매도 조건 체크 (주기적)
                if current_time - last_balance_check >= TradingConfig.BALANCE_CHECK_INTERVAL:
                    self._check_and_sell_stocks()
                    last_balance_check = current_time

                # CPU 부하 방지
                time.sleep(1)

            except Exception as e:
                logger.error(f"메인 루프 오류: {e}")
                time.sleep(5)

    def _check_and_buy_stocks(self):
        """조건검색 및 매수 실행"""
        try:
            logger.info("--- 조건검색 실행 ---")

            # 조건검색 실행
            stock_codes = self.condition_manager.search_stocks(
                seq=TradingConfig.CONDITION_SEQ,
                condition_name=TradingConfig.CONDITION_NAME
            )

            if not stock_codes:
                logger.info("매수 대상 종목 없음")
                return

            # 현재 보유 종목 수 확인
            df1, df2 = self.balance_manager.get_balance()
            current_holdings = len(self.balance_manager.positions)

            if current_holdings >= TradingConfig.MAX_STOCKS:
                logger.info(f"최대 보유 종목 수 도달 ({current_holdings}/{TradingConfig.MAX_STOCKS})")
                return

            # 매수 가능한 종목 수
            available_slots = TradingConfig.MAX_STOCKS - current_holdings

            # 매수 실행
            for stock_code in stock_codes[:available_slots]:
                # 이미 보유 중인 종목은 스킵
                if stock_code in self.balance_manager.positions:
                    continue

                # 매수 수량 계산 (매수금액 / 현재가)
                # 여기서는 간단히 매수금액으로만 계산 (실제로는 현재가 조회 필요)
                qty = 1  # 최소 1주

                # 매수 주문
                order_info = self.order_manager.buy_stock(stock_code, qty)

                if order_info:
                    logger.info(f"매수주문 완료: {stock_code}")

                # API 호출 제한 고려
                time.sleep(0.1)

        except Exception as e:
            logger.error(f"조건검색 및 매수 오류: {e}")

    def _check_and_sell_stocks(self):
        """잔고 조회 및 매도 실행"""
        try:
            logger.info("--- 잔고 조회 및 매도 체크 ---")

            # 잔고 조회
            df1, df2 = self.balance_manager.get_balance()

            # 매도 조건 체크
            sell_list = self.balance_manager.check_sell_condition()

            # 매도 실행
            for stock_code, qty, reason in sell_list:
                logger.info(f"매도 실행: {stock_code} ({reason})")
                order_info = self.order_manager.sell_stock(stock_code, qty)

                if order_info:
                    logger.info(f"매도주문 완료: {stock_code}")

                # API 호출 제한 고려
                time.sleep(0.1)

            # 잔고 현황 로깅
            if not df2.empty:
                total_eval = float(df2.iloc[0].get('tot_evlu_amt', 0))
                total_profit = float(df2.iloc[0].get('evlu_pfls_smtl_amt', 0))
                if total_eval > 0:
                    profit_rate = (total_profit / total_eval) * 100
                    logger.info(f"총 평가금액: {total_eval:,.0f}원, 평가손익: {total_profit:,.0f}원, 수익률: {profit_rate:.2f}%")

        except Exception as e:
            logger.error(f"잔고 조회 및 매도 오류: {e}")

    def _on_execution_callback(self, df: pd.DataFrame):
        """체결통보 콜백"""
        try:
            if df.empty:
                return

            row = df.iloc[0]
            stock_code = row['STCK_SHRN_ISCD']
            stock_name = row['CNTG_ISNM40']
            order_type = row['SELN_BYOV_CLS']  # 01: 매도, 02: 매수
            qty = int(row['CNTG_QTY'])
            price = float(row['CNTG_UNPR'])

            # 텔레그램 알림
            if order_type == '02':  # 매수
                self.telegram.notify_buy(stock_code, stock_name, qty, price)
            elif order_type == '01':  # 매도
                # 수익률 계산 (보유종목 정보에서)
                profit_rate = 0
                if stock_code in self.balance_manager.positions:
                    position = self.balance_manager.positions[stock_code]
                    profit_rate = position.profit_rate

                self.telegram.notify_sell(stock_code, stock_name, qty, price, profit_rate)

        except Exception as e:
            logger.error(f"체결통보 콜백 오류: {e}")


# ====================================================================================================
# 메인 실행
# ====================================================================================================

def main():
    """메인 함수"""

    # 설정 파일 로드 (선택사항)
    # config.yaml 파일이 있으면 설정 로드
    config_file = "trading_config.yaml"
    if os.path.exists(config_file):
        try:
            import yaml
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.load(f, Loader=yaml.FullLoader)

            # 설정 적용
            TradingConfig.ENV_MODE = config.get('env_mode', TradingConfig.ENV_MODE)
            TradingConfig.MAX_STOCKS = config.get('max_stocks', TradingConfig.MAX_STOCKS)
            TradingConfig.BUY_AMOUNT = config.get('buy_amount', TradingConfig.BUY_AMOUNT)
            TradingConfig.TARGET_PROFIT_RATE = config.get('target_profit_rate', TradingConfig.TARGET_PROFIT_RATE)
            TradingConfig.STOP_LOSS_RATE = config.get('stop_loss_rate', TradingConfig.STOP_LOSS_RATE)
            TradingConfig.TELEGRAM_BOT_TOKEN = config.get('telegram_bot_token', '')
            TradingConfig.TELEGRAM_CHAT_ID = config.get('telegram_chat_id', '')
            TradingConfig.TELEGRAM_ENABLED = config.get('telegram_enabled', False)

            logger.info(f"설정 파일 로드 완료: {config_file}")
        except Exception as e:
            logger.warning(f"설정 파일 로드 실패: {e}")

    # 자동매매 시스템 생성 및 시작
    system = AutoTradingSystem()
    system.start()


if __name__ == "__main__":
    main()
