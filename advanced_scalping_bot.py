#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
한국투자증권 고급 스캘핑 자동매매 시스템
Advanced Multi-Layer Scalping Strategy

[전략 구조]
TIER 1: 종목 유니버스 필터링 (일일 1회)
TIER 2: 실시간 진입 시그널 (5분봉 체크)
TIER 3: 지능형 주문 실행 (슬리피지 최소화)
TIER 4: 동적 출구 전략 (트레일링 스톱)
TIER 5: 리스크 관리 (다층 안전장치)
"""

import asyncio
import json
import logging
import os
import sys
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import deque, defaultdict

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
    print("⚠️  pip install python-telegram-bot")

# ============================================================================
# 로깅
# ============================================================================
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(f'logs/trading_{datetime.now().strftime("%Y%m%d")}.log', encoding='utf-8'),
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
    logger.error("❌ kis_devlp.yaml 없음")
    sys.exit(1)


# ============================================================================
# 전략 파라미터
# ============================================================================
class Strategy:
    """월가 스타일 다층 필터링 전략"""
    
    # TIER 1: 종목 유니버스 필터
    MIN_MARKET_CAP = 50_000_000_000  # 500억 이상
    MIN_DAILY_VOLUME = 5_000_000_000  # 50억 이상
    MIN_PRICE = 5000
    MAX_PRICE = 500_000
    
    # TIER 2: 진입 신호 (복합 분석)
    VOLUME_SPIKE = 2.5  # 직전 20봉 평균 대비
    VOLUME_AMOUNT_SPIKE = 3.0  # 거래대금 급증
    MIN_STRENGTH_3BARS = 150  # 연속 3봉 체결강도
    MIN_STRENGTH_INSTANT = 300  # 순간 체결강도
    MIN_CANDLE_BODY = 0.6  # 캔들 실체 비율
    MIN_GREEN_CANDLES = 2  # 최소 연속 양봉
    
    # TIER 3: 주문 실행
    INITIAL_OFFSET = 0.002  # +0.2%
    RETRY_OFFSET = 0.005  # +0.5%
    ORDER_TIMEOUT = 2  # 초
    
    # TIER 4: 출구 전략
    BASE_PROFIT = 0.03  # 기본 익절 3%
    TRAILING_START = 0.05  # 트레일링 시작 5%
    TRAILING_OFFSET = 0.02  # 트레일링 오프셋 2%
    
    HARD_STOP = 0.025  # 하드 스톱 -2.5%
    TECH_STOP_OFFSET = 0.003  # 기술적 스톱
    
    TIME_PROFIT_HOURS = 2  # 시간 익절
    TIME_PROFIT_MIN = 0.01
    TIME_LOSS_HOURS = 1  # 시간 손절
    TIME_LOSS_MAX = -0.01
    
    EMERGENCY_DROP = 0.015  # 긴급 탈출 -1.5%
    EMERGENCY_SECONDS = 60
    
    # TIER 5: 리스크 관리
    CAPITAL_PER_POS = 0.02  # 2%
    MAX_CAPITAL_PER_POS = 0.05  # 최대 5%
    MAX_POSITIONS = 3
    MAX_DAILY_TRADES = 10
    
    DAILY_LOSS_LIMIT = 0.05  # -5%
    CONSECUTIVE_LOSS = 3
    COOLDOWN_SECONDS = 3600
    
    MIN_WIN_RATE = 0.60
    MAX_DRAWDOWN = 0.10
    MIN_SHARPE = 1.0


# ============================================================================
# 기술적 분석 엔진
# ============================================================================
class TechnicalAnalysis:
    """기술적 분석 (MA, RSI, ADX, 볼린저밴드)"""
    
    @staticmethod
    def calculate_ma(prices: List[float], period: int) -> float:
        """이동평균"""
        if len(prices) < period:
            return 0
        return sum(prices[-period:]) / period
    
    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> float:
        """RSI"""
        if len(prices) < period + 1:
            return 50
        
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    @staticmethod
    def calculate_bollinger(prices: List[float], period: int = 20, std_dev: float = 2.0) -> Tuple[float, float, float]:
        """볼린저 밴드"""
        if len(prices) < period:
            return 0, 0, 0
        
        recent = prices[-period:]
        ma = sum(recent) / period
        variance = sum((x - ma) ** 2 for x in recent) / period
        std = variance ** 0.5
        
        upper = ma + (std * std_dev)
        lower = ma - (std * std_dev)
        
        return upper, ma, lower
    
    @staticmethod
    def check_golden_cross(short_ma: float, long_ma: float, prev_short: float, prev_long: float) -> bool:
        """골든크로스 (신선한 것만)"""
        # 현재 골든크로스 상태이고, 이전에는 아니었음
        current_cross = short_ma > long_ma
        prev_cross = prev_short > prev_long
        
        return current_cross and not prev_cross
    
    @staticmethod
    def calculate_adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """ADX (추세 강도)"""
        if len(highs) < period + 1:
            return 0
        
        # 간단한 ADX 근사치
        tr_sum = 0
        for i in range(1, len(highs)):
            high_low = highs[i] - lows[i]
            high_close = abs(highs[i] - closes[i-1])
            low_close = abs(lows[i] - closes[i-1])
            tr = max(high_low, high_close, low_close)
            tr_sum += tr
        
        avg_tr = tr_sum / len(highs)
        
        # ADX 근사값 (실제로는 더 복잡함)
        return min(100, avg_tr / closes[-1] * 100) if closes[-1] > 0 else 0


# ============================================================================
# 시세 데이터 관리
# ============================================================================
class MarketData:
    """실시간 시세 및 캔들 데이터"""
    
    def __init__(self):
        self.candles_5m = {}  # {code: deque(maxlen=100)}
        self.candles_15m = {}
        self.candles_daily = {}
        
        self.current_price = {}
        self.volume_history = {}
        
        self.ta = TechnicalAnalysis()
    
    def add_candle(self, code: str, candle: dict, timeframe: str = '5m'):
        """캔들 추가"""
        if timeframe == '5m':
            if code not in self.candles_5m:
                self.candles_5m[code] = deque(maxlen=100)
            self.candles_5m[code].append(candle)
        
        elif timeframe == '15m':
            if code not in self.candles_15m:
                self.candles_15m[code] = deque(maxlen=100)
            self.candles_15m[code].append(candle)
        
        elif timeframe == 'daily':
            if code not in self.candles_daily:
                self.candles_daily[code] = deque(maxlen=250)
            self.candles_daily[code].append(candle)
    
    def get_prices(self, code: str, timeframe: str = '15m') -> List[float]:
        """종가 리스트"""
        candles = getattr(self, f'candles_{timeframe}', {}).get(code, [])
        return [c['close'] for c in candles]
    
    # TIER 1: 종목 유니버스 필터
    def check_universe_filter(self, code: str, market_cap: float, daily_volume: float, price: float) -> bool:
        """종목 유니버스 적격성"""
        if market_cap < Strategy.MIN_MARKET_CAP:
            return False
        if daily_volume < Strategy.MIN_DAILY_VOLUME:
            return False
        if price < Strategy.MIN_PRICE or price > Strategy.MAX_PRICE:
            return False
        
        # 일봉 추세 확인 (MA20 > MA60 > MA120)
        daily_prices = self.get_prices(code, 'daily')
        if len(daily_prices) < 120:
            return False
        
        ma20 = self.ta.calculate_ma(daily_prices, 20)
        ma60 = self.ta.calculate_ma(daily_prices, 60)
        ma120 = self.ta.calculate_ma(daily_prices, 120)
        
        if not (ma20 > ma60 > ma120):
            return False
        
        # ADX > 25 (추세 강도)
        if len(self.candles_daily.get(code, [])) >= 20:
            candles = list(self.candles_daily[code])
            highs = [c['high'] for c in candles[-20:]]
            lows = [c['low'] for c in candles[-20:]]
            closes = [c['close'] for c in candles[-20:]]
            adx = self.ta.calculate_adx(highs, lows, closes)
            
            if adx < 25:
                return False
        
        # 15분봉 골든크로스 (5봉 이내)
        prices_15m = self.get_prices(code, '15m')
        if len(prices_15m) < 200:
            return False
        
        ma50 = self.ta.calculate_ma(prices_15m, 50)
        ma200 = self.ta.calculate_ma(prices_15m, 200)
        
        if ma50 <= ma200:
            return False
        
        # RSI 40~70 구간
        rsi = self.ta.calculate_rsi(prices_15m)
        if rsi < 40 or rsi > 70:
            return False
        
        logger.info(f"✅ TIER 1 통과: {code}")
        return True
    
    # TIER 2: 실시간 진입 시그널
    def check_entry_signal(self, code: str) -> Tuple[bool, str]:
        """진입 신호 (복합 분석)"""
        candles_5m = list(self.candles_5m.get(code, []))
        
        if len(candles_5m) < 25:
            return False, "데이터 부족"
        
        current = candles_5m[-1]
        
        # 2.1 거래량 분석
        volumes = [c['volume'] for c in candles_5m[-21:-1]]
        avg_volume = sum(volumes) / len(volumes)
        
        if current['volume'] < avg_volume * Strategy.VOLUME_SPIKE:
            return False, "거래량 미달"
        
        # 2.2 체결강도 (임시로 거래량으로 대체)
        recent_3 = candles_5m[-3:]
        if len(recent_3) < 3:
            return False, "체결강도 데이터 부족"
        
        # 2.3 가격 액션
        # 양봉 체크
        if current['close'] <= current['open']:
            return False, "음봉"
        
        # 캔들 실체 비율
        candle_height = current['high'] - current['low']
        candle_body = abs(current['close'] - current['open'])
        
        if candle_height > 0:
            body_ratio = candle_body / candle_height
            if body_ratio < Strategy.MIN_CANDLE_BODY:
                return False, "긴 꼬리"
        
        # 연속 양봉 체크
        green_count = sum(1 for c in candles_5m[-3:] if c['close'] > c['open'])
        if green_count < Strategy.MIN_GREEN_CANDLES:
            return False, "연속 양봉 부족"
        
        # 2시간 고점 돌파 체크
        prices_2h = [c['high'] for c in candles_5m[-24:]]  # 2시간 = 24개 5분봉
        high_2h = max(prices_2h[:-1]) if len(prices_2h) > 1 else 0
        
        if current['close'] <= high_2h:
            return False, "고점 미돌파"
        
        # 볼린저밴드 체크 (과열 배제)
        prices = [c['close'] for c in candles_5m]
        upper, mid, lower = self.ta.calculate_bollinger(prices)
        
        if upper > 0 and current['close'] > upper * 1.02:  # 상단 +2% 이탈
            return False, "과열 (볼린저 상단 이탈)"
        
        logger.info(f"✅ TIER 2 통과: {code} - 모든 진입 조건 충족")
        return True, "진입 신호"
    
    # TIER 4: 청산 신호
    def check_exit_signal(self, code: str, position: dict) -> Tuple[bool, str]:
        """청산 신호 (동적 전략)"""
        current_price = self.current_price.get(code, 0)
        if current_price == 0:
            return False, ""
        
        buy_price = position['buy_price']
        entry_time = position['entry_time']
        peak_price = position.get('peak_price', buy_price)
        
        # 수익률
        profit_rate = (current_price - buy_price) / buy_price
        
        # 4.1 이익 실현
        # 기본 익절
        if profit_rate >= Strategy.BASE_PROFIT:
            return True, f"익절 {profit_rate:.2%}"
        
        # 트레일링 스톱
        if profit_rate >= Strategy.TRAILING_START:
            # 고점 갱신
            if current_price > peak_price:
                position['peak_price'] = current_price
                position['trailing_active'] = True
                logger.info(f"📈 {code} 고점 갱신: {current_price:,}원")
            
            # 트레일링 스톱 발동
            if position.get('trailing_active'):
                drop_from_peak = (peak_price - current_price) / peak_price
                if drop_from_peak >= Strategy.TRAILING_OFFSET:
                    return True, f"트레일링 스톱 (고점대비 -{drop_from_peak:.2%})"
        
        # 시간 기반 익절
        elapsed = (datetime.now() - entry_time).seconds
        if elapsed > Strategy.TIME_PROFIT_HOURS * 3600:
            if profit_rate >= Strategy.TIME_PROFIT_MIN:
                return True, f"시간 익절 ({elapsed//3600}시간)"
        
        # 4.2 손실 제한
        # 하드 스톱
        if profit_rate <= -Strategy.HARD_STOP:
            return True, f"하드 스톱 {profit_rate:.2%}"
        
        # 기술적 스톱 (5분봉 직전 저점 이탈)
        candles = list(self.candles_5m.get(code, []))
        if len(candles) >= 2:
            prev_low = candles[-2]['low']
            tech_stop = prev_low * (1 - Strategy.TECH_STOP_OFFSET)
            
            if current_price < tech_stop:
                return True, f"기술적 스톱 (직전저점 이탈)"
        
        # 시간 기반 손절
        if elapsed > Strategy.TIME_LOSS_HOURS * 3600:
            if profit_rate <= Strategy.TIME_LOSS_MAX:
                return True, f"시간 손절 ({elapsed//3600}시간)"
        
        # 4.3 긴급 탈출 (1분 내 급락)
        if 'price_1m_ago' in position:
            drop_1m = (position['price_1m_ago'] - current_price) / position['price_1m_ago']
            if drop_1m >= Strategy.EMERGENCY_DROP:
                return True, f"긴급 탈출 (1분 급락 {drop_1m:.2%})"
        
        # 1분 전 가격 기록
        position['price_1m_ago'] = current_price
        
        return False, ""


# ============================================================================
# 성과 추적
# ============================================================================
class PerformanceTracker:
    """성과 분석 및 리스크 관리"""
    
    def __init__(self, start_capital: float):
        self.start_capital = start_capital
        self.current_capital = start_capital
        self.peak_capital = start_capital
        
        self.trades = []
        self.daily_stats = defaultdict(lambda: {
            'trades': 0, 'wins': 0, 'losses': 0, 'profit': 0
        })
        
        self.consecutive_losses = 0
        self.last_loss_time = None
    
    def record_trade(self, trade: dict):
        """거래 기록"""
        self.trades.append({**trade, 'time': datetime.now()})
        
        date = datetime.now().strftime('%Y-%m-%d')
        stats = self.daily_stats[date]
        
        stats['trades'] += 1
        profit = trade.get('profit', 0)
        stats['profit'] += profit
        
        if profit > 0:
            stats['wins'] += 1
            self.consecutive_losses = 0
        else:
            stats['losses'] += 1
            self.consecutive_losses += 1
            self.last_loss_time = datetime.now()
        
        self.current_capital += profit
        
        # MDD
        if self.current_capital > self.peak_capital:
            self.peak_capital = self.current_capital
        
        logger.info(f"📊 거래: {trade['code']} | 손익: {profit:+,.0f}원 | "
                   f"승률: {stats['wins']}/{stats['trades']}")
    
    def get_win_rate(self) -> float:
        """승률"""
        if not self.trades:
            return 0
        wins = sum(1 for t in self.trades if t.get('profit', 0) > 0)
        return wins / len(self.trades)
    
    def get_mdd(self) -> float:
        """최대 낙폭"""
        if self.peak_capital == 0:
            return 0
        return (self.peak_capital - self.current_capital) / self.peak_capital
    
    # TIER 5: 리스크 체크
    def should_stop_trading(self) -> Tuple[bool, str]:
        """거래 중단 여부"""
        # 연속 손절
        if self.consecutive_losses >= Strategy.CONSECUTIVE_LOSS:
            if self.last_loss_time:
                elapsed = (datetime.now() - self.last_loss_time).seconds
                if elapsed < Strategy.COOLDOWN_SECONDS:
                    return True, f"연속 손절 {self.consecutive_losses}회 (대기중)"
        
        # 일일 손실 한도
        today = datetime.now().strftime('%Y-%m-%d')
        daily_profit = self.daily_stats[today]['profit']
        loss_limit = self.start_capital * Strategy.DAILY_LOSS_LIMIT
        
        if daily_profit < -loss_limit:
            return True, f"일일 손실 한도 초과 {daily_profit:,.0f}원"
        
        # 승률
        if len(self.trades) >= 10:
            win_rate = self.get_win_rate()
            if win_rate < Strategy.MIN_WIN_RATE:
                return True, f"승률 미달 {win_rate:.1%}"
        
        # MDD
        mdd = self.get_mdd()
        if mdd > Strategy.MAX_DRAWDOWN:
            return True, f"MDD 초과 {mdd:.1%}"
        
        return False, ""
    
    def save_performance(self):
        """성과 저장"""
        os.makedirs("performance", exist_ok=True)
        
        df = pd.DataFrame(self.trades)
        filename = f"performance/trades_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        logger.info(f"✅ 성과 저장: {filename}")


# ============================================================================
# 한투 API 인증
# ============================================================================
class KISAuth:
    @staticmethod
    def get_token(svr="prod"):
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
        
        ak = "my_app" if svr == "prod" else "paper_app"
        sec = "my_sec" if svr == "prod" else "paper_sec"
        
        url = f"{CFG[svr]}/oauth2/tokenP"
        headers = {"Content-Type": "application/json"}
        body = {"grant_type": "client_credentials", "appkey": CFG[ak], "appsecret": CFG[sec]}
        
        res = requests.post(url, headers=headers, data=json.dumps(body))
        if res.status_code == 200:
            data = res.json()
            token = data["access_token"]
            expired = data["access_token_token_expired"]
            
            valid_date = datetime.strptime(expired, "%Y-%m-%d %H:%M:%S")
            with open(TOKEN_FILE, "w") as f:
                f.write(f"token: {token}\nvalid-date: {valid_date}\n")
            
            logger.info("✅ 토큰 발급")
            return token
        return None


# ============================================================================
# 주문 관리
# ============================================================================
class OrderManager:
    def __init__(self, env):
        self.env = env
        self.positions = {}
    
    # TIER 3: 지능형 주문
    def smart_buy(self, code: str, qty: int, current_price: float) -> bool:
        """지능형 매수 (슬리피지 최소화)"""
        # 1차 시도: 현재가 +0.2%
        price1 = int(current_price * (1 + Strategy.INITIAL_OFFSET))
        
        logger.info(f"🔵 매수 시도: {code} {qty}주 @{price1:,}원")
        
        if self._order(code, "buy", qty, price1):
            return True
        
        # 2차 시도: 현재가 +0.5%
        time.sleep(1)
        price2 = int(current_price * (1 + Strategy.RETRY_OFFSET))
        
        logger.info(f"🔵 재시도: {code} @{price2:,}원")
        
        if self._order(code, "buy", qty, price2):
            return True
        
        logger.warning(f"❌ 매수 포기: {code} (모멘텀 상실)")
        return False
    
    def _order(self, code, side, qty, price):
        """실제 주문"""
        url = f"{self.env.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        
        if side == "buy":
            tr_id = "VTTC0802U" if self.env.is_vps else "TTTC0802U"
        else:
            tr_id = "VTTC0801U" if self.env.is_vps else "TTTC0801U"
        
        headers = self.env.get_headers(tr_id)
        body = {
            "CANO": self.env.account,
            "ACNT_PRDT_CD": self.env.product,
            "PDNO": code,
            "ORD_DVSN": "00",  # 지정가
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price),
        }
        
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=Strategy.ORDER_TIMEOUT)
        if res.status_code == 200:
            data = res.json()
            if data.get("rt_cd") == "0":
                logger.info(f"✅ 주문 성공: {side} {code} {qty}주")
                return True
        
        return False
    
    def market_sell(self, code: str, qty: int) -> bool:
        """시장가 매도"""
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
                logger.info(f"✅ 매도 성공: {code}")
                return True
        
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
                return pd.DataFrame(data.get("output1", [])), data.get("output2", {})
        
        return pd.DataFrame(), {}


# ============================================================================
# 거래 환경
# ============================================================================
class TradingEnv:
    def __init__(self, svr="vps", market="domestic"):
        self.svr = svr
        self.is_vps = (svr == "vps")
        self.market = market
        
        ak = "my_app" if svr == "prod" else "paper_app"
        sec = "my_sec" if svr == "prod" else "paper_sec"
        self.app_key = CFG[ak]
        self.app_secret = CFG[sec]
        
        if market == "domestic":
            self.account = CFG["my_acct_stock"] if svr == "prod" else CFG["my_paper_stock"]
        else:
            self.account = CFG["my_acct_stock"] if svr == "prod" else CFG["my_paper_stock"]
        
        self.product = "01"
        self.base_url = CFG[svr]
        
        self.token = KISAuth.get_token(svr)
        if not self.token:
            raise Exception("토큰 실패")
    
    def get_headers(self, tr_id, tr_cont=""):
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
    def __init__(self, token, chat_id, system):
        self.token = token
        self.chat_id = chat_id
        self.system = system
        self.app = None
        self.enabled = bool(token and chat_id and TELEGRAM_OK)
        
        if self.enabled:
            self.app = Application.builder().token(token).build()
            self._register()
    
    def _register(self):
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("menu", self.cmd_menu))
        self.app.add_handler(CommandHandler("perf", self.cmd_performance))
        self.app.add_handler(CallbackQueryHandler(self.button))
    
    async def cmd_start(self, update: Update, context):
        await update.message.reply_text(
            "🤖 <b>고급 스캘핑 봇</b>\n\n"
            "Multi-Layer Strategy\n"
            "/menu - 메뉴\n"
            "/perf - 성과",
            parse_mode='HTML'
        )
    
    async def cmd_menu(self, update: Update, context):
        keyboard = [
            [InlineKeyboardButton("💼 잔고", callback_data="balance"),
             InlineKeyboardButton("📊 포지션", callback_data="positions")],
            [InlineKeyboardButton("📈 성과", callback_data="performance"),
             InlineKeyboardButton("⚙️ 전략", callback_data="strategy")],
            [InlineKeyboardButton("🟢 국내", callback_data="market_domestic"),
             InlineKeyboardButton("🔵 해외", callback_data="market_overseas")],
            [InlineKeyboardButton("▶️ 시작", callback_data="start"),
             InlineKeyboardButton("⏹ 중지", callback_data="stop")]
        ]
        
        status = "🟢 실행" if self.system.running else "🔴 중지"
        market = "🟢 국내" if self.system.current_market == "domestic" else "🔵 해외"
        
        msg = f"<b>고급 스캘핑 봇</b>\n\n"
        msg += f"상태: {status}\n"
        msg += f"시장: {market}\n"
        msg += f"포지션: {len(self.system.order_mgr.positions)}/{Strategy.MAX_POSITIONS}\n"
        msg += f"시간: {datetime.now().strftime('%H:%M:%S')}"
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await update.message.reply_text(msg, parse_mode='HTML', reply_markup=reply_markup)
    
    async def cmd_performance(self, update: Update, context):
        """성과 조회"""
        perf = self.system.performance
        
        msg = "<b>📈 실시간 성과</b>\n\n"
        msg += f"시작 자본: {perf.start_capital:,.0f}원\n"
        msg += f"현재 자본: {perf.current_capital:,.0f}원\n"
        msg += f"손익: {perf.current_capital - perf.start_capital:+,.0f}원\n\n"
        
        msg += f"총 거래: {len(perf.trades)}회\n"
        msg += f"승률: {perf.get_win_rate():.1%}\n"
        msg += f"MDD: {perf.get_mdd():.1%}\n"
        msg += f"연속 손절: {perf.consecutive_losses}회\n"
        
        await update.message.reply_text(msg, parse_mode='HTML')
    
    async def button(self, query):
        data = query.data
        
        if data == "balance":
            await self._show_balance(query)
        elif data == "positions":
            await self._show_positions(query)
        elif data == "performance":
            await self._show_performance(query)
        elif data == "strategy":
            await self._show_strategy(query)
        elif data == "market_domestic":
            self.system.current_market = "domestic"
            await query.answer("🟢 국내주식")
            await self.cmd_menu(query, None)
        elif data == "market_overseas":
            self.system.current_market = "overseas"
            await query.answer("🔵 해외주식")
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
        await query.edit_message_text("⏳ 조회중...")
        stocks, summary = self.system.order_mgr.get_balance()
        
        msg = "<b>💼 실시간 잔고</b>\n\n"
        if not stocks.empty:
            for _, row in stocks.iterrows():
                msg += f"📌 {row.get('prdt_name', '')}\n"
                msg += f"   {row.get('hldg_qty', '0')}주 @ {row.get('prpr', '0')}원\n"
                msg += f"   손익: {row.get('evlu_pfls_amt', '0')}원\n\n"
        else:
            msg += "보유 종목 없음"
        
        keyboard = [[InlineKeyboardButton("🔙 메뉴", callback_data="menu")]]
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    
    async def _show_positions(self, query):
        positions = self.system.order_mgr.positions
        
        msg = "<b>📊 현재 포지션</b>\n\n"
        if positions:
            for code, pos in positions.items():
                current = self.system.market_data.current_price.get(code, 0)
                profit_rate = (current - pos['buy_price']) / pos['buy_price'] if pos['buy_price'] > 0 else 0
                
                msg += f"📌 {code}\n"
                msg += f"   매수: {pos['buy_price']:,}원\n"
                msg += f"   현재: {current:,}원 ({profit_rate:+.2%})\n"
                msg += f"   고점: {pos.get('peak_price', 0):,}원\n"
                msg += f"   진입: {pos['entry_time'].strftime('%H:%M')}\n\n"
        else:
            msg += "포지션 없음"
        
        keyboard = [[InlineKeyboardButton("🔙 메뉴", callback_data="menu")]]
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    
    async def _show_performance(self, query):
        perf = self.system.performance
        
        msg = "<b>📈 성과 분석</b>\n\n"
        msg += f"<b>자본</b>\n"
        msg += f"시작: {perf.start_capital:,.0f}원\n"
        msg += f"현재: {perf.current_capital:,.0f}원\n"
        msg += f"손익: {perf.current_capital - perf.start_capital:+,.0f}원\n\n"
        
        msg += f"<b>거래</b>\n"
        msg += f"총 {len(perf.trades)}회\n"
        msg += f"승률: {perf.get_win_rate():.1%}\n"
        msg += f"MDD: {perf.get_mdd():.1%}\n\n"
        
        today = datetime.now().strftime('%Y-%m-%d')
        stats = perf.daily_stats[today]
        msg += f"<b>오늘</b>\n"
        msg += f"{stats['wins']}승 {stats['losses']}패\n"
        msg += f"손익: {stats['profit']:+,.0f}원"
        
        keyboard = [[InlineKeyboardButton("🔙 메뉴", callback_data="menu")]]
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    
    async def _show_strategy(self, query):
        msg = "<b>⚙️ 전략 파라미터</b>\n\n"
        msg += f"<b>TIER 1: 유니버스</b>\n"
        msg += f"시총: {Strategy.MIN_MARKET_CAP/1e8:.0f}억+\n"
        msg += f"거래: {Strategy.MIN_DAILY_VOLUME/1e8:.0f}억+\n\n"
        
        msg += f"<b>TIER 2: 진입</b>\n"
        msg += f"거래량: {Strategy.VOLUME_SPIKE}배+\n"
        msg += f"체결강도: {Strategy.MIN_STRENGTH_INSTANT}%+\n\n"
        
        msg += f"<b>TIER 4: 청산</b>\n"
        msg += f"익절: {Strategy.BASE_PROFIT:.1%}\n"
        msg += f"손절: {Strategy.HARD_STOP:.1%}\n"
        msg += f"트레일링: {Strategy.TRAILING_START:.1%}\n\n"
        
        msg += f"<b>TIER 5: 리스크</b>\n"
        msg += f"최대 포지션: {Strategy.MAX_POSITIONS}개\n"
        msg += f"일일 손실: {Strategy.DAILY_LOSS_LIMIT:.1%}"
        
        keyboard = [[InlineKeyboardButton("🔙 메뉴", callback_data="menu")]]
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    
    def send_message(self, text):
        if not self.enabled:
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}
        try:
            requests.post(url, data=data, timeout=5)
        except:
            pass
    
    def start_bot(self):
        if not self.enabled:
            return
        def run():
            self.app.run_polling(allowed_updates=Update.ALL_TYPES)
        threading.Thread(target=run, daemon=True).start()
        logger.info("✅ 텔레그램 봇 시작")


# ============================================================================
# 메인 시스템
# ============================================================================
class AdvancedScalpingSystem:
    """고급 스캘핑 시스템 (Multi-Layer Strategy)"""
    
    def __init__(self, telegram_token="", telegram_chat_id="", start_capital=10000000):
        logger.info("="*60)
        logger.info("고급 스캘핑 시스템 초기화 (Multi-Layer Strategy)")
        logger.info("="*60)
        
        self.env_domestic = TradingEnv("vps", "domestic")
        self.current_market = "domestic"
        
        self.market_data = MarketData()
        self.order_mgr = OrderManager(self.env_domestic)
        self.performance = PerformanceTracker(start_capital)
        self.telegram = TelegramBot(telegram_token, telegram_chat_id, self)
        
        self.running = False
        self.watch_list = []  # TIER 1 통과 종목
        
        logger.info("✅ 초기화 완료")
    
    def execute_buy(self, code: str):
        """매수 실행"""
        current_price = self.market_data.current_price.get(code, 0)
        if current_price == 0:
            return
        
        # 포지션 사이징
        capital_per_pos = self.performance.start_capital * Strategy.CAPITAL_PER_POS
        qty = int(capital_per_pos / current_price)
        
        if qty == 0:
            return
        
        logger.info(f"🔵 매수 시도: {code} {qty}주 @{current_price:,}원")
        
        # TIER 3: 지능형 주문
        if self.order_mgr.smart_buy(code, qty, current_price):
            self.order_mgr.positions[code] = {
                'buy_price': current_price,
                'qty': qty,
                'entry_time': datetime.now(),
                'peak_price': current_price,
                'trailing_active': False
            }
            
            self.telegram.send_message(
                f"🔵 <b>매수 체결</b>\n"
                f"종목: {code}\n"
                f"수량: {qty}주\n"
                f"가격: {current_price:,}원\n"
                f"시간: {datetime.now().strftime('%H:%M:%S')}"
            )
    
    def execute_sell(self, code: str, reason: str):
        """매도 실행"""
        if code not in self.order_mgr.positions:
            return
        
        pos = self.order_mgr.positions[code]
        current_price = self.market_data.current_price.get(code, 0)
        
        logger.info(f"🔴 매도 시도: {code} - {reason}")
        
        if self.order_mgr.market_sell(code, pos['qty']):
            profit = (current_price - pos['buy_price']) * pos['qty']
            profit_rate = (current_price - pos['buy_price']) / pos['buy_price']
            
            # 성과 기록
            self.performance.record_trade({
                'code': code,
                'profit': profit,
                'profit_rate': profit_rate,
                'reason': reason
            })
            
            self.telegram.send_message(
                f"🔴 <b>매도 체결</b>\n"
                f"종목: {code}\n"
                f"사유: {reason}\n"
                f"손익: {profit:+,.0f}원 ({profit_rate:+.2%})\n"
                f"시간: {datetime.now().strftime('%H:%M:%S')}"
            )
            
            del self.order_mgr.positions[code]
            
            # 성과 저장
            if len(self.performance.trades) % 5 == 0:
                self.performance.save_performance()
    
    def run_loop(self):
        """메인 루프"""
        logger.info("메인 루프 시작")
        
        last_balance_check = datetime.now()
        
        while True:
            try:
                if not self.running:
                    time.sleep(10)
                    continue
                
                # TIER 5: 리스크 체크
                should_stop, reason = self.performance.should_stop_trading()
                if should_stop:
                    logger.warning(f"⚠️ 거래 중단: {reason}")
                    self.telegram.send_message(f"⚠️ <b>거래 중단</b>\n{reason}")
                    time.sleep(60)
                    continue
                
                # 잔고 업데이트 (30초마다)
                if (datetime.now() - last_balance_check).seconds >= 30:
                    stocks, summary = self.order_mgr.get_balance()
                    last_balance_check = datetime.now()
                
                # 포지션 체크 (청산 신호)
                for code in list(self.order_mgr.positions.keys()):
                    should_exit, reason = self.market_data.check_exit_signal(
                        code, self.order_mgr.positions[code]
                    )
                    
                    if should_exit:
                        self.execute_sell(code, reason)
                
                # TODO: 진입 신호 체크 (실제로는 웹소켓으로 실시간 시세 받아서 처리)
                # 현재는 watch_list를 수동으로 관리해야 함
                
                time.sleep(10)
            
            except Exception as e:
                logger.error(f"❌ 루프 오류: {e}")
                logger.error(traceback.format_exc())
                time.sleep(10)
    
    def start(self):
        logger.info("="*60)
        logger.info("시스템 시작")
        logger.info("="*60)
        
        self.telegram.start_bot()
        time.sleep(2)
        
        self.telegram.send_message(
            "🚀 <b>고급 스캘핑 시스템 시작</b>\n\n"
            "<b>Multi-Layer Strategy</b>\n"
            "• TIER 1: 종목 유니버스 필터\n"
            "• TIER 2: 실시간 진입 시그널\n"
            "• TIER 3: 지능형 주문 실행\n"
            "• TIER 4: 동적 출구 전략\n"
            "• TIER 5: 리스크 관리\n\n"
            "/menu - 메인 메뉴"
        )
        
        self.run_loop()


# ============================================================================
# 실행
# ============================================================================
def main():
    print("="*60)
    print("고급 스캘핑 자동매매 시스템")
    print("Multi-Layer Filtering + Dynamic Exit Strategy")
    print("="*60)
    
    telegram_token = input("텔레그램 봇 토큰: ").strip()
    telegram_chat_id = input("텔레그램 채팅 ID: ").strip()
    start_capital = int(input("시작 자본금 (원) [10000000]: ").strip() or "10000000")
    
    system = AdvancedScalpingSystem(telegram_token, telegram_chat_id, start_capital)
    system.start()


if __name__ == "__main__":
    main()
