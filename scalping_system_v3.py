#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
한국투자증권 고급 스캘핑 자동매매 시스템 (Advanced Scalping Trading System)
===============================================================================

[전략 개요]
Multi-Layer Filtering + Dynamic Exit Strategy
- TIER 1: 종목 유니버스 필터링 (일일 1회)
- TIER 2: 실시간 진입 시그널 (5분봉)
- TIER 3: 지능형 주문 실행 (슬리피지 최소화)
- TIER 4: 동적 출구 전략 (트레일링 스톱)
- TIER 5: 다층 리스크 관리

[주요 기능]
- 국내주식 + 해외주식 동시 지원
- 15분봉/5분봉 기반 기술적 분석
- 거래량/체결강도/가격액션 복합 분석
- 텔레그램 봇 실시간 모니터링
- 포지션 사이징 및 리스크 관리
- 일일/주간/월간 성과 분석

Created: 2026-01-19
Author: GenSpark AI + SALBO-Y
Version: 3.0.0 (Advanced Scalping Strategy)
"""

import asyncio
import json
import logging
import os
import sys
import time
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import traceback

import pandas as pd
import numpy as np
import requests
import websockets
import yaml

# 기술적 분석 라이브러리
try:
    import pandas_ta as ta
    TA_AVAILABLE = True
except ImportError:
    TA_AVAILABLE = False
    print("⚠️  pandas_ta가 설치되지 않았습니다. 기술적 분석 기능이 제한됩니다.")
    print("설치: pip install pandas-ta")

# 텔레그램 봇
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("⚠️  python-telegram-bot이 설치되지 않았습니다.")
    print("설치: pip install python-telegram-bot")

from base64 import b64decode
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


# ============================================================================
# 전역 설정 및 로깅
# ============================================================================

# 로깅 설정
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{LOG_DIR}/scalping_system_{datetime.now().strftime("%Y%m%d")}.log', encoding='utf-8'),
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
    logger.error(f"❌ 설정 파일을 찾을 수 없습니다: {CONFIG_FILE}")
    sys.exit(1)

# 기본 헤더값
_base_headers = {
    "Content-Type": "application/json",
    "Accept": "text/plain",
    "charset": "UTF-8",
    "User-Agent": _cfg["my_agent"],
}


# ============================================================================
# 전략 파라미터 설정
# ============================================================================

class StrategyConfig:
    """전략 설정 클래스"""
    
    # TIER 1: 종목 유니버스 필터 (일일 1회)
    UNIVERSE_FILTER = {
        "min_market_cap": 50_000_000_000,  # 최소 시가총액 500억
        "min_daily_volume": 5_000_000_000,  # 최소 일평균 거래대금 50억
        "min_price": 5000,  # 최소 주가
        "max_price": 500_000,  # 최대 주가
        "min_days_since_listing": 90,  # 상장 후 최소 일수
    }
    
    # TIER 2: 실시간 진입 시그널
    ENTRY_SIGNAL = {
        # 거래량 분석
        "volume_spike_multiplier": 2.5,  # 직전 20봉 평균 대비 배수
        "volume_amount_multiplier": 3.0,  # 거래대금 급증 배수
        
        # 체결강도
        "min_consecutive_strength": 150,  # 연속 3봉 최소 체결강도
        "min_instant_strength": 300,  # 순간 체결강도
        
        # 가격 액션
        "min_candle_body_ratio": 0.6,  # 캔들 실체 비율
        "min_consecutive_green": 2,  # 최소 연속 양봉 수
    }
    
    # TIER 3: 주문 실행
    ORDER_EXECUTION = {
        "initial_price_offset": 0.002,  # 초기 주문 가격 오프셋 (+0.2%)
        "retry_price_offset": 0.005,  # 재주문 가격 오프셋 (+0.5%)
        "order_timeout": 2,  # 주문 타임아웃 (초)
    }
    
    # TIER 4: 출구 전략
    EXIT_STRATEGY = {
        "base_profit_rate": 0.03,  # 기본 익절 3%
        "trailing_start_rate": 0.05,  # 트레일링 스톱 시작 5%
        "trailing_offset_rate": 0.02,  # 트레일링 스톱 오프셋 2%
        
        "hard_stop_loss": 0.025,  # 하드 스톱 -2.5%
        "technical_stop_offset": 0.003,  # 기술적 스톱 오프셋
        
        "time_based_profit_hours": 2,  # 시간 기반 익절 (시간)
        "time_based_profit_min": 0.01,  # 시간 기반 최소 수익률
        
        "time_based_loss_hours": 1,  # 시간 기반 손절 (시간)
        "time_based_loss_max": -0.01,  # 시간 기반 최대 손실률
        
        "emergency_drop_rate": 0.015,  # 긴급 탈출 급락률 -1.5%
        "emergency_drop_seconds": 60,  # 긴급 탈출 시간 (초)
    }
    
    # TIER 5: 리스크 관리
    RISK_MANAGEMENT = {
        "capital_per_position": 0.02,  # 종목당 자본금 비율 2%
        "max_capital_per_position": 0.05,  # 최대 종목당 자본금 5%
        "max_concurrent_positions": 3,  # 최대 동시 보유 종목 수
        "max_daily_trades": 10,  # 일일 최대 거래 횟수
        
        "daily_loss_limit": 0.05,  # 일일 손실 한도 -5%
        "consecutive_loss_limit": 3,  # 연속 손절 한도
        "consecutive_loss_cooldown": 3600,  # 연속 손절 후 대기 시간 (초)
        
        "min_win_rate": 0.60,  # 최소 승률
        "max_drawdown": 0.10,  # 최대 MDD -10%
        "min_sharpe_ratio": 1.0,  # 최소 샤프 비율
    }
    
    # 시장 시간 설정
    MARKET_HOURS = {
        "domestic": {
            "start": "09:00",
            "end": "15:30",
            "avoid_start_minutes": 10,  # 장 시작 후 회피 시간
            "avoid_end_minutes": 30,  # 장 마감 전 회피 시간
        },
        "overseas": {
            "us": {
                "start": "23:30",  # 한국 시간 기준
                "end": "06:00",
            }
        }
    }
    
    # 시스템 설정
    SYSTEM = {
        "check_interval": 10,  # 상태 체크 주기 (초)
        "candle_update_interval": 60,  # 캔들 데이터 업데이트 주기 (초)
        "balance_update_interval": 30,  # 잔고 업데이트 주기 (초)
        "performance_save_interval": 300,  # 성과 저장 주기 (초)
    }


# ============================================================================
# 성과 추적 시스템
# ============================================================================

class PerformanceTracker:
    """성과 추적 및 분석 클래스"""
    
    def __init__(self):
        self.trades = []  # 전체 거래 내역
        self.daily_stats = defaultdict(lambda: {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "profit": 0.0,
            "volume": 0,
        })
        
        self.start_capital = 0
        self.current_capital = 0
        self.peak_capital = 0
        self.current_drawdown = 0
        self.max_drawdown = 0
        
        self.consecutive_losses = 0
        self.last_loss_time = None
    
    def record_trade(self, trade_data: Dict):
        """거래 기록"""
        self.trades.append({
            **trade_data,
            "timestamp": datetime.now()
        })
        
        date_key = datetime.now().strftime("%Y-%m-%d")
        stats = self.daily_stats[date_key]
        
        stats["trades"] += 1
        stats["volume"] += trade_data.get("amount", 0)
        
        profit_loss = trade_data.get("profit_loss", 0)
        stats["profit"] += profit_loss
        
        if profit_loss > 0:
            stats["wins"] += 1
            self.consecutive_losses = 0
        else:
            stats["losses"] += 1
            self.consecutive_losses += 1
            self.last_loss_time = datetime.now()
        
        # 자본금 업데이트
        self.current_capital += profit_loss
        
        # MDD 계산
        if self.current_capital > self.peak_capital:
            self.peak_capital = self.current_capital
        
        self.current_drawdown = (self.peak_capital - self.current_capital) / self.peak_capital
        self.max_drawdown = max(self.max_drawdown, self.current_drawdown)
        
        logger.info(f"📊 거래 기록: {trade_data['stock_code']} | "
                   f"손익: {profit_loss:+,.0f}원 ({trade_data.get('profit_rate', 0):.2%}) | "
                   f"누적: {stats['wins']}승 {stats['losses']}패")
    
    def get_win_rate(self) -> float:
        """승률 계산"""
        total_trades = len(self.trades)
        if total_trades == 0:
            return 0.0
        
        wins = sum(1 for t in self.trades if t.get("profit_loss", 0) > 0)
        return wins / total_trades
    
    def get_sharpe_ratio(self) -> float:
        """샤프 비율 계산"""
        if len(self.trades) < 2:
            return 0.0
        
        returns = [t.get("profit_rate", 0) for t in self.trades]
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        
        if std_return == 0:
            return 0.0
        
        return mean_return / std_return * np.sqrt(252)  # 연율화
    
    def get_daily_summary(self, date: str = None) -> Dict:
        """일일 요약"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        stats = self.daily_stats[date]
        
        win_rate = stats["wins"] / stats["trades"] if stats["trades"] > 0 else 0
        
        return {
            "date": date,
            "trades": stats["trades"],
            "wins": stats["wins"],
            "losses": stats["losses"],
            "win_rate": win_rate,
            "profit": stats["profit"],
            "volume": stats["volume"],
        }
    
    def should_stop_trading(self, config: StrategyConfig) -> Tuple[bool, str]:
        """거래 중단 여부 판단"""
        # 연속 손절 체크
        if self.consecutive_losses >= config.RISK_MANAGEMENT["consecutive_loss_limit"]:
            if self.last_loss_time:
                cooldown = config.RISK_MANAGEMENT["consecutive_loss_cooldown"]
                elapsed = (datetime.now() - self.last_loss_time).total_seconds()
                if elapsed < cooldown:
                    remaining = int(cooldown - elapsed)
                    return True, f"연속 손절 {self.consecutive_losses}회 - {remaining}초 대기 중"
        
        # 일일 손실 한도 체크
        today = datetime.now().strftime("%Y-%m-%d")
        daily_profit = self.daily_stats[today]["profit"]
        daily_loss_limit = self.start_capital * config.RISK_MANAGEMENT["daily_loss_limit"]
        
        if daily_profit < -daily_loss_limit:
            return True, f"일일 손실 한도 초과: {daily_profit:,.0f}원"
        
        # 승률 체크
        win_rate = self.get_win_rate()
        if len(self.trades) >= 10 and win_rate < config.RISK_MANAGEMENT["min_win_rate"]:
            return True, f"승률 미달: {win_rate:.1%} < {config.RISK_MANAGEMENT['min_win_rate']:.1%}"
        
        # MDD 체크
        if self.max_drawdown > config.RISK_MANAGEMENT["max_drawdown"]:
            return True, f"최대 낙폭 초과: {self.max_drawdown:.1%}"
        
        return False, ""
    
    def save_to_file(self):
        """성과를 파일로 저장"""
        try:
            os.makedirs("performance", exist_ok=True)
            
            # 거래 내역 저장
            trades_df = pd.DataFrame(self.trades)
            filename = f"performance/trades_{datetime.now().strftime('%Y%m%d')}.csv"
            trades_df.to_csv(filename, index=False, encoding='utf-8-sig')
            
            # 일일 통계 저장
            daily_stats_list = []
            for date, stats in self.daily_stats.items():
                daily_stats_list.append({
                    "date": date,
                    **stats,
                    "win_rate": stats["wins"] / stats["trades"] if stats["trades"] > 0 else 0
                })
            
            daily_df = pd.DataFrame(daily_stats_list)
            filename = f"performance/daily_stats_{datetime.now().strftime('%Y%m%d')}.csv"
            daily_df.to_csv(filename, index=False, encoding='utf-8-sig')
            
            logger.info(f"✅ 성과 데이터 저장 완료")
        
        except Exception as e:
            logger.error(f"❌ 성과 저장 실패: {e}")


# 다음 파일에서 계속...
# 이 파일이 너무 길어져서 모듈을 분리해야 합니다.
