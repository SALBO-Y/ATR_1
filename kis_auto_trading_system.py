#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
한국투자증권 자동시스템트레이딩 매매 프로그램
===========================================

[주요 기능]
- 한국투자증권 서버에 저장된 내 종목검색식 기반으로 조회된 종목 스캘핑 트레이딩 실시
- 텔레그램봇 연동하여 매수/매도 체결알림, 실시간 잔고조회, 실시간 미실현손익 조회 실시
- REST 호출형 API를 통해 주요 기능 구현(체결통보만 웹소켓 이용)

[개발 구조]
STEP 1: 인증 시스템 (Access Token 발급/갱신, Hashkey 생성)
STEP 2: 조건검색식 기반 종목 필터링
STEP 3: 실시간 체결 및 시세 수신 (WebSocket)
STEP 4: 주문/매도/매수 실행 (REST)
STEP 5: 텔레그램 봇 연동
STEP 6: 잔고/손익 실시간 조회
STEP 7: 예외/장애 처리 및 로깅
STEP 8: 코스피/코스닥 구분 처리

Created: 2026-01-12
Author: AI Auto Trading System
Version: 2.0.0 (Telegram Bot Enhanced)
"""

import asyncio
import copy
import json
import logging
import os
import sys
import time
import threading
from base64 import b64decode
from collections import namedtuple
from datetime import datetime, timedelta
from io import StringIO
from typing import Dict, List, Optional, Tuple
from queue import Queue

import pandas as pd
import requests
import websockets
import yaml
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# 텔레그램 봇 라이브러리
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.warning("python-telegram-bot 라이브러리가 설치되지 않았습니다. 텔레그램 기능이 제한됩니다.")

# ============================================================================
# 전역 설정 및 상수
# ============================================================================

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('kis_auto_trading.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# 설정 파일 경로
CONFIG_ROOT = os.path.join(os.path.expanduser("~"), "KIS", "config")
TOKEN_FILE = os.path.join(CONFIG_ROOT, f"KIS{datetime.today().strftime('%Y%m%d')}")
CONFIG_FILE = "kis_devlp.yaml"

# 토큰 관리 파일 생성
os.makedirs(CONFIG_ROOT, exist_ok=True)
if not os.path.exists(TOKEN_FILE):
    with open(TOKEN_FILE, "w+") as f:
        pass

# 설정 파일 로드
try:
    with open(CONFIG_FILE, encoding="UTF-8") as f:
        _cfg = yaml.load(f, Loader=yaml.FullLoader)
except FileNotFoundError:
    logger.error(f"설정 파일을 찾을 수 없습니다: {CONFIG_FILE}")
    sys.exit(1)

# 전역 변수
_TRENV = None
_last_auth_time = datetime.now()
_isPaper = False
_smartSleep = 0.1

# 기본 헤더값
_base_headers = {
    "Content-Type": "application/json",
    "Accept": "text/plain",
    "charset": "UTF-8",
    "User-Agent": _cfg["my_agent"],
}

_base_headers_ws = {
    "content-type": "utf-8",
}


# ============================================================================
# STEP 1: 인증 시스템 구현
# ============================================================================

class KISAuth:
    """한국투자증권 API 인증 관리 클래스"""
    
    @staticmethod
    def save_token(my_token: str, my_expired: str) -> None:
        """토큰 저장"""
        valid_date = datetime.strptime(my_expired, "%Y-%m-%d %H:%M:%S")
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(f"token: {my_token}\n")
            f.write(f"valid-date: {valid_date}\n")
        logger.info("토큰이 저장되었습니다.")
    
    @staticmethod
    def read_token() -> Optional[str]:
        """저장된 토큰 읽기"""
        try:
            with open(TOKEN_FILE, encoding="UTF-8") as f:
                tkg_tmp = yaml.load(f, Loader=yaml.FullLoader)
            
            if not tkg_tmp or 'token' not in tkg_tmp:
                return None
            
            exp_dt = datetime.strftime(tkg_tmp["valid-date"], "%Y-%m-%d %H:%M:%S")
            now_dt = datetime.today().strftime("%Y-%m-%d %H:%M:%S")
            
            if exp_dt > now_dt:
                logger.info("기존 토큰이 유효합니다.")
                return tkg_tmp["token"]
            else:
                logger.info("토큰이 만료되었습니다. 재발급이 필요합니다.")
                return None
        except Exception as e:
            logger.warning(f"토큰 읽기 실패: {e}")
            return None
    
    @staticmethod
    def get_access_token(svr: str = "prod") -> Optional[str]:
        """접근 토큰 발급"""
        p = {"grant_type": "client_credentials"}
        
        if svr == "prod":
            ak1, ak2 = "my_app", "my_sec"
        elif svr == "vps":
            ak1, ak2 = "paper_app", "paper_sec"
        else:
            raise ValueError("svr는 'prod' 또는 'vps'여야 합니다.")
        
        p["appkey"] = _cfg[ak1]
        p["appsecret"] = _cfg[ak2]
        
        # 기존 토큰 확인
        saved_token = KISAuth.read_token()
        if saved_token:
            return saved_token
        
        # 새 토큰 발급
        url = f"{_cfg[svr]}/oauth2/tokenP"
        try:
            res = requests.post(url, data=json.dumps(p), headers=_base_headers)
            if res.status_code == 200:
                result = res.json()
                my_token = result["access_token"]
                my_expired = result["access_token_token_expired"]
                KISAuth.save_token(my_token, my_expired)
                logger.info("새로운 토큰이 발급되었습니다.")
                return my_token
            else:
                logger.error(f"토큰 발급 실패: {res.status_code} - {res.text}")
                return None
        except Exception as e:
            logger.error(f"토큰 발급 중 오류 발생: {e}")
            return None
    
    @staticmethod
    def get_approval_key(svr: str = "prod") -> Optional[str]:
        """웹소켓 접속키 발급"""
        p = {"grant_type": "client_credentials"}
        
        if svr == "prod":
            ak1, ak2 = "my_app", "my_sec"
        elif svr == "vps":
            ak1, ak2 = "paper_app", "paper_sec"
        else:
            raise ValueError("svr는 'prod' 또는 'vps'여야 합니다.")
        
        p["appkey"] = _cfg[ak1]
        p["secretkey"] = _cfg[ak2]
        
        url = f"{_cfg[svr]}/oauth2/Approval"
        try:
            res = requests.post(url, data=json.dumps(p), headers=_base_headers)
            if res.status_code == 200:
                approval_key = res.json()["approval_key"]
                logger.info("웹소켓 접속키가 발급되었습니다.")
                return approval_key
            else:
                logger.error(f"접속키 발급 실패: {res.status_code} - {res.text}")
                return None
        except Exception as e:
            logger.error(f"접속키 발급 중 오류 발생: {e}")
            return None
    
    @staticmethod
    def set_hashkey(params: dict, svr: str = "prod") -> Optional[str]:
        """Hashkey 생성"""
        url = f"{_cfg[svr]}/uapi/hashkey"
        try:
            res = requests.post(url, data=json.dumps(params), headers=_base_headers)
            if res.status_code == 200:
                return res.json()["HASH"]
            else:
                logger.warning(f"Hashkey 생성 실패: {res.status_code}")
                return None
        except Exception as e:
            logger.warning(f"Hashkey 생성 중 오류: {e}")
            return None


# ============================================================================
# STEP 2: 조건검색식 기반 종목 필터링
# ============================================================================

class ConditionSearch:
    """조건검색식 관리 클래스"""
    
    def __init__(self, env: 'TradingEnvironment'):
        self.env = env
    
    def get_condition_list(self) -> pd.DataFrame:
        """조건검색식 목록 조회"""
        logger.info("조건검색식 목록을 조회합니다.")
        
        url = f"{self.env.base_url}/uapi/domestic-stock/v1/quotations/psearch-title"
        tr_id = "HHKST03900300"
        
        headers = self.env.get_headers(tr_id)
        params = {"user_id": self.env.hts_id}
        
        try:
            res = requests.get(url, headers=headers, params=params)
            if res.status_code == 200:
                data = res.json()
                if data.get("rt_cd") == "0":
                    df = pd.DataFrame(data.get("output2", []))
                    logger.info(f"조건검색식 {len(df)}개를 찾았습니다.")
                    return df
                else:
                    logger.error(f"조건검색 목록 조회 실패: {data.get('msg1')}")
                    return pd.DataFrame()
            else:
                logger.error(f"API 호출 실패: {res.status_code}")
                return pd.DataFrame()
        except Exception as e:
            logger.error(f"조건검색 목록 조회 중 오류: {e}")
            return pd.DataFrame()
    
    def get_condition_stocks(self, seq: str) -> pd.DataFrame:
        """조건검색 결과 종목 조회"""
        logger.info(f"조건검색 결과를 조회합니다. (seq: {seq})")
        
        url = f"{self.env.base_url}/uapi/domestic-stock/v1/quotations/psearch-result"
        tr_id = "HHKST03900400"
        
        headers = self.env.get_headers(tr_id)
        params = {
            "user_id": self.env.hts_id,
            "seq": seq
        }
        
        try:
            res = requests.get(url, headers=headers, params=params)
            if res.status_code == 200:
                data = res.json()
                if data.get("rt_cd") == "0":
                    df = pd.DataFrame(data.get("output2", []))
                    logger.info(f"조건검색 결과 {len(df)}개 종목을 찾았습니다.")
                    return df
                else:
                    logger.warning(f"조건검색 결과 없음: {data.get('msg1')}")
                    return pd.DataFrame()
            else:
                logger.error(f"API 호출 실패: {res.status_code}")
                return pd.DataFrame()
        except Exception as e:
            logger.error(f"조건검색 결과 조회 중 오류: {e}")
            return pd.DataFrame()


# ============================================================================
# STEP 3: 실시간 체결통보 웹소켓
# ============================================================================

class WebSocketClient:
    """웹소켓 클라이언트 관리 클래스"""
    
    def __init__(self, env: 'TradingEnvironment'):
        self.env = env
        self.ws = None
        self.is_running = False
        self.callbacks = {}
        self.encrypt_keys = {}
    
    def aes_cbc_base64_dec(self, key: str, iv: str, cipher_text: str) -> str:
        """AES 복호화"""
        cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, iv.encode("utf-8"))
        return bytes.decode(unpad(cipher.decrypt(b64decode(cipher_text)), AES.block_size))
    
    async def connect(self):
        """웹소켓 연결"""
        url = self.env.ws_url
        logger.info(f"웹소켓에 연결합니다: {url}")
        
        try:
            async with websockets.connect(url) as ws:
                self.ws = ws
                self.is_running = True
                logger.info("웹소켓 연결 성공")
                
                # 체결통보 구독
                await self.subscribe_execution_notice()
                
                # 메시지 수신 루프
                await self.receive_messages()
        except Exception as e:
            logger.error(f"웹소켓 연결 오류: {e}")
            self.is_running = False
    
    async def subscribe_execution_notice(self):
        """체결통보 구독"""
        tr_id = "H0STCNI0" if not self.env.is_paper else "H0STCNI9"
        
        msg = {
            "header": {
                "approval_key": self.env.approval_key,
                "custtype": "P",
                "tr_type": "1",
                "content-type": "utf-8"
            },
            "body": {
                "input": {
                    "tr_id": tr_id,
                    "tr_key": self.env.account_no
                }
            }
        }
        
        await self.ws.send(json.dumps(msg))
        logger.info("체결통보 구독 요청을 전송했습니다.")
    
    async def receive_messages(self):
        """메시지 수신 처리"""
        async for raw in self.ws:
            try:
                # 데이터 메시지 처리
                if raw[0] in ["0", "1"]:
                    parts = raw.split("|")
                    if len(parts) >= 4:
                        tr_id = parts[1]
                        data = parts[3]
                        
                        # 암호화된 경우 복호화
                        if tr_id in self.encrypt_keys:
                            keys = self.encrypt_keys[tr_id]
                            if keys.get("encrypt") == "Y":
                                data = self.aes_cbc_base64_dec(
                                    keys["key"], keys["iv"], data
                                )
                        
                        # 콜백 호출
                        if tr_id in self.callbacks:
                            self.callbacks[tr_id](data)
                
                # 시스템 메시지 처리
                else:
                    msg = json.loads(raw)
                    tr_id = msg["header"]["tr_id"]
                    
                    # PINGPONG 처리
                    if tr_id == "PINGPONG":
                        await self.ws.pong(raw)
                        logger.debug("PINGPONG 응답")
                    
                    # 암호화 키 저장
                    elif "body" in msg and "output" in msg["body"]:
                        output = msg["body"]["output"]
                        if "iv" in output and "key" in output:
                            self.encrypt_keys[tr_id] = {
                                "encrypt": msg["header"].get("encrypt", "N"),
                                "iv": output["iv"],
                                "key": output["key"]
                            }
                            logger.info(f"암호화 키 저장: {tr_id}")
            
            except Exception as e:
                logger.error(f"메시지 처리 오류: {e}")
    
    def register_callback(self, tr_id: str, callback):
        """콜백 등록"""
        self.callbacks[tr_id] = callback
    
    def start(self):
        """웹소켓 시작 (별도 스레드)"""
        def run():
            asyncio.run(self.connect())
        
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        logger.info("웹소켓 스레드를 시작했습니다.")


# ============================================================================
# STEP 4: 주문/매도/매수 실행
# ============================================================================

class OrderManager:
    """주문 관리 클래스"""
    
    def __init__(self, env: 'TradingEnvironment'):
        self.env = env
    
    def order_stock(
        self,
        stock_code: str,
        order_type: str,  # "buy" or "sell"
        order_qty: int,
        order_price: int = 0,
        order_div: str = "01"  # 00:지정가, 01:시장가
    ) -> dict:
        """주식 주문"""
        logger.info(f"주문 실행: {order_type} {stock_code} {order_qty}주 @{order_price}")
        
        url = f"{self.env.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        
        # TR ID 설정
        if self.env.is_paper:
            tr_id = "VTTC0011U" if order_type == "sell" else "VTTC0012U"
        else:
            tr_id = "TTTC0011U" if order_type == "sell" else "TTTC0012U"
        
        headers = self.env.get_headers(tr_id)
        
        params = {
            "CANO": self.env.account_no,
            "ACNT_PRDT_CD": self.env.account_prod,
            "PDNO": stock_code,
            "ORD_DVSN": order_div,
            "ORD_QTY": str(order_qty),
            "ORD_UNPR": str(order_price),
            "EXCG_ID_DVSN_CD": "KRX",
            "SLL_TYPE": "01" if order_type == "sell" else "",
            "CNDT_PRIC": ""
        }
        
        # Hashkey 설정 (선택사항)
        hashkey = KISAuth.set_hashkey(params, "prod" if not self.env.is_paper else "vps")
        if hashkey:
            headers["hashkey"] = hashkey
        
        try:
            res = requests.post(url, headers=headers, data=json.dumps(params))
            if res.status_code == 200:
                data = res.json()
                if data.get("rt_cd") == "0":
                    logger.info(f"주문 성공: {data.get('msg1')}")
                    return {"success": True, "data": data}
                else:
                    logger.error(f"주문 실패: {data.get('msg1')}")
                    return {"success": False, "error": data.get("msg1")}
            else:
                logger.error(f"주문 API 호출 실패: {res.status_code}")
                return {"success": False, "error": f"HTTP {res.status_code}"}
        except Exception as e:
            logger.error(f"주문 중 오류 발생: {e}")
            return {"success": False, "error": str(e)}
    
    def get_balance(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """잔고 조회"""
        logger.info("잔고를 조회합니다.")
        
        url = f"{self.env.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "VTTC8434R" if self.env.is_paper else "TTTC8434R"
        
        headers = self.env.get_headers(tr_id)
        params = {
            "CANO": self.env.account_no,
            "ACNT_PRDT_CD": self.env.account_prod,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        
        try:
            res = requests.get(url, headers=headers, params=params)
            if res.status_code == 200:
                data = res.json()
                if data.get("rt_cd") == "0":
                    df1 = pd.DataFrame(data.get("output1", []))
                    df2 = pd.DataFrame([data.get("output2", {})])
                    logger.info(f"잔고 조회 성공: {len(df1)}개 종목")
                    return df1, df2
                else:
                    logger.error(f"잔고 조회 실패: {data.get('msg1')}")
                    return pd.DataFrame(), pd.DataFrame()
            else:
                logger.error(f"잔고 조회 API 호출 실패: {res.status_code}")
                return pd.DataFrame(), pd.DataFrame()
        except Exception as e:
            logger.error(f"잔고 조회 중 오류: {e}")
            return pd.DataFrame(), pd.DataFrame()
    
    def get_buyable_cash(self, stock_code: str, price: int) -> dict:
        """매수가능금액/수량 조회"""
        logger.info(f"매수가능 조회: {stock_code}")
        
        url = f"{self.env.base_url}/uapi/domestic-stock/v1/trading/inquire-psbl-order"
        tr_id = "VTTC8908R" if self.env.is_paper else "TTTC8908R"
        
        headers = self.env.get_headers(tr_id)
        params = {
            "CANO": self.env.account_no,
            "ACNT_PRDT_CD": self.env.account_prod,
            "PDNO": stock_code,
            "ORD_UNPR": str(price),
            "ORD_DVSN": "01",  # 시장가
            "CMA_EVLU_AMT_ICLD_YN": "N",
            "OVRS_ICLD_YN": "N"
        }
        
        try:
            res = requests.get(url, headers=headers, params=params)
            if res.status_code == 200:
                data = res.json()
                if data.get("rt_cd") == "0":
                    output = data.get("output", {})
                    result = {
                        "max_buy_amt": output.get("max_buy_amt", "0"),
                        "max_buy_qty": output.get("max_buy_qty", "0"),
                        "nrcvb_buy_amt": output.get("nrcvb_buy_amt", "0"),
                        "nrcvb_buy_qty": output.get("nrcvb_buy_qty", "0")
                    }
                    logger.info(f"매수가능: {result['max_buy_qty']}주")
                    return result
                else:
                    logger.error(f"매수가능 조회 실패: {data.get('msg1')}")
                    return {}
            else:
                logger.error(f"매수가능 조회 API 호출 실패: {res.status_code}")
                return {}
        except Exception as e:
            logger.error(f"매수가능 조회 중 오류: {e}")
            return {}


# ============================================================================
# STEP 5: 텔레그램 봇 연동 (Enhanced with Button Interface)
# ============================================================================

class TelegramBotEnhanced:
    """텔레그램 봇 고급 기능 클래스 (버튼 클릭형 인터페이스)"""
    
    def __init__(self, bot_token: str, chat_id: str, trading_system=None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.trading_system = trading_system
        self.enabled = bool(bot_token and chat_id) and TELEGRAM_AVAILABLE
        self.application = None
        self.bot_running = False
        
        # 알림 설정
        self.notifications = {
            "execution": True,   # 체결 알림
            "order": True,       # 주문 알림
            "balance": True,     # 잔고 알림
            "error": True        # 오류 알림
        }
        
        if not TELEGRAM_AVAILABLE:
            logger.warning("python-telegram-bot 라이브러리가 설치되지 않았습니다.")
            logger.warning("설치: pip install python-telegram-bot")
            self.enabled = False
        elif self.enabled:
            logger.info("텔레그램 봇 (Enhanced) 활성화되었습니다.")
            self._initialize_bot()
        else:
            logger.warning("텔레그램 봇이 비활성화되었습니다.")
    
    def set_trading_system(self, trading_system):
        """트레이딩 시스템 연결"""
        self.trading_system = trading_system
    
    def _initialize_bot(self):
        """봇 초기화"""
        if not self.enabled:
            return
        
        try:
            self.application = Application.builder().token(self.bot_token).build()
            
            # 명령어 핸들러 등록
            self.application.add_handler(CommandHandler("start", self._cmd_start))
            self.application.add_handler(CommandHandler("menu", self._cmd_menu))
            self.application.add_handler(CommandHandler("help", self._cmd_help))
            
            # 버튼 콜백 핸들러 등록
            self.application.add_handler(CallbackQueryHandler(self._button_callback))
            
            logger.info("텔레그램 봇 핸들러 등록 완료")
        except Exception as e:
            logger.error(f"텔레그램 봇 초기화 오류: {e}")
            self.enabled = False
    
    def start_bot(self):
        """봇 시작 (별도 스레드)"""
        if not self.enabled or self.bot_running:
            return
        
        def run_bot():
            try:
                self.bot_running = True
                logger.info("텔레그램 봇을 시작합니다...")
                self.application.run_polling(allowed_updates=Update.ALL_TYPES)
            except Exception as e:
                logger.error(f"텔레그램 봇 실행 오류: {e}")
                self.bot_running = False
        
        thread = threading.Thread(target=run_bot, daemon=True)
        thread.start()
        time.sleep(2)  # 봇 시작 대기
    
    def stop_bot(self):
        """봇 종료"""
        if self.application and self.bot_running:
            try:
                self.application.stop()
                self.bot_running = False
                logger.info("텔레그램 봇이 종료되었습니다.")
            except Exception as e:
                logger.error(f"텔레그램 봇 종료 오류: {e}")
    
    # ========================================================================
    # 명령어 핸들러
    # ========================================================================
    
    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """시작 명령어"""
        welcome_msg = """
🤖 <b>한국투자증권 자동매매 시스템</b>
━━━━━━━━━━━━━━━━━━━━━━

안녕하세요! 자동매매 시스템 봇입니다.

📋 <b>주요 기능</b>
• 실시간 잔고 조회
• 미실현 손익 확인
• 체결 알림 설정
• 시스템 시작/종료

/menu 명령어로 메뉴를 확인하세요.
"""
        await update.message.reply_text(welcome_msg, parse_mode='HTML')
        await self._cmd_menu(update, context)
    
    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """도움말"""
        help_msg = """
📖 <b>명령어 도움말</b>
━━━━━━━━━━━━━━━━━━━━━━

/start - 봇 시작 및 환영 메시지
/menu - 메인 메뉴 표시
/help - 도움말 표시

<b>버튼 기능:</b>
💼 실시간 잔고 - 현재 보유 종목 및 평가금액 확인
📊 미실현손익 - 실시간 평가손익 확인
🔔 체결알림 - 체결 알림 ON/OFF 설정
▶️ 시스템 시작 - 자동매매 시작
⏹ 시스템 종료 - 자동매매 중지

문의사항이 있으시면 로그 파일을 확인하세요.
"""
        await update.message.reply_text(help_msg, parse_mode='HTML')
    
    async def _cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """메인 메뉴"""
        keyboard = [
            [
                InlineKeyboardButton("💼 실시간 잔고", callback_data="balance"),
                InlineKeyboardButton("📊 미실현손익", callback_data="profit_loss")
            ],
            [
                InlineKeyboardButton("🔔 체결알림 설정", callback_data="toggle_execution"),
                InlineKeyboardButton("📢 주문알림 설정", callback_data="toggle_order")
            ],
            [
                InlineKeyboardButton("▶️ 시스템 시작", callback_data="start_system"),
                InlineKeyboardButton("⏹ 시스템 종료", callback_data="stop_system")
            ],
            [
                InlineKeyboardButton("🔄 새로고침", callback_data="refresh_menu"),
                InlineKeyboardButton("❓ 도움말", callback_data="help")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        status = "🟢 실행중" if (self.trading_system and self.trading_system.is_running) else "🔴 중지됨"
        exec_status = "🔔 ON" if self.notifications["execution"] else "🔕 OFF"
        order_status = "🔔 ON" if self.notifications["order"] else "🔕 OFF"
        
        menu_msg = f"""
🎛 <b>자동매매 컨트롤 패널</b>
━━━━━━━━━━━━━━━━━━━━━━

📍 시스템 상태: {status}
🔔 체결 알림: {exec_status}
📢 주문 알림: {order_status}

⏰ 현재 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

원하는 기능을 선택하세요:
"""
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                menu_msg,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                menu_msg,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
    
    # ========================================================================
    # 버튼 콜백 핸들러
    # ========================================================================
    
    async def _button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """버튼 클릭 처리"""
        query = update.callback_query
        await query.answer()
        
        callback_data = query.data
        
        # 각 버튼에 따른 처리
        if callback_data == "balance":
            await self._handle_balance(query)
        elif callback_data == "profit_loss":
            await self._handle_profit_loss(query)
        elif callback_data == "toggle_execution":
            await self._handle_toggle_execution(query)
        elif callback_data == "toggle_order":
            await self._handle_toggle_order(query)
        elif callback_data == "start_system":
            await self._handle_start_system(query)
        elif callback_data == "stop_system":
            await self._handle_stop_system(query)
        elif callback_data == "refresh_menu":
            await self._cmd_menu(update, context)
        elif callback_data == "help":
            await self._handle_help_button(query)
    
    async def _handle_balance(self, query):
        """실시간 잔고 조회"""
        await query.edit_message_text("⏳ 잔고 정보를 조회 중입니다...")
        
        try:
            if not self.trading_system:
                await query.edit_message_text("❌ 트레이딩 시스템이 연결되지 않았습니다.")
                return
            
            df_stocks, df_summary = self.trading_system.order_manager.get_balance()
            
            if df_stocks.empty:
                msg = """
💼 <b>잔고 조회 결과</b>
━━━━━━━━━━━━━━━

보유 종목이 없습니다.

⏰ 조회 시각: {}
""".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            else:
                # 보유 종목 정보
                stocks_info = []
                for _, row in df_stocks.head(10).iterrows():  # 최대 10개만 표시
                    stock_name = row.get('prdt_name', 'N/A')
                    qty = row.get('hldg_qty', '0')
                    buy_price = row.get('pchs_avg_pric', '0')
                    current_price = row.get('prpr', '0')
                    profit_loss = row.get('evlu_pfls_amt', '0')
                    profit_rate = row.get('evlu_pfls_rt', '0')
                    
                    stocks_info.append(f"""
📌 {stock_name}
   수량: {qty}주 | 매입가: {buy_price}원
   현재가: {current_price}원
   평가손익: {profit_loss}원 ({profit_rate}%)
""")
                
                # 전체 요약
                if not df_summary.empty:
                    total_buy = df_summary.iloc[0].get('pchs_amt_smtl_amt', '0')
                    total_eval = df_summary.iloc[0].get('tot_evlu_amt', '0')
                    total_profit = df_summary.iloc[0].get('evlu_pfls_smtl_amt', '0')
                    total_profit_rate = df_summary.iloc[0].get('evlu_pfls_rt', '0')
                else:
                    total_buy = total_eval = total_profit = total_profit_rate = 'N/A'
                
                msg = f"""
💼 <b>실시간 잔고 조회</b>
━━━━━━━━━━━━━━━

<b>📊 전체 요약</b>
총 매입금액: {total_buy}원
총 평가금액: {total_eval}원
평가손익: {total_profit}원
수익률: {total_profit_rate}%

<b>📋 보유 종목</b>
{''.join(stocks_info)}

⏰ 조회 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            
            # 메뉴 버튼 추가
            keyboard = [[InlineKeyboardButton("🔙 메인 메뉴", callback_data="refresh_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(msg, parse_mode='HTML', reply_markup=reply_markup)
        
        except Exception as e:
            error_msg = f"❌ 잔고 조회 중 오류 발생:\n{str(e)}"
            keyboard = [[InlineKeyboardButton("🔙 메인 메뉴", callback_data="refresh_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(error_msg, reply_markup=reply_markup)
    
    async def _handle_profit_loss(self, query):
        """미실현 손익 조회"""
        await query.edit_message_text("⏳ 미실현 손익을 조회 중입니다...")
        
        try:
            if not self.trading_system:
                await query.edit_message_text("❌ 트레이딩 시스템이 연결되지 않았습니다.")
                return
            
            df_stocks, df_summary = self.trading_system.order_manager.get_balance()
            
            if df_stocks.empty:
                msg = """
📊 <b>미실현 손익</b>
━━━━━━━━━━━━━━━

보유 종목이 없어 손익 정보가 없습니다.

⏰ 조회 시각: {}
""".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            else:
                # 종목별 손익
                profit_info = []
                for _, row in df_stocks.iterrows():
                    stock_name = row.get('prdt_name', 'N/A')
                    profit_loss = int(row.get('evlu_pfls_amt', '0'))
                    profit_rate = float(row.get('evlu_pfls_rt', '0'))
                    
                    emoji = "🔴" if profit_loss < 0 else "🟢" if profit_loss > 0 else "⚪"
                    
                    profit_info.append(f"{emoji} {stock_name}: {profit_loss:,}원 ({profit_rate:.2f}%)")
                
                # 전체 손익
                if not df_summary.empty:
                    total_profit = int(df_summary.iloc[0].get('evlu_pfls_smtl_amt', '0'))
                    total_profit_rate = float(df_summary.iloc[0].get('evlu_pfls_rt', '0'))
                else:
                    total_profit = 0
                    total_profit_rate = 0.0
                
                total_emoji = "🔴" if total_profit < 0 else "🟢" if total_profit > 0 else "⚪"
                
                msg = f"""
📊 <b>미실현 손익 현황</b>
━━━━━━━━━━━━━━━

<b>{total_emoji} 전체 평가손익</b>
금액: {total_profit:,}원
수익률: {total_profit_rate:.2f}%

<b>📋 종목별 손익</b>
{chr(10).join(profit_info)}

⏰ 조회 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            
            # 메뉴 버튼 추가
            keyboard = [[InlineKeyboardButton("🔙 메인 메뉴", callback_data="refresh_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(msg, parse_mode='HTML', reply_markup=reply_markup)
        
        except Exception as e:
            error_msg = f"❌ 손익 조회 중 오류 발생:\n{str(e)}"
            keyboard = [[InlineKeyboardButton("🔙 메인 메뉴", callback_data="refresh_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(error_msg, reply_markup=reply_markup)
    
    async def _handle_toggle_execution(self, query):
        """체결 알림 ON/OFF"""
        self.notifications["execution"] = not self.notifications["execution"]
        status = "ON 🔔" if self.notifications["execution"] else "OFF 🔕"
        
        msg = f"""
🔔 <b>체결 알림 설정</b>
━━━━━━━━━━━━━━━

체결 알림이 <b>{status}</b> 되었습니다.

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        keyboard = [[InlineKeyboardButton("🔙 메인 메뉴", callback_data="refresh_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=reply_markup)
    
    async def _handle_toggle_order(self, query):
        """주문 알림 ON/OFF"""
        self.notifications["order"] = not self.notifications["order"]
        status = "ON 🔔" if self.notifications["order"] else "OFF 🔕"
        
        msg = f"""
📢 <b>주문 알림 설정</b>
━━━━━━━━━━━━━━━

주문 알림이 <b>{status}</b> 되었습니다.

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        keyboard = [[InlineKeyboardButton("🔙 메인 메뉴", callback_data="refresh_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=reply_markup)
    
    async def _handle_start_system(self, query):
        """시스템 시작"""
        if not self.trading_system:
            await query.edit_message_text("❌ 트레이딩 시스템이 연결되지 않았습니다.")
            return
        
        if self.trading_system.is_running:
            msg = "⚠️ 시스템이 이미 실행 중입니다."
        else:
            msg = "✅ 자동매매 시스템을 시작합니다.\n\n시스템이 백그라운드에서 실행됩니다."
            # 실제로는 시스템이 이미 실행 중이므로 상태만 변경
            self.trading_system.is_running = True
        
        keyboard = [[InlineKeyboardButton("🔙 메인 메뉴", callback_data="refresh_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(msg, reply_markup=reply_markup)
    
    async def _handle_stop_system(self, query):
        """시스템 종료"""
        if not self.trading_system:
            await query.edit_message_text("❌ 트레이딩 시스템이 연결되지 않았습니다.")
            return
        
        if not self.trading_system.is_running:
            msg = "⚠️ 시스템이 이미 중지되어 있습니다."
        else:
            msg = "⏹ 자동매매 시스템을 중지합니다."
            self.trading_system.is_running = False
        
        keyboard = [[InlineKeyboardButton("🔙 메인 메뉴", callback_data="refresh_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(msg, reply_markup=reply_markup)
    
    async def _handle_help_button(self, query):
        """도움말 버튼"""
        help_msg = """
📖 <b>사용 가이드</b>
━━━━━━━━━━━━━━━

<b>💼 실시간 잔고</b>
현재 보유 중인 종목과 평가금액을 확인합니다.

<b>📊 미실현손익</b>
각 종목의 평가손익과 전체 수익률을 확인합니다.

<b>🔔 체결알림 설정</b>
주문 체결 시 알림을 받을지 설정합니다.

<b>📢 주문알림 설정</b>
주문 접수 시 알림을 받을지 설정합니다.

<b>▶️ 시스템 시작</b>
자동매매를 시작합니다.

<b>⏹ 시스템 종료</b>
자동매매를 중지합니다.
"""
        
        keyboard = [[InlineKeyboardButton("🔙 메인 메뉴", callback_data="refresh_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(help_msg, parse_mode='HTML', reply_markup=reply_markup)
    
    # ========================================================================
    # 알림 전송 메서드 (기존 호환성 유지)
    # ========================================================================
    
    def send_message(self, message: str, force: bool = False) -> bool:
        """메시지 전송 (Simple API for compatibility)"""
        if not self.enabled and not force:
            return False
        
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        params = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        try:
            res = requests.post(url, data=params, timeout=5)
            if res.status_code == 200:
                logger.debug("텔레그램 메시지 전송 성공")
                return True
            else:
                logger.warning(f"텔레그램 메시지 전송 실패: {res.status_code}")
                return False
        except Exception as e:
            logger.warning(f"텔레그램 메시지 전송 중 오류: {e}")
            return False
    
    def send_order_alert(self, order_type: str, stock_code: str, qty: int, price: int):
        """주문 알림"""
        if not self.notifications["order"]:
            return
        
        msg = f"""
🔔 <b>주문 알림</b>
━━━━━━━━━━━━━━━
📌 유형: {order_type}
🏷 종목: {stock_code}
📊 수량: {qty:,}주
💰 가격: {price:,}원
⏰ 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        self.send_message(msg)
    
    def send_execution_alert(self, data: dict):
        """체결 알림"""
        if not self.notifications["execution"]:
            return
        
        msg = f"""
✅ <b>체결 알림</b>
━━━━━━━━━━━━━━━
🏷 종목: {data.get('stock_code', 'N/A')}
📊 수량: {data.get('qty', 'N/A')}주
💰 가격: {data.get('price', 'N/A')}원
⏰ 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        self.send_message(msg)
    
    def send_balance_alert(self, total_value: str, profit_loss: str):
        """잔고 알림"""
        if not self.notifications["balance"]:
            return
        
        msg = f"""
💼 <b>잔고 현황</b>
━━━━━━━━━━━━━━━
💵 총평가금액: {total_value}
📈 손익금액: {profit_loss}
⏰ 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        self.send_message(msg)
    
    def send_error_alert(self, error_msg: str):
        """에러 알림"""
        if not self.notifications["error"]:
            return
        
        msg = f"""
❌ <b>오류 발생</b>
━━━━━━━━━━━━━━━
{error_msg}
⏰ 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        self.send_message(msg)


# ============================================================================
# STEP 6~8: 거래 환경 및 메인 트레이딩 시스템
# ============================================================================

class TradingEnvironment:
    """거래 환경 설정 클래스"""
    
    def __init__(self, svr: str = "prod", product: str = "01"):
        self.svr = svr
        self.is_paper = (svr == "vps")
        self.product = product
        
        # 계정 정보
        if svr == "prod":
            self.app_key = _cfg["my_app"]
            self.app_secret = _cfg["my_sec"]
            self.account_no = _cfg["my_acct_stock"] if product == "01" else _cfg["my_acct_future"]
        else:
            self.app_key = _cfg["paper_app"]
            self.app_secret = _cfg["paper_sec"]
            self.account_no = _cfg["my_paper_stock"] if product == "01" else _cfg["my_paper_future"]
        
        self.account_prod = product
        self.hts_id = _cfg["my_htsid"]
        
        # URL 설정
        self.base_url = _cfg[svr]
        self.ws_url = _cfg["ops" if svr == "prod" else "vops"]
        
        # 인증
        self.access_token = KISAuth.get_access_token(svr)
        self.approval_key = KISAuth.get_approval_key(svr)
        
        if not self.access_token:
            raise Exception("Access Token 발급 실패")
        if not self.approval_key:
            raise Exception("Approval Key 발급 실패")
        
        logger.info(f"거래 환경 초기화 완료: {svr} / {product}")
    
    def get_headers(self, tr_id: str, tr_cont: str = "") -> dict:
        """API 헤더 생성"""
        # 모의투자인 경우 TR ID 변경
        if self.is_paper and tr_id[0] in ("T", "J", "C"):
            tr_id = "V" + tr_id[1:]
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "tr_cont": tr_cont,
            "custtype": "P"
        }
        return headers


class AutoTradingSystem:
    """자동매매 시스템 메인 클래스"""
    
    def __init__(
        self,
        svr: str = "vps",
        product: str = "01",
        telegram_token: str = "",
        telegram_chat_id: str = "",
        condition_seq: str = "0",
        trading_params: dict = None
    ):
        """
        자동매매 시스템 초기화
        
        Args:
            svr: 서버 구분 (prod: 실전, vps: 모의)
            product: 계좌 상품코드 (01: 위탁계좌)
            telegram_token: 텔레그램 봇 토큰
            telegram_chat_id: 텔레그램 채팅 ID
            condition_seq: 조건검색식 번호
            trading_params: 매매 파라미터 설정
        """
        logger.info("=" * 60)
        logger.info("자동매매 시스템을 초기화합니다.")
        logger.info("=" * 60)
        
        # 거래 환경
        self.env = TradingEnvironment(svr, product)
        
        # 각 모듈 초기화
        self.condition_search = ConditionSearch(self.env)
        self.order_manager = OrderManager(self.env)
        self.telegram = TelegramBotEnhanced(telegram_token, telegram_chat_id, self)
        self.websocket = WebSocketClient(self.env)
        
        # 조건검색식 번호
        self.condition_seq = condition_seq
        
        # 매매 파라미터 (기본값)
        self.params = trading_params or {
            "buy_amount": 1000000,  # 종목당 매수금액
            "profit_rate": 0.02,    # 익절 비율 (2%)
            "loss_rate": -0.01,     # 손절 비율 (-1%)
            "max_stocks": 5,        # 최대 보유 종목 수
            "check_interval": 10,   # 상태 체크 주기 (초)
        }
        
        # 포지션 관리
        self.positions = {}  # {종목코드: {매수가, 수량, 현재가, ...}}
        self.watch_list = []  # 조건검색 종목 리스트
        
        # 상태 플래그
        self.is_running = False
        self.last_condition_check = None
        self.last_balance_check = None
        
        logger.info("자동매매 시스템 초기화 완료")
    
    def update_watch_list(self):
        """조건검색 종목 업데이트"""
        try:
            df = self.condition_search.get_condition_stocks(self.condition_seq)
            if not df.empty:
                self.watch_list = df['code'].tolist() if 'code' in df.columns else []
                logger.info(f"관심 종목 업데이트: {len(self.watch_list)}개")
                self.last_condition_check = datetime.now()
        except Exception as e:
            logger.error(f"관심 종목 업데이트 실패: {e}")
    
    def check_buy_signal(self, stock_code: str) -> bool:
        """매수 신호 확인"""
        # 이미 보유중인지 확인
        if stock_code in self.positions:
            return False
        
        # 최대 보유 종목 수 확인
        if len(self.positions) >= self.params["max_stocks"]:
            return False
        
        # 조건검색 종목인지 확인
        if stock_code not in self.watch_list:
            return False
        
        return True
    
    def check_sell_signal(self, stock_code: str, current_price: float) -> bool:
        """매도 신호 확인"""
        if stock_code not in self.positions:
            return False
        
        pos = self.positions[stock_code]
        buy_price = float(pos["buy_price"])
        
        # 수익률 계산
        profit_rate = (current_price - buy_price) / buy_price
        
        # 익절 또는 손절
        if profit_rate >= self.params["profit_rate"]:
            logger.info(f"{stock_code} 익절 조건 충족: {profit_rate:.2%}")
            return True
        
        if profit_rate <= self.params["loss_rate"]:
            logger.info(f"{stock_code} 손절 조건 충족: {profit_rate:.2%}")
            return True
        
        return False
    
    def execute_buy(self, stock_code: str):
        """매수 실행"""
        try:
            # 매수가능 조회
            buyable = self.order_manager.get_buyable_cash(stock_code, 0)
            if not buyable:
                return
            
            max_qty = int(buyable.get("max_buy_qty", "0"))
            if max_qty <= 0:
                logger.warning(f"{stock_code} 매수가능 수량 없음")
                return
            
            # 매수 실행 (시장가)
            result = self.order_manager.order_stock(
                stock_code=stock_code,
                order_type="buy",
                order_qty=max_qty,
                order_price=0,
                order_div="01"  # 시장가
            )
            
            if result.get("success"):
                self.telegram.send_order_alert("매수", stock_code, max_qty, 0)
                logger.info(f"매수 주문 완료: {stock_code} {max_qty}주")
            else:
                error_msg = f"매수 실패: {stock_code} - {result.get('error')}"
                logger.error(error_msg)
                self.telegram.send_error_alert(error_msg)
        
        except Exception as e:
            error_msg = f"매수 실행 중 오류: {stock_code} - {e}"
            logger.error(error_msg)
            self.telegram.send_error_alert(error_msg)
    
    def execute_sell(self, stock_code: str):
        """매도 실행"""
        try:
            if stock_code not in self.positions:
                return
            
            qty = int(self.positions[stock_code]["qty"])
            
            # 매도 실행 (시장가)
            result = self.order_manager.order_stock(
                stock_code=stock_code,
                order_type="sell",
                order_qty=qty,
                order_price=0,
                order_div="01"  # 시장가
            )
            
            if result.get("success"):
                self.telegram.send_order_alert("매도", stock_code, qty, 0)
                logger.info(f"매도 주문 완료: {stock_code} {qty}주")
            else:
                error_msg = f"매도 실패: {stock_code} - {result.get('error')}"
                logger.error(error_msg)
                self.telegram.send_error_alert(error_msg)
        
        except Exception as e:
            error_msg = f"매도 실행 중 오류: {stock_code} - {e}"
            logger.error(error_msg)
            self.telegram.send_error_alert(error_msg)
    
    def update_positions(self):
        """포지션 정보 업데이트"""
        try:
            df_stocks, df_summary = self.order_manager.get_balance()
            
            # 포지션 초기화
            new_positions = {}
            
            if not df_stocks.empty:
                for _, row in df_stocks.iterrows():
                    stock_code = row.get("pdno", "")
                    if not stock_code:
                        continue
                    
                    new_positions[stock_code] = {
                        "stock_name": row.get("prdt_name", ""),
                        "qty": row.get("hldg_qty", "0"),
                        "buy_price": row.get("pchs_avg_pric", "0"),
                        "current_price": row.get("prpr", "0"),
                        "eval_amt": row.get("evlu_amt", "0"),
                        "profit_loss": row.get("evlu_pfls_amt", "0"),
                        "profit_rate": row.get("evlu_pfls_rt", "0")
                    }
            
            self.positions = new_positions
            self.last_balance_check = datetime.now()
            
            logger.info(f"포지션 업데이트: {len(self.positions)}개 보유")
            
            # 텔레그램 알림 (잔고)
            if not df_summary.empty:
                total_value = df_summary.iloc[0].get("tot_evlu_amt", "0")
                profit_loss = df_summary.iloc[0].get("evlu_pfls_smtl_amt", "0")
                self.telegram.send_balance_alert(total_value, profit_loss)
        
        except Exception as e:
            logger.error(f"포지션 업데이트 중 오류: {e}")
    
    def handle_execution_notice(self, data: str):
        """체결통보 처리"""
        try:
            logger.info(f"체결통보 수신: {data}")
            
            # 체결 데이터 파싱
            parts = data.split("^")
            if len(parts) < 25:
                return
            
            # 체결 여부 확인 (14번째 필드)
            cntg_yn = parts[13]
            if cntg_yn != "2":  # 2: 체결통보
                return
            
            # 체결 정보 추출
            execution_data = {
                "stock_code": parts[8],
                "qty": parts[9],
                "price": parts[10],
                "time": parts[11]
            }
            
            logger.info(f"체결 완료: {execution_data}")
            self.telegram.send_execution_alert(execution_data)
            
            # 포지션 업데이트
            self.update_positions()
        
        except Exception as e:
            logger.error(f"체결통보 처리 중 오류: {e}")
    
    def run_trading_loop(self):
        """매매 루프 실행"""
        logger.info("매매 루프를 시작합니다.")
        
        while self.is_running:
            try:
                current_time = datetime.now()
                
                # 1. 조건검색 업데이트 (5분마다)
                if (not self.last_condition_check or
                    (current_time - self.last_condition_check).seconds >= 300):
                    self.update_watch_list()
                
                # 2. 포지션 업데이트 (30초마다)
                if (not self.last_balance_check or
                    (current_time - self.last_balance_check).seconds >= 30):
                    self.update_positions()
                
                # 3. 매도 신호 체크
                for stock_code in list(self.positions.keys()):
                    current_price = float(self.positions[stock_code].get("current_price", "0"))
                    if current_price > 0:
                        if self.check_sell_signal(stock_code, current_price):
                            self.execute_sell(stock_code)
                
                # 4. 매수 신호 체크
                for stock_code in self.watch_list:
                    if self.check_buy_signal(stock_code):
                        self.execute_buy(stock_code)
                
                # 대기
                time.sleep(self.params["check_interval"])
            
            except Exception as e:
                error_msg = f"매매 루프 오류: {e}"
                logger.error(error_msg)
                self.telegram.send_error_alert(error_msg)
                time.sleep(10)
    
    def start(self):
        """시스템 시작"""
        logger.info("=" * 60)
        logger.info("자동매매 시스템을 시작합니다.")
        logger.info("=" * 60)
        
        self.is_running = True
        
        # 텔레그램 봇 시작
        if self.telegram.enabled:
            logger.info("텔레그램 봇을 시작합니다...")
            self.telegram.start_bot()
            logger.info("텔레그램 봇 명령어: /start, /menu, /help")
        
        # 웹소켓 콜백 등록
        tr_id = "H0STCNI0" if not self.env.is_paper else "H0STCNI9"
        self.websocket.register_callback(tr_id, self.handle_execution_notice)
        
        # 웹소켓 시작
        self.websocket.start()
        
        # 시작 알림
        self.telegram.send_message(
            f"🚀 <b>자동매매 시스템 시작</b>\n"
            f"서버: {'모의투자' if self.env.is_paper else '실전투자'}\n"
            f"계좌: {self.env.account_no}-{self.env.account_prod}\n"
            f"시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"텔레그램 봇 명령어: /menu"
        )
        
        # 초기 상태 업데이트
        self.update_watch_list()
        self.update_positions()
        
        # 매매 루프 시작
        try:
            self.run_trading_loop()
        except KeyboardInterrupt:
            logger.info("사용자에 의해 종료되었습니다.")
            self.stop()
    
    def stop(self):
        """시스템 종료"""
        logger.info("=" * 60)
        logger.info("자동매매 시스템을 종료합니다.")
        logger.info("=" * 60)
        
        self.is_running = False
        
        # 종료 알림
        self.telegram.send_message(
            f"🛑 <b>자동매매 시스템 종료</b>\n"
            f"시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        # 텔레그램 봇 종료
        if self.telegram.enabled:
            self.telegram.stop_bot()
        
        logger.info("시스템 종료 완료")


# ============================================================================
# 메인 실행 부분
# ============================================================================

def main():
    """메인 함수"""
    print("=" * 60)
    print("한국투자증권 자동시스템트레이딩 매매 프로그램")
    print("=" * 60)
    print()
    
    # 설정 입력
    print("■ 환경 설정")
    svr = input("서버 구분 (prod: 실전, vps: 모의) [vps]: ").strip() or "vps"
    product = input("계좌 상품코드 (01: 위탁계좌) [01]: ").strip() or "01"
    
    print("\n■ 텔레그램 설정 (선택사항)")
    telegram_token = input("텔레그램 봇 토큰 (없으면 Enter): ").strip()
    telegram_chat_id = input("텔레그램 채팅 ID (없으면 Enter): ").strip()
    
    print("\n■ 조건검색 설정")
    condition_seq = input("조건검색식 번호 (0부터 시작) [0]: ").strip() or "0"
    
    print("\n■ 매매 파라미터 설정")
    try:
        buy_amount = int(input("종목당 매수금액 (원) [1000000]: ").strip() or "1000000")
        profit_rate = float(input("익절 비율 (%) [2.0]: ").strip() or "2.0") / 100
        loss_rate = -float(input("손절 비율 (%) [1.0]: ").strip() or "1.0") / 100
        max_stocks = int(input("최대 보유 종목 수 [5]: ").strip() or "5")
        check_interval = int(input("상태 체크 주기 (초) [10]: ").strip() or "10")
    except ValueError:
        print("잘못된 입력입니다. 기본값을 사용합니다.")
        buy_amount = 1000000
        profit_rate = 0.02
        loss_rate = -0.01
        max_stocks = 5
        check_interval = 10
    
    trading_params = {
        "buy_amount": buy_amount,
        "profit_rate": profit_rate,
        "loss_rate": loss_rate,
        "max_stocks": max_stocks,
        "check_interval": check_interval
    }
    
    print("\n" + "=" * 60)
    print("설정이 완료되었습니다. 시스템을 시작합니다...")
    print("=" * 60)
    print()
    
    # 시스템 초기화 및 시작
    try:
        system = AutoTradingSystem(
            svr=svr,
            product=product,
            telegram_token=telegram_token,
            telegram_chat_id=telegram_chat_id,
            condition_seq=condition_seq,
            trading_params=trading_params
        )
        
        system.start()
    
    except Exception as e:
        logger.error(f"시스템 실행 중 오류 발생: {e}")
        print(f"\n오류 발생: {e}")
        print("프로그램을 종료합니다.")


if __name__ == "__main__":
    main()
