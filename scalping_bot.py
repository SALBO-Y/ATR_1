#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
한국투자증권 스캘핑 자동매매 봇 (Simple Version)
- 단순하고 실용적인 접근
- 텔레그램 봇으로 모든 제어
- 국내주식 + 해외주식 지원
"""

import asyncio
import json
import logging
import os
import sys
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import deque

import pandas as pd
import numpy as np
import requests
import websockets
import yaml
from base64 import b64decode
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# 텔레그램
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
    TELEGRAM_OK = True
except:
    TELEGRAM_OK = False
    print("⚠️  텔레그램 설치 필요: pip install python-telegram-bot")


# ============================================================================
# 로깅 설정
# ============================================================================
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(f'logs/bot_{datetime.now().strftime("%Y%m%d")}.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ============================================================================
# 설정
# ============================================================================
CONFIG_ROOT = os.path.join(os.path.expanduser("~"), "KIS", "config")
TOKEN_FILE = os.path.join(CONFIG_ROOT, f"KIS{datetime.today().strftime('%Y%m%d')}")
CONFIG_FILE = "kis_devlp.yaml"

os.makedirs(CONFIG_ROOT, exist_ok=True)
if not os.path.exists(TOKEN_FILE):
    open(TOKEN_FILE, "w").close()

try:
    with open(CONFIG_FILE, encoding="UTF-8") as f:
        CFG = yaml.load(f, Loader=yaml.FullLoader)
except:
    logger.error("❌ kis_devlp.yaml 파일이 없습니다!")
    sys.exit(1)


# ============================================================================
# 한투 API 인증
# ============================================================================
class KISAuth:
    """한투 API 인증"""
    
    @staticmethod
    def get_token(svr="prod"):
        """토큰 발급"""
        # 기존 토큰 확인
        try:
            with open(TOKEN_FILE) as f:
                data = yaml.load(f, Loader=yaml.FullLoader)
                if data and 'token' in data:
                    exp = datetime.strftime(data["valid-date"], "%Y-%m-%d %H:%M:%S")
                    now = datetime.today().strftime("%Y-%m-%d %H:%M:%S")
                    if exp > now:
                        return data["token"]
        except:
            pass
        
        # 새 토큰 발급
        ak = "my_app" if svr == "prod" else "paper_app"
        sec = "my_sec" if svr == "prod" else "paper_sec"
        
        url = f"{CFG[svr]}/oauth2/tokenP"
        headers = {"Content-Type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": CFG[ak],
            "appsecret": CFG[sec]
        }
        
        res = requests.post(url, headers=headers, data=json.dumps(body))
        if res.status_code == 200:
            data = res.json()
            token = data["access_token"]
            expired = data["access_token_token_expired"]
            
            # 저장
            valid_date = datetime.strptime(expired, "%Y-%m-%d %H:%M:%S")
            with open(TOKEN_FILE, "w") as f:
                f.write(f"token: {token}\nvalid-date: {valid_date}\n")
            
            logger.info("✅ 토큰 발급 완료")
            return token
        else:
            logger.error(f"❌ 토큰 발급 실패: {res.text}")
            return None
    
    @staticmethod
    def get_ws_key(svr="prod"):
        """웹소켓 접속키"""
        ak = "my_app" if svr == "prod" else "paper_app"
        sec = "my_sec" if svr == "prod" else "paper_sec"
        
        url = f"{CFG[svr]}/oauth2/Approval"
        headers = {"Content-Type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": CFG[ak],
            "secretkey": CFG[sec]
        }
        
        res = requests.post(url, headers=headers, data=json.dumps(body))
        if res.status_code == 200:
            return res.json()["approval_key"]
        return None


# ============================================================================
# 시세 데이터 관리
# ============================================================================
class MarketData:
    """시세 데이터 저장 및 분석"""
    
    def __init__(self):
        # 종목별 캔들 데이터 (5분봉, 15분봉)
        self.candles_5m = {}  # {종목코드: deque(최대 100개)}
        self.candles_15m = {}
        
        # 실시간 체결가
        self.current_price = {}
        
        # 거래량 추적
        self.volume_history = {}  # 최근 20개 5분봉 거래량
    
    def add_candle_5m(self, code, candle):
        """5분봉 추가"""
        if code not in self.candles_5m:
            self.candles_5m[code] = deque(maxlen=100)
        self.candles_5m[code].append(candle)
    
    def add_candle_15m(self, code, candle):
        """15분봉 추가"""
        if code not in self.candles_15m:
            self.candles_15m[code] = deque(maxlen=100)
        self.candles_15m[code].append(candle)
    
    def update_price(self, code, price):
        """현재가 업데이트"""
        self.current_price[code] = price
    
    def get_ma(self, code, period=50, timeframe='15m'):
        """이동평균 계산"""
        candles = self.candles_15m.get(code) if timeframe == '15m' else self.candles_5m.get(code)
        if not candles or len(candles) < period:
            return None
        
        prices = [c['close'] for c in list(candles)[-period:]]
        return sum(prices) / len(prices)
    
    def check_golden_cross(self, code):
        """골든크로스 확인 (15분봉 MA50/MA200)"""
        ma50 = self.get_ma(code, 50, '15m')
        ma200 = self.get_ma(code, 200, '15m')
        
        if ma50 is None or ma200 is None:
            return False
        
        return ma50 > ma200
    
    def check_volume_spike(self, code):
        """거래량 급증 확인"""
        candles = self.candles_5m.get(code, [])
        if len(candles) < 21:
            return False
        
        recent = list(candles)
        current_vol = recent[-1]['volume']
        avg_vol = sum(c['volume'] for c in recent[-21:-1]) / 20
        
        return current_vol > avg_vol * 2.5  # 2.5배 이상


# ============================================================================
# 주문 관리
# ============================================================================
class OrderManager:
    """주문 실행 및 관리"""
    
    def __init__(self, env):
        self.env = env
        self.positions = {}  # {종목코드: {매수가, 수량, 진입시간, 최고가}}
    
    def buy(self, code, qty, price=0):
        """매수 주문"""
        url = f"{self.env.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        tr_id = "VTTC0802U" if self.env.is_vps else "TTTC0802U"
        
        headers = self.env.get_headers(tr_id)
        body = {
            "CANO": self.env.account,
            "ACNT_PRDT_CD": self.env.product,
            "PDNO": code,
            "ORD_DVSN": "01",  # 시장가
            "ORD_QTY": str(qty),
            "ORD_UNPR": "0",
        }
        
        res = requests.post(url, headers=headers, data=json.dumps(body))
        if res.status_code == 200:
            data = res.json()
            if data.get("rt_cd") == "0":
                logger.info(f"✅ 매수 주문: {code} {qty}주")
                return True
        
        logger.error(f"❌ 매수 실패: {code}")
        return False
    
    def sell(self, code, qty, price=0):
        """매도 주문"""
        url = f"{self.env.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        tr_id = "VTTC0801U" if self.env.is_vps else "TTTC0801U"
        
        headers = self.env.get_headers(tr_id)
        body = {
            "CANO": self.env.account,
            "ACNT_PRDT_CD": self.env.product,
            "PDNO": code,
            "ORD_DVSN": "01",  # 시장가
            "ORD_QTY": str(qty),
            "ORD_UNPR": "0",
        }
        
        res = requests.post(url, headers=headers, data=json.dumps(body))
        if res.status_code == 200:
            data = res.json()
            if data.get("rt_cd") == "0":
                logger.info(f"✅ 매도 주문: {code} {qty}주")
                return True
        
        logger.error(f"❌ 매도 실패: {code}")
        return False
    
    def get_balance(self):
        """잔고 조회"""
        url = f"{self.env.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "VTTC8434R" if self.env.is_vps else "TTTC8434R"
        
        headers = self.env.get_headers(tr_id)
        params = {
            "CANO": self.env.account,
            "ACNT_PRDT_CD": self.env.product,
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
        
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 200:
            data = res.json()
            if data.get("rt_cd") == "0":
                stocks = pd.DataFrame(data.get("output1", []))
                summary = data.get("output2", {})
                return stocks, summary
        
        return pd.DataFrame(), {}


# ============================================================================
# 거래 환경
# ============================================================================
class TradingEnv:
    """거래 환경"""
    
    def __init__(self, svr="vps", market="domestic"):
        self.svr = svr
        self.is_vps = (svr == "vps")
        self.market = market  # domestic or overseas
        
        # API 키
        ak = "my_app" if svr == "prod" else "paper_app"
        sec = "my_sec" if svr == "prod" else "paper_sec"
        self.app_key = CFG[ak]
        self.app_secret = CFG[sec]
        
        # 계좌
        if market == "domestic":
            self.account = CFG["my_acct_stock"] if svr == "prod" else CFG["my_paper_stock"]
        else:
            self.account = CFG["my_acct_stock"] if svr == "prod" else CFG["my_paper_stock"]
        
        self.product = "01"
        
        # URL
        self.base_url = CFG[svr]
        self.ws_url = CFG["ops" if svr == "prod" else "vops"]
        
        # 토큰
        self.token = KISAuth.get_token(svr)
        self.ws_key = KISAuth.get_ws_key(svr)
        
        if not self.token:
            raise Exception("토큰 발급 실패")
    
    def get_headers(self, tr_id, tr_cont=""):
        """API 헤더"""
        return {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "tr_cont": tr_cont,
            "custtype": "P"
        }


# ============================================================================
# 텔레그램 봇
# ============================================================================
class TelegramBot:
    """텔레그램 봇"""
    
    def __init__(self, token, chat_id, system):
        self.token = token
        self.chat_id = chat_id
        self.system = system
        self.app = None
        self.enabled = bool(token and chat_id and TELEGRAM_OK)
        
        if self.enabled:
            self.app = Application.builder().token(token).build()
            self._register_handlers()
    
    def _register_handlers(self):
        """명령어 등록"""
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("menu", self.cmd_menu))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CallbackQueryHandler(self.button_handler))
    
    async def cmd_start(self, update: Update, context):
        """시작"""
        await update.message.reply_text(
            "🤖 <b>스캘핑 자동매매 봇</b>\n\n"
            "/menu - 메인 메뉴\n"
            "/status - 현재 상태",
            parse_mode='HTML'
        )
    
    async def cmd_menu(self, update: Update, context):
        """메뉴"""
        keyboard = [
            [
                InlineKeyboardButton("💼 잔고", callback_data="balance"),
                InlineKeyboardButton("📊 포지션", callback_data="positions")
            ],
            [
                InlineKeyboardButton("🟢 국내주식", callback_data="market_domestic"),
                InlineKeyboardButton("🔵 해외주식", callback_data="market_overseas")
            ],
            [
                InlineKeyboardButton("▶️ 시작", callback_data="start"),
                InlineKeyboardButton("⏹ 중지", callback_data="stop")
            ]
        ]
        
        status = "🟢 실행중" if self.system.running else "🔴 중지"
        market = "🟢 국내" if self.system.current_market == "domestic" else "🔵 해외"
        
        msg = f"<b>자동매매 상태</b>\n\n"
        msg += f"상태: {status}\n"
        msg += f"시장: {market}\n"
        msg += f"시간: {datetime.now().strftime('%H:%M:%S')}"
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await update.message.reply_text(msg, parse_mode='HTML', reply_markup=reply_markup)
    
    async def cmd_status(self, update: Update, context):
        """상태 조회"""
        stocks, summary = self.system.order_mgr.get_balance()
        
        msg = "<b>💼 현재 잔고</b>\n\n"
        
        if not stocks.empty:
            for _, row in stocks.head(5).iterrows():
                name = row.get('prdt_name', 'N/A')
                qty = row.get('hldg_qty', '0')
                price = row.get('prpr', '0')
                profit = row.get('evlu_pfls_amt', '0')
                msg += f"• {name}\n  {qty}주 @ {price}원 ({profit}원)\n\n"
        else:
            msg += "보유 종목 없음\n"
        
        if summary:
            total = summary.get('tot_evlu_amt', '0')
            profit = summary.get('evlu_pfls_smtl_amt', '0')
            msg += f"\n총 평가: {total}원\n"
            msg += f"평가손익: {profit}원"
        
        await update.message.reply_text(msg, parse_mode='HTML')
    
    async def button_handler(self, query):
        """버튼 클릭"""
        data = query.data
        
        if data == "balance":
            await self._show_balance(query)
        elif data == "positions":
            await self._show_positions(query)
        elif data == "market_domestic":
            self.system.current_market = "domestic"
            await query.answer("🟢 국내주식으로 전환")
            await self.cmd_menu(query, None)
        elif data == "market_overseas":
            self.system.current_market = "overseas"
            await query.answer("🔵 해외주식으로 전환")
            await self.cmd_menu(query, None)
        elif data == "start":
            self.system.running = True
            await query.answer("▶️ 시작")
            await self.cmd_menu(query, None)
        elif data == "stop":
            self.system.running = False
            await query.answer("⏹ 중지")
            await self.cmd_menu(query, None)
    
    async def _show_balance(self, query):
        """잔고 표시"""
        await query.edit_message_text("⏳ 조회 중...")
        
        stocks, summary = self.system.order_mgr.get_balance()
        
        msg = "<b>💼 실시간 잔고</b>\n\n"
        
        if not stocks.empty:
            for _, row in stocks.iterrows():
                name = row.get('prdt_name', '')
                qty = row.get('hldg_qty', '0')
                price = row.get('prpr', '0')
                profit = row.get('evlu_pfls_amt', '0')
                rate = row.get('evlu_pfls_rt', '0')
                msg += f"📌 {name}\n"
                msg += f"   {qty}주 @ {price}원\n"
                msg += f"   손익: {profit}원 ({rate}%)\n\n"
        else:
            msg += "보유 종목 없음"
        
        keyboard = [[InlineKeyboardButton("🔙 메뉴", callback_data="menu")]]
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    
    async def _show_positions(self, query):
        """포지션 표시"""
        positions = self.system.order_mgr.positions
        
        msg = "<b>📊 현재 포지션</b>\n\n"
        
        if positions:
            for code, pos in positions.items():
                msg += f"📌 {code}\n"
                msg += f"   매수가: {pos['buy_price']:,}원\n"
                msg += f"   수량: {pos['qty']}주\n"
                msg += f"   진입: {pos['entry_time'].strftime('%H:%M')}\n\n"
        else:
            msg += "현재 포지션 없음"
        
        keyboard = [[InlineKeyboardButton("🔙 메뉴", callback_data="menu")]]
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    
    def send_message(self, text):
        """메시지 전송"""
        if not self.enabled:
            return
        
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}
        
        try:
            requests.post(url, data=data, timeout=5)
        except:
            pass
    
    def start_bot(self):
        """봇 시작"""
        if not self.enabled:
            return
        
        def run():
            self.app.run_polling(allowed_updates=Update.ALL_TYPES)
        
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        logger.info("✅ 텔레그램 봇 시작")


# ============================================================================
# 메인 시스템
# ============================================================================
class ScalpingSystem:
    """스캘핑 자동매매 시스템"""
    
    def __init__(self, telegram_token="", telegram_chat_id=""):
        logger.info("="*60)
        logger.info("스캘핑 자동매매 시스템 초기화")
        logger.info("="*60)
        
        # 환경
        self.env_domestic = TradingEnv("vps", "domestic")
        self.env_overseas = TradingEnv("vps", "overseas")
        
        # 현재 시장
        self.current_market = "domestic"
        
        # 모듈
        self.market_data = MarketData()
        self.order_mgr = OrderManager(self.env_domestic)
        self.telegram = TelegramBot(telegram_token, telegram_chat_id, self)
        
        # 상태
        self.running = False
        self.positions = {}
        
        # 전략 파라미터
        self.max_positions = 3
        self.profit_rate = 0.03  # 3%
        self.loss_rate = 0.025  # 2.5%
        
        logger.info("✅ 초기화 완료")
    
    def check_entry_signal(self, code):
        """진입 신호 확인"""
        # 골든크로스 확인
        if not self.market_data.check_golden_cross(code):
            return False
        
        # 거래량 급증 확인
        if not self.market_data.check_volume_spike(code):
            return False
        
        # 최대 포지션 체크
        if len(self.positions) >= self.max_positions:
            return False
        
        return True
    
    def check_exit_signal(self, code, current_price):
        """청산 신호 확인"""
        if code not in self.positions:
            return False
        
        pos = self.positions[code]
        buy_price = pos['buy_price']
        
        # 수익률 계산
        profit_rate = (current_price - buy_price) / buy_price
        
        # 익절
        if profit_rate >= self.profit_rate:
            logger.info(f"✅ 익절: {code} {profit_rate:.2%}")
            return True
        
        # 손절
        if profit_rate <= -self.loss_rate:
            logger.info(f"❌ 손절: {code} {profit_rate:.2%}")
            return True
        
        # 시간 체크 (2시간 이상 보유 시)
        elapsed = (datetime.now() - pos['entry_time']).seconds
        if elapsed > 7200 and profit_rate > 0.01:
            logger.info(f"⏰ 시간 청산: {code}")
            return True
        
        return False
    
    def execute_buy(self, code):
        """매수 실행"""
        logger.info(f"🔵 매수 시도: {code}")
        
        # 매수 (임시로 10주)
        if self.order_mgr.buy(code, 10):
            self.positions[code] = {
                'buy_price': self.market_data.current_price.get(code, 0),
                'qty': 10,
                'entry_time': datetime.now(),
                'peak_price': self.market_data.current_price.get(code, 0)
            }
            
            self.telegram.send_message(
                f"🔵 <b>매수</b>\n"
                f"종목: {code}\n"
                f"시간: {datetime.now().strftime('%H:%M:%S')}"
            )
    
    def execute_sell(self, code):
        """매도 실행"""
        if code not in self.positions:
            return
        
        logger.info(f"🔴 매도 시도: {code}")
        
        pos = self.positions[code]
        if self.order_mgr.sell(code, pos['qty']):
            current_price = self.market_data.current_price.get(code, 0)
            profit = (current_price - pos['buy_price']) * pos['qty']
            profit_rate = (current_price - pos['buy_price']) / pos['buy_price']
            
            self.telegram.send_message(
                f"🔴 <b>매도</b>\n"
                f"종목: {code}\n"
                f"손익: {profit:+,.0f}원 ({profit_rate:+.2%})\n"
                f"시간: {datetime.now().strftime('%H:%M:%S')}"
            )
            
            del self.positions[code]
    
    def run_loop(self):
        """메인 루프"""
        logger.info("메인 루프 시작")
        
        while True:
            try:
                if not self.running:
                    time.sleep(10)
                    continue
                
                # 잔고 업데이트
                stocks, summary = self.order_mgr.get_balance()
                
                # 포지션 체크 (청산 신호)
                for code in list(self.positions.keys()):
                    current_price = self.market_data.current_price.get(code, 0)
                    if current_price > 0:
                        if self.check_exit_signal(code, current_price):
                            self.execute_sell(code)
                
                # 대기
                time.sleep(10)
            
            except Exception as e:
                logger.error(f"❌ 루프 오류: {e}")
                time.sleep(10)
    
    def start(self):
        """시스템 시작"""
        logger.info("="*60)
        logger.info("시스템 시작")
        logger.info("="*60)
        
        # 텔레그램 봇 시작
        self.telegram.start_bot()
        time.sleep(2)
        
        self.telegram.send_message(
            "🚀 <b>자동매매 시스템 시작</b>\n\n"
            "텔레그램 명령어:\n"
            "/menu - 메인 메뉴\n"
            "/status - 현재 상태"
        )
        
        # 메인 루프
        self.run_loop()


# ============================================================================
# 실행
# ============================================================================
def main():
    print("="*60)
    print("스캘핑 자동매매 봇")
    print("="*60)
    
    # 텔레그램 설정
    telegram_token = input("텔레그램 봇 토큰 (선택): ").strip()
    telegram_chat_id = input("텔레그램 채팅 ID (선택): ").strip()
    
    # 시스템 시작
    system = ScalpingSystem(telegram_token, telegram_chat_id)
    system.start()


if __name__ == "__main__":
    main()
