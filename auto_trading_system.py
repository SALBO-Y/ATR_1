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
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
    from telegram.error import TelegramError
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("Warning: python-telegram-bot not installed. Telegram features will be disabled.")
    print("Install with: pip install python-telegram-bot>=20.0")

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
# STEP 5: 텔레그램 봇 연동 (버튼 클릭형 양방향 통신)
# ====================================================================================================

class TelegramNotifier:
    """텔레그램 알림 클래스 (버튼 클릭형 인터페이스)"""

    def __init__(self, bot_token: str, chat_id: str, trading_system=None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.trading_system = trading_system
        self.application = None
        self.bot_thread = None

        # 알림 설정 상태
        self.execution_notice_enabled = True  # 체결알림 ON/OFF

        if TELEGRAM_AVAILABLE and bot_token and chat_id:
            try:
                # Application 생성
                self.application = Application.builder().token(bot_token).build()

                # 핸들러 등록
                self._register_handlers()

                logger.info("텔레그램 봇 초기화 완료")
            except Exception as e:
                logger.error(f"텔레그램 봇 초기화 실패: {e}")

    def _register_handlers(self):
        """핸들러 등록"""
        if not self.application:
            return

        # 명령어 핸들러
        self.application.add_handler(CommandHandler("start", self._cmd_start))
        self.application.add_handler(CommandHandler("menu", self._cmd_menu))
        self.application.add_handler(CommandHandler("help", self._cmd_help))

        # 버튼 콜백 핸들러
        self.application.add_handler(CallbackQueryHandler(self._button_callback))

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """봇 시작 명령어"""
        welcome_text = (
            "🤖 한국투자증권 자동트레이딩 시스템\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "환영합니다! 아래 메뉴를 선택하세요.\n\n"
            f"현재 모드: {TradingConfig.ENV_MODE.upper()}\n"
            f"체결알림: {'ON ✅' if self.execution_notice_enabled else 'OFF ❌'}"
        )

        keyboard = self._get_main_menu_keyboard()

        await update.message.reply_text(
            welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """메뉴 표시 명령어"""
        menu_text = (
            "📱 메인 메뉴\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "원하는 기능을 선택하세요."
        )

        keyboard = self._get_main_menu_keyboard()

        await update.message.reply_text(
            menu_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """도움말 명령어"""
        help_text = (
            "📖 사용 가이드\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔹 /start - 봇 시작 및 메인 메뉴\n"
            "🔹 /menu - 메인 메뉴 표시\n"
            "🔹 /help - 도움말 표시\n\n"
            "📌 메뉴 설명:\n"
            "• 봇 시작/종료 - 자동매매 시스템 제어\n"
            "• 실시간 잔고 - 현재 보유 종목 및 잔고 조회\n"
            "• 미실현손익 - 실시간 평가손익 조회\n"
            "• 체결알림 설정 - 체결 알림 ON/OFF\n"
            "• 시스템 상태 - 현재 시스템 운영 상태\n\n"
            "💡 Tip: 버튼을 클릭하여 쉽게 조회 가능합니다!"
        )

        await update.message.reply_text(help_text)

    def _get_main_menu_keyboard(self):
        """메인 메뉴 키보드 생성"""
        trading_status = "실행중 🟢" if (self.trading_system and self.trading_system.is_running) else "정지 🔴"
        notice_status = "ON ✅" if self.execution_notice_enabled else "OFF ❌"

        keyboard = [
            [
                InlineKeyboardButton(f"🤖 봇 시작/종료 ({trading_status})", callback_data="toggle_bot"),
            ],
            [
                InlineKeyboardButton("💰 실시간 잔고", callback_data="balance"),
                InlineKeyboardButton("📊 미실현손익", callback_data="unrealized_pl"),
            ],
            [
                InlineKeyboardButton(f"🔔 체결알림 ({notice_status})", callback_data="toggle_notice"),
                InlineKeyboardButton("📈 시스템 상태", callback_data="system_status"),
            ],
            [
                InlineKeyboardButton("🔄 새로고침", callback_data="refresh"),
                InlineKeyboardButton("❓ 도움말", callback_data="help"),
            ]
        ]

        return keyboard

    async def _button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """버튼 클릭 콜백 처리"""
        query = update.callback_query
        await query.answer()

        callback_data = query.data

        try:
            if callback_data == "toggle_bot":
                await self._handle_toggle_bot(query)
            elif callback_data == "balance":
                await self._handle_balance(query)
            elif callback_data == "unrealized_pl":
                await self._handle_unrealized_pl(query)
            elif callback_data == "toggle_notice":
                await self._handle_toggle_notice(query)
            elif callback_data == "system_status":
                await self._handle_system_status(query)
            elif callback_data == "refresh":
                await self._handle_refresh(query)
            elif callback_data == "help":
                await self._handle_help(query)
        except Exception as e:
            logger.error(f"버튼 콜백 처리 오류: {e}")
            await query.edit_message_text(f"⚠️ 오류 발생: {str(e)}")

    async def _handle_toggle_bot(self, query):
        """봇 시작/종료 처리"""
        if not self.trading_system:
            await query.edit_message_text("⚠️ 트레이딩 시스템이 연결되지 않았습니다.")
            return

        if self.trading_system.is_running:
            # 봇 종료
            self.trading_system.stop()
            message = "🛑 자동매매 시스템을 종료합니다."
        else:
            # 봇 시작 (별도 스레드에서 실행 중이므로 상태만 변경)
            message = "⚠️ 시스템은 메인 프로그램에서 시작됩니다.\n현재 상태를 확인하세요."

        keyboard = self._get_main_menu_keyboard()
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _handle_balance(self, query):
        """실시간 잔고 조회 처리"""
        if not self.trading_system:
            await query.edit_message_text("⚠️ 트레이딩 시스템이 연결되지 않았습니다.")
            return

        try:
            df1, df2 = self.trading_system.balance_manager.get_balance()

            if df1.empty:
                message = "📭 보유 종목이 없습니다."
            else:
                message = "💰 [실시간 잔고]\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

                # 보유 종목 상세
                for _, row in df1.iterrows():
                    qty = int(row.get('hldg_qty', 0))
                    if qty > 0:
                        name = row.get('prdt_name', '')
                        code = row.get('pdno', '')
                        avg_price = float(row.get('pchs_avg_pric', 0))
                        current_price = float(row.get('prpr', 0))
                        eval_amt = float(row.get('evlu_amt', 0))
                        profit = float(row.get('evlu_pfls_amt', 0))
                        profit_rate = float(row.get('evlu_pfls_rt', 0))

                        emoji = "🟢" if profit >= 0 else "🔴"

                        message += (
                            f"{emoji} {name} ({code})\n"
                            f"  보유: {qty}주 | 평균: {avg_price:,.0f}원\n"
                            f"  현재: {current_price:,.0f}원 | 평가: {eval_amt:,.0f}원\n"
                            f"  손익: {profit:,.0f}원 ({profit_rate:+.2f}%)\n\n"
                        )

                # 계좌 요약
                if not df2.empty:
                    total_eval = float(df2.iloc[0].get('tot_evlu_amt', 0))
                    total_profit = float(df2.iloc[0].get('evlu_pfls_smtl_amt', 0))

                    message += (
                        "━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"💵 총 평가금액: {total_eval:,.0f}원\n"
                        f"📈 총 평가손익: {total_profit:,.0f}원\n"
                    )

            keyboard = [[InlineKeyboardButton("🔙 메인 메뉴", callback_data="refresh")]]
            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        except Exception as e:
            logger.error(f"잔고 조회 오류: {e}")
            await query.edit_message_text(f"⚠️ 잔고 조회 실패: {str(e)}")

    async def _handle_unrealized_pl(self, query):
        """미실현손익 조회 처리"""
        if not self.trading_system:
            await query.edit_message_text("⚠️ 트레이딩 시스템이 연결되지 않았습니다.")
            return

        try:
            df1, df2 = self.trading_system.balance_manager.get_balance()

            if df1.empty:
                message = "📭 보유 종목이 없습니다."
            else:
                message = "📊 [실시간 미실현손익]\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

                total_buy_amt = 0
                total_eval_amt = 0

                # 종목별 손익
                for _, row in df1.iterrows():
                    qty = int(row.get('hldg_qty', 0))
                    if qty > 0:
                        name = row.get('prdt_name', '')
                        code = row.get('pdno', '')
                        avg_price = float(row.get('pchs_avg_pric', 0))
                        current_price = float(row.get('prpr', 0))
                        profit = float(row.get('evlu_pfls_amt', 0))
                        profit_rate = float(row.get('evlu_pfls_rt', 0))

                        buy_amt = avg_price * qty
                        eval_amt = current_price * qty

                        total_buy_amt += buy_amt
                        total_eval_amt += eval_amt

                        emoji = "🟢" if profit >= 0 else "🔴"

                        message += (
                            f"{emoji} {name}\n"
                            f"  매입금액: {buy_amt:,.0f}원\n"
                            f"  평가금액: {eval_amt:,.0f}원\n"
                            f"  손익: {profit:,.0f}원 ({profit_rate:+.2f}%)\n\n"
                        )

                # 전체 손익
                total_profit = total_eval_amt - total_buy_amt
                total_profit_rate = (total_profit / total_buy_amt * 100) if total_buy_amt > 0 else 0

                emoji = "🟢" if total_profit >= 0 else "🔴"

                message += (
                    "━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{emoji} 전체 손익\n"
                    f"  총 매입금액: {total_buy_amt:,.0f}원\n"
                    f"  총 평가금액: {total_eval_amt:,.0f}원\n"
                    f"  총 손익: {total_profit:,.0f}원\n"
                    f"  수익률: {total_profit_rate:+.2f}%\n"
                )

            keyboard = [[InlineKeyboardButton("🔙 메인 메뉴", callback_data="refresh")]]
            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        except Exception as e:
            logger.error(f"미실현손익 조회 오류: {e}")
            await query.edit_message_text(f"⚠️ 미실현손익 조회 실패: {str(e)}")

    async def _handle_toggle_notice(self, query):
        """체결알림 ON/OFF 처리"""
        self.execution_notice_enabled = not self.execution_notice_enabled

        status = "ON ✅" if self.execution_notice_enabled else "OFF ❌"
        message = f"🔔 체결알림이 {status} 되었습니다."

        keyboard = self._get_main_menu_keyboard()
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _handle_system_status(self, query):
        """시스템 상태 조회 처리"""
        if not self.trading_system:
            await query.edit_message_text("⚠️ 트레이딩 시스템이 연결되지 않았습니다.")
            return

        status = "실행중 🟢" if self.trading_system.is_running else "정지 🔴"
        notice_status = "ON ✅" if self.execution_notice_enabled else "OFF ❌"

        message = (
            "📈 [시스템 상태]\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🤖 자동매매: {status}\n"
            f"🔔 체결알림: {notice_status}\n"
            f"🌐 환경: {TradingConfig.ENV_MODE.upper()}\n"
            f"📊 최대 보유 종목: {TradingConfig.MAX_STOCKS}개\n"
            f"💰 종목당 매수금액: {TradingConfig.BUY_AMOUNT:,}원\n"
            f"🎯 목표수익률: {TradingConfig.TARGET_PROFIT_RATE}%\n"
            f"🛡️ 손절률: {TradingConfig.STOP_LOSS_RATE}%\n\n"
            f"현재시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        )

        keyboard = [[InlineKeyboardButton("🔙 메인 메뉴", callback_data="refresh")]]
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _handle_refresh(self, query):
        """새로고침 처리"""
        menu_text = (
            "📱 메인 메뉴\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "원하는 기능을 선택하세요.\n\n"
            f"현재시간: {datetime.now().strftime('%H:%M:%S')}"
        )

        keyboard = self._get_main_menu_keyboard()
        await query.edit_message_text(
            menu_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _handle_help(self, query):
        """도움말 처리"""
        help_text = (
            "📖 사용 가이드\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔹 /start - 봇 시작 및 메인 메뉴\n"
            "🔹 /menu - 메인 메뉴 표시\n"
            "🔹 /help - 도움말 표시\n\n"
            "📌 메뉴 설명:\n"
            "• 봇 시작/종료 - 자동매매 시스템 제어\n"
            "• 실시간 잔고 - 현재 보유 종목 및 잔고 조회\n"
            "• 미실현손익 - 실시간 평가손익 조회\n"
            "• 체결알림 설정 - 체결 알림 ON/OFF\n"
            "• 시스템 상태 - 현재 시스템 운영 상태\n\n"
            "💡 Tip: 버튼을 클릭하여 쉽게 조회 가능합니다!"
        )

        keyboard = [[InlineKeyboardButton("🔙 메인 메뉴", callback_data="refresh")]]
        await query.edit_message_text(
            help_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    def start_bot(self):
        """텔레그램 봇 시작 (별도 스레드)"""
        if not self.application or not TradingConfig.TELEGRAM_ENABLED:
            return

        def run_bot():
            try:
                logger.info("텔레그램 봇 시작")
                self.application.run_polling(allowed_updates=Update.ALL_TYPES)
            except Exception as e:
                logger.error(f"텔레그램 봇 실행 오류: {e}")

        self.bot_thread = threading.Thread(target=run_bot, daemon=True)
        self.bot_thread.start()

    def stop_bot(self):
        """텔레그램 봇 중지"""
        if self.application:
            try:
                self.application.stop()
                logger.info("텔레그램 봇 종료")
            except Exception as e:
                logger.error(f"텔레그램 봇 종료 오류: {e}")

    async def send_message_async(self, message: str):
        """비동기 메시지 전송"""
        if not self.application or not TradingConfig.TELEGRAM_ENABLED:
            return

        try:
            await self.application.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"메시지 전송 실패: {e}")

    def send_message(self, message: str):
        """동기 메시지 전송 (기존 코드 호환용)"""
        if not self.application or not TradingConfig.TELEGRAM_ENABLED:
            return

        try:
            # 이벤트 루프에서 실행
            asyncio.run(self.send_message_async(message))
        except Exception as e:
            logger.error(f"메시지 전송 실패: {e}")

    def notify_buy(self, stock_code: str, stock_name: str, qty: int, price: float):
        """매수 체결 알림"""
        if not self.execution_notice_enabled:
            return

        message = (
            f"🔵 <b>[매수 체결]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"종목: {stock_name} ({stock_code})\n"
            f"수량: {qty}주\n"
            f"가격: {price:,.0f}원\n"
            f"시간: {datetime.now().strftime('%H:%M:%S')}"
        )
        self.send_message(message)

    def notify_sell(self, stock_code: str, stock_name: str, qty: int, price: float, profit_rate: float):
        """매도 체결 알림"""
        if not self.execution_notice_enabled:
            return

        emoji = "🔴" if profit_rate < 0 else "🟢"
        message = (
            f"{emoji} <b>[매도 체결]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"종목: {stock_name} ({stock_code})\n"
            f"수량: {qty}주\n"
            f"가격: {price:,.0f}원\n"
            f"수익률: {profit_rate:+.2f}%\n"
            f"시간: {datetime.now().strftime('%H:%M:%S')}"
        )
        self.send_message(message)

    def notify_balance(self, total_eval: float, total_profit: float, profit_rate: float):
        """잔고 현황 알림"""
        emoji = "🟢" if total_profit >= 0 else "🔴"
        message = (
            f"{emoji} <b>[잔고 현황]</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"평가금액: {total_eval:,.0f}원\n"
            f"평가손익: {total_profit:,.0f}원\n"
            f"수익률: {profit_rate:+.2f}%\n"
            f"시간: {datetime.now().strftime('%H:%M:%S')}"
        )
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
            chat_id=TradingConfig.TELEGRAM_CHAT_ID,
            trading_system=self  # 트레이딩 시스템 참조 전달
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

            # 텔레그램 봇 시작 (별도 스레드)
            self.telegram.start_bot()
            logger.info("텔레그램 봇 시작됨")

            # WebSocket 체결통보 시작 (별도 스레드)
            ws_thread = threading.Thread(target=self._start_websocket_thread, daemon=True)
            ws_thread.start()

            # 텔레그램 시작 알림
            self.telegram.send_message("🚀 자동매매 시스템 시작\n\n/start 명령어로 메뉴를 사용하세요.")

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
        self.telegram.stop_bot()
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
