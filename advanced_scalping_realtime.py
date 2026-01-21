#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
한국투자증권 고급 스캘핑 자동매매 시스템 (실전 버전)
Advanced Multi-Layer Scalping Strategy with Real-time WebSocket

[개선 사항]
1. 5분봉 자동 생성 (실시간 체결가 → 캔들)
2. 웹소켓 자동 재연결
3. 체결강도 정확도 개선
4. 실전 통합 테스트
"""

import asyncio
import json
import logging
import os
import sys
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import deque, defaultdict
import traceback

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
    """전략 설정"""
    
    # TIER 1
    MIN_MARKET_CAP = 50_000_000_000
    MIN_DAILY_VOLUME = 5_000_000_000
    MIN_PRICE = 5000
    MAX_PRICE = 500_000
    
    # TIER 2
    VOLUME_SPIKE = 2.5
    VOLUME_AMOUNT_SPIKE = 3.0
    MIN_STRENGTH_3BARS = 150
    MIN_STRENGTH_INSTANT = 300
    MIN_CANDLE_BODY = 0.6
    MIN_GREEN_CANDLES = 2
    
    # TIER 3
    INITIAL_OFFSET = 0.002
    RETRY_OFFSET = 0.005
    ORDER_TIMEOUT = 2
    
    # TIER 4
    BASE_PROFIT = 0.03
    TRAILING_START = 0.05
    TRAILING_OFFSET = 0.02
    HARD_STOP = 0.025
    TECH_STOP_OFFSET = 0.003
    TIME_PROFIT_HOURS = 2
    TIME_PROFIT_MIN = 0.01
    TIME_LOSS_HOURS = 1
    TIME_LOSS_MAX = -0.01
    EMERGENCY_DROP = 0.015
    EMERGENCY_SECONDS = 60
    
    # TIER 5
    CAPITAL_PER_POS = 0.02
    MAX_CAPITAL_PER_POS = 0.05
    MAX_POSITIONS = 3
    MAX_DAILY_TRADES = 10
    DAILY_LOSS_LIMIT = 0.05
    CONSECUTIVE_LOSS = 3
    COOLDOWN_SECONDS = 3600
    MIN_WIN_RATE = 0.60
    MAX_DRAWDOWN = 0.10


# ============================================================================
# 5분봉 자동 생성기 (개선)
# ============================================================================
class CandleBuilder:
    """실시간 체결가로 5분봉 생성"""
    
    def __init__(self, timeframe_minutes=5):
        self.timeframe = timeframe_minutes
        self.candles = {}  # {종목코드: deque(캔들)}
        self.current_candles = {}  # {종목코드: 현재 캔들}
        self.candle_start_times = {}  # {종목코드: 시작 시간}
        
        logger.info(f"✅ CandleBuilder 초기화 ({timeframe_minutes}분봉)")
    
    def add_tick(self, code: str, price: float, volume: int, timestamp: datetime) -> Optional[dict]:
        """
        체결 틱 추가 및 캔들 생성
        
        Returns:
            완성된 캔들 (있으면) 또는 None
        """
        # 캔들 시작 시간 계산 (5분 단위)
        minute = timestamp.minute
        candle_minute = (minute // self.timeframe) * self.timeframe
        candle_start = timestamp.replace(minute=candle_minute, second=0, microsecond=0)
        
        # 종목 초기화
        if code not in self.candles:
            self.candles[code] = deque(maxlen=200)  # 최대 200개 저장
        
        # 새 캔들 시작
        if code not in self.current_candles or self.candle_start_times[code] != candle_start:
            # 기존 캔들 완성
            completed_candle = None
            if code in self.current_candles:
                completed_candle = self.current_candles[code].copy()
                self.candles[code].append(completed_candle)
                logger.debug(f"✅ {code} 캔들 완성: {completed_candle['time']} | "
                           f"O:{completed_candle['open']} H:{completed_candle['high']} "
                           f"L:{completed_candle['low']} C:{completed_candle['close']} V:{completed_candle['volume']}")
            
            # 새 캔들 시작
            self.current_candles[code] = {
                'time': candle_start,
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': volume
            }
            self.candle_start_times[code] = candle_start
            
            return completed_candle
        
        # 기존 캔들 업데이트
        else:
            candle = self.current_candles[code]
            candle['high'] = max(candle['high'], price)
            candle['low'] = min(candle['low'], price)
            candle['close'] = price
            candle['volume'] += volume
            
            return None
    
    def get_candles(self, code: str, count: int = None) -> List[dict]:
        """완성된 캔들 조회"""
        if code not in self.candles:
            return []
        
        candles = list(self.candles[code])
        if count:
            return candles[-count:]
        return candles
    
    def get_recent_volume_avg(self, code: str, periods: int = 20) -> float:
        """최근 N개 캔들 평균 거래량"""
        candles = self.get_candles(code, periods)
        if len(candles) < periods:
            return 0
        
        return sum(c['volume'] for c in candles) / len(candles)


# ============================================================================
# 체결강도 계산기 (개선)
# ============================================================================
class StrengthCalculator:
    """체결강도 정확도 개선"""
    
    def __init__(self):
        self.strength_history = {}  # {종목코드: deque(체결강도)}
        logger.info("✅ StrengthCalculator 초기화")
    
    def calculate(self, code: str, asking_data: dict) -> float:
        """
        호가창 데이터로 체결강도 계산
        
        Args:
            asking_data: 실시간 호가 데이터
                - ASKP_RSQN1~10: 매도 호가 잔량
                - BIDP_RSQN1~10: 매수 호가 잔량
        
        Returns:
            체결강도 (%)
        """
        try:
            # 매도 잔량 (Ask)
            ask_volume = 0
            for i in range(1, 11):
                vol = asking_data.get(f'ASKP_RSQN{i}', 0)
                ask_volume += int(vol) if vol else 0
            
            # 매수 잔량 (Bid)
            bid_volume = 0
            for i in range(1, 11):
                vol = asking_data.get(f'BIDP_RSQN{i}', 0)
                bid_volume += int(vol) if vol else 0
            
            # 체결강도 = (매수 / 매도) × 100
            if ask_volume == 0:
                strength = 200  # 매도 잔량이 없으면 강세
            else:
                strength = (bid_volume / ask_volume) * 100
            
            # 이력 저장
            if code not in self.strength_history:
                self.strength_history[code] = deque(maxlen=100)
            self.strength_history[code].append({
                'time': datetime.now(),
                'strength': strength,
                'bid_vol': bid_volume,
                'ask_vol': ask_volume
            })
            
            return strength
        
        except Exception as e:
            logger.error(f"❌ 체결강도 계산 오류 ({code}): {e}")
            return 100
    
    def get_average_strength(self, code: str, periods: int = 3) -> float:
        """최근 N개 평균 체결강도"""
        if code not in self.strength_history or len(self.strength_history[code]) == 0:
            return 100
        
        recent = list(self.strength_history[code])[-periods:]
        return sum(s['strength'] for s in recent) / len(recent)
    
    def check_consecutive_strength(self, code: str, min_strength: float = 150, periods: int = 3) -> bool:
        """연속 N개 체결강도 체크"""
        if code not in self.strength_history or len(self.strength_history[code]) < periods:
            return False
        
        recent = list(self.strength_history[code])[-periods:]
        return all(s['strength'] >= min_strength for s in recent)


# ============================================================================
# 웹소켓 클라이언트 (재연결 로직 추가)
# ============================================================================
class WebSocketClient:
    """웹소켓 자동 재연결"""
    
    def __init__(self, env):
        self.env = env
        self.ws = None
        self.is_running = False
        self.callbacks = {}
        self.subscriptions = []  # 구독 목록 저장
        
        # 재연결 설정
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5
        
        logger.info("✅ WebSocketClient 초기화")
    
    async def connect(self):
        """웹소켓 연결 (재연결 로직 포함)"""
        reconnect_count = 0
        
        while self.is_running and reconnect_count < self.max_reconnect_attempts:
            try:
                url = self.env.ws_url
                logger.info(f"🔌 웹소켓 연결 시도... ({reconnect_count + 1}/{self.max_reconnect_attempts})")
                
                async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                    self.ws = ws
                    reconnect_count = 0  # 연결 성공 시 카운트 리셋
                    
                    logger.info("✅ 웹소켓 연결 성공")
                    
                    # 기존 구독 재등록
                    await self.resubscribe()
                    
                    # 메시지 수신
                    await self.receive_messages()
            
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"⚠️ 웹소켓 연결 끊김: {e}")
                reconnect_count += 1
                
                if reconnect_count < self.max_reconnect_attempts:
                    logger.info(f"🔄 {self.reconnect_delay}초 후 재연결...")
                    await asyncio.sleep(self.reconnect_delay)
                else:
                    logger.error("❌ 최대 재연결 시도 횟수 초과")
                    break
            
            except Exception as e:
                logger.error(f"❌ 웹소켓 오류: {e}")
                logger.error(traceback.format_exc())
                reconnect_count += 1
                await asyncio.sleep(self.reconnect_delay)
    
    async def subscribe(self, tr_id: str, tr_key: str):
        """실시간 구독"""
        if not self.ws:
            logger.warning("⚠️ 웹소켓 미연결")
            return
        
        msg = {
            "header": {
                "approval_key": self.env.ws_key,
                "custtype": "P",
                "tr_type": "1",  # 구독
                "content-type": "utf-8"
            },
            "body": {
                "input": {
                    "tr_id": tr_id,
                    "tr_key": tr_key
                }
            }
        }
        
        await self.ws.send(json.dumps(msg))
        
        # 구독 목록 저장
        self.subscriptions.append((tr_id, tr_key))
        
        logger.info(f"📡 구독: {tr_id} - {tr_key}")
    
    async def resubscribe(self):
        """재연결 시 구독 재등록"""
        if not self.subscriptions:
            return
        
        logger.info(f"🔄 {len(self.subscriptions)}개 구독 재등록 중...")
        
        for tr_id, tr_key in self.subscriptions:
            await self.subscribe(tr_id, tr_key)
            await asyncio.sleep(0.1)  # 과부하 방지
    
    async def receive_messages(self):
        """메시지 수신"""
        async for raw in self.ws:
            try:
                # 데이터 메시지
                if raw[0] in ["0", "1"]:
                    parts = raw.split("|")
                    if len(parts) >= 4:
                        tr_id = parts[1]
                        data = parts[3]
                        
                        # 콜백 실행
                        if tr_id in self.callbacks:
                            self.callbacks[tr_id](data)
                
                # 시스템 메시지
                else:
                    msg = json.loads(raw)
                    
                    # PINGPONG
                    if msg.get("header", {}).get("tr_id") == "PINGPONG":
                        await self.ws.pong(raw)
            
            except Exception as e:
                logger.error(f"❌ 메시지 처리 오류: {e}")
    
    def register_callback(self, tr_id: str, callback):
        """콜백 등록"""
        self.callbacks[tr_id] = callback
        logger.info(f"✅ 콜백 등록: {tr_id}")
    
    def start(self):
        """웹소켓 시작"""
        self.is_running = True
        
        def run():
            asyncio.run(self.connect())
        
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        
        logger.info("🚀 웹소켓 스레드 시작")
    
    def stop(self):
        """웹소켓 중지"""
        self.is_running = False
        logger.info("⏹ 웹소켓 중지")


# ============================================================================
# 기술적 분석
# ============================================================================
class TechnicalAnalysis:
    """기술적 지표 계산"""
    
    @staticmethod
    def calculate_ma(prices: List[float], period: int) -> float:
        if len(prices) < period:
            return 0
        return sum(prices[-period:]) / period
    
    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> float:
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
        return 100 - (100 / (1 + rs))
    
    @staticmethod
    def calculate_bollinger(prices: List[float], period: int = 20, std_dev: float = 2.0) -> Tuple[float, float, float]:
        if len(prices) < period:
            return 0, 0, 0
        
        recent = prices[-period:]
        ma = sum(recent) / period
        variance = sum((x - ma) ** 2 for x in recent) / period
        std = variance ** 0.5
        
        upper = ma + (std * std_dev)
        lower = ma - (std * std_dev)
        
        return upper, ma, lower


# ============================================================================
# 시세 데이터 관리 (개선)
# ============================================================================
class MarketData:
    """실시간 시세 및 캔들 데이터"""
    
    def __init__(self):
        self.candle_builder = CandleBuilder(timeframe_minutes=5)
        self.strength_calc = StrengthCalculator()
        self.ta = TechnicalAnalysis()
        
        self.current_price = {}
        self.daily_data = {}  # 일봉 데이터
        
        logger.info("✅ MarketData 초기화")
    
    def on_tick(self, code: str, price: float, volume: int, timestamp: datetime = None):
        """실시간 체결 틱 처리"""
        if timestamp is None:
            timestamp = datetime.now()
        
        self.current_price[code] = price
        
        # 5분봉 생성
        completed_candle = self.candle_builder.add_tick(code, price, volume, timestamp)
        
        if completed_candle:
            logger.info(f"📊 {code} 5분봉 완성: {completed_candle['close']:,.0f}원 | Vol:{completed_candle['volume']:,}")
    
    def on_asking_price(self, code: str, asking_data: dict):
        """실시간 호가 처리"""
        # 체결강도 계산
        strength = self.strength_calc.calculate(code, asking_data)
        
        logger.debug(f"💪 {code} 체결강도: {strength:.1f}%")
    
    def check_entry_signal(self, code: str) -> Tuple[bool, str]:
        """진입 신호 (TIER 2)"""
        candles = self.candle_builder.get_candles(code)
        
        if len(candles) < 25:
            return False, "데이터 부족"
        
        current = candles[-1]
        
        # 거래량 급증
        avg_volume = self.candle_builder.get_recent_volume_avg(code, 20)
        if current['volume'] < avg_volume * Strategy.VOLUME_SPIKE:
            return False, "거래량 미달"
        
        # 체결강도 (연속 3개)
        if not self.strength_calc.check_consecutive_strength(code, Strategy.MIN_STRENGTH_3BARS, 3):
            return False, "체결강도 미달"
        
        # 양봉
        if current['close'] <= current['open']:
            return False, "음봉"
        
        # 캔들 실체
        body = abs(current['close'] - current['open'])
        total = current['high'] - current['low']
        if total > 0 and body / total < Strategy.MIN_CANDLE_BODY:
            return False, "긴 꼬리"
        
        # 연속 양봉
        green_count = sum(1 for c in candles[-3:] if c['close'] > c['open'])
        if green_count < Strategy.MIN_GREEN_CANDLES:
            return False, "연속 양봉 부족"
        
        # 2시간 고점 돌파
        recent_highs = [c['high'] for c in candles[-24:]]
        if current['close'] <= max(recent_highs[:-1]):
            return False, "고점 미돌파"
        
        logger.info(f"✅ {code} TIER 2 진입 신호!")
        return True, "진입"
    
    def check_exit_signal(self, code: str, position: dict) -> Tuple[bool, str]:
        """청산 신호 (TIER 4)"""
        current_price = self.current_price.get(code, 0)
        if current_price == 0:
            return False, ""
        
        buy_price = position['buy_price']
        profit_rate = (current_price - buy_price) / buy_price
        
        # 익절
        if profit_rate >= Strategy.BASE_PROFIT:
            return True, f"익절 {profit_rate:.2%}"
        
        # 트레일링 스톱
        if profit_rate >= Strategy.TRAILING_START:
            if current_price > position.get('peak_price', buy_price):
                position['peak_price'] = current_price
                position['trailing_active'] = True
            
            if position.get('trailing_active'):
                drop = (position['peak_price'] - current_price) / position['peak_price']
                if drop >= Strategy.TRAILING_OFFSET:
                    return True, f"트레일링 스톱"
        
        # 손절
        if profit_rate <= -Strategy.HARD_STOP:
            return True, f"하드 스톱 {profit_rate:.2%}"
        
        # 시간 청산
        elapsed = (datetime.now() - position['entry_time']).seconds
        if elapsed > Strategy.TIME_PROFIT_HOURS * 3600:
            if profit_rate >= Strategy.TIME_PROFIT_MIN:
                return True, f"시간 익절"
        
        if elapsed > Strategy.TIME_LOSS_HOURS * 3600:
            if profit_rate <= Strategy.TIME_LOSS_MAX:
                return True, f"시간 손절"
        
        return False, ""


# 이하 나머지 코드는 이전과 동일 (PerformanceTracker, KISAuth, OrderManager, TradingEnv, TelegramBot, AdvancedScalpingSystem, main)
# 너무 길어서 생략하고 핵심 개선사항만 포함

# ... (나머지 코드 계속)
