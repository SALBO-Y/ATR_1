"""
실전 트레이딩을 위한 핵심 모듈
- 5분봉 자동 생성
- 웹소켓 재연결
- 체결강도 계산
"""

import logging
import asyncio
import websockets
import json
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from collections import deque

logger = logging.getLogger(__name__)


# ============================================================================
# 1. 5분봉 자동 생성기
# ============================================================================
class CandleBuilder:
    """
    실시간 체결가로 5분봉 자동 생성
    
    Usage:
        builder = CandleBuilder(timeframe_minutes=5)
        
        # 체결 틱 추가
        completed_candle = builder.add_tick(
            code="005930",
            price=60000,
            volume=100,
            timestamp=datetime.now()
        )
        
        if completed_candle:
            print(f"캔들 완성: {completed_candle}")
        
        # 완성된 캔들 조회
        candles = builder.get_candles("005930", count=20)
    """
    
    def __init__(self, timeframe_minutes=5):
        self.timeframe = timeframe_minutes
        self.candles = {}  # {종목코드: deque(캔들)}
        self.current_candles = {}  # {종목코드: 현재 캔들}
        self.candle_start_times = {}
        
        logger.info(f"✅ CandleBuilder 초기화 ({timeframe_minutes}분봉)")
    
    def add_tick(self, code: str, price: float, volume: int, 
                 timestamp: datetime = None) -> Optional[Dict]:
        """
        체결 틱 추가
        
        Returns:
            완성된 캔들 (있으면) 또는 None
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # 캔들 시작 시간 계산
        minute = timestamp.minute
        candle_minute = (minute // self.timeframe) * self.timeframe
        candle_start = timestamp.replace(
            minute=candle_minute, second=0, microsecond=0
        )
        
        # 종목 초기화
        if code not in self.candles:
            self.candles[code] = deque(maxlen=200)
        
        # 새 캔들 시작
        if (code not in self.current_candles or 
            self.candle_start_times.get(code) != candle_start):
            
            # 기존 캔들 완성
            completed_candle = None
            if code in self.current_candles:
                completed_candle = self.current_candles[code].copy()
                self.candles[code].append(completed_candle)
                
                logger.info(
                    f"✅ {code} 캔들 완성 | "
                    f"시간:{completed_candle['time'].strftime('%H:%M')} | "
                    f"O:{completed_candle['open']:,.0f} "
                    f"H:{completed_candle['high']:,.0f} "
                    f"L:{completed_candle['low']:,.0f} "
                    f"C:{completed_candle['close']:,.0f} "
                    f"V:{completed_candle['volume']:,}"
                )
            
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
    
    def get_candles(self, code: str, count: int = None) -> List[Dict]:
        """완성된 캔들 조회"""
        if code not in self.candles:
            return []
        
        candles = list(self.candles[code])
        if count:
            return candles[-count:]
        return candles
    
    def get_recent_volume_avg(self, code: str, periods: int = 20) -> float:
        """최근 N개 평균 거래량"""
        candles = self.get_candles(code, periods)
        if len(candles) < periods:
            return 0
        
        return sum(c['volume'] for c in candles) / len(candles)
    
    def get_latest_candle(self, code: str) -> Optional[Dict]:
        """최신 완성 캔들"""
        candles = self.get_candles(code, 1)
        return candles[0] if candles else None


# ============================================================================
# 2. 체결강도 계산기
# ============================================================================
class StrengthCalculator:
    """
    호가창 데이터로 체결강도 정확 계산
    
    Usage:
        calc = StrengthCalculator()
        
        # 실시간 호가 데이터 입력
        asking_data = {
            'ASKP_RSQN1': 1000,  # 매도 호가 잔량
            'ASKP_RSQN2': 2000,
            ...
            'BIDP_RSQN1': 3000,  # 매수 호가 잔량
            'BIDP_RSQN2': 4000,
            ...
        }
        
        strength = calc.calculate("005930", asking_data)
        print(f"체결강도: {strength:.1f}%")
        
        # 연속 3개 체결강도 체크
        if calc.check_consecutive_strength("005930", min_strength=150, periods=3):
            print("매수세 강함!")
    """
    
    def __init__(self):
        self.strength_history = {}  # {종목코드: deque(체결강도)}
        logger.info("✅ StrengthCalculator 초기화")
    
    def calculate(self, code: str, asking_data: Dict) -> float:
        """
        체결강도 계산
        
        Args:
            asking_data: 실시간 호가 데이터
                - ASKP_RSQN1~10: 매도 호가 잔량
                - BIDP_RSQN1~10: 매수 호가 잔량
        
        Returns:
            체결강도 (%)
            - 100 미만: 매도세 강함
            - 100: 중립
            - 100 초과: 매수세 강함
        """
        try:
            # 매도 잔량 합계
            ask_volume = sum(
                int(asking_data.get(f'ASKP_RSQN{i}', 0) or 0)
                for i in range(1, 11)
            )
            
            # 매수 잔량 합계
            bid_volume = sum(
                int(asking_data.get(f'BIDP_RSQN{i}', 0) or 0)
                for i in range(1, 11)
            )
            
            # 체결강도 = (매수 / 매도) × 100
            if ask_volume == 0:
                strength = 200  # 매도 없으면 강세
            elif bid_volume == 0:
                strength = 0  # 매수 없으면 약세
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
            
            logger.debug(
                f"💪 {code} 체결강도: {strength:.1f}% | "
                f"매수:{bid_volume:,} / 매도:{ask_volume:,}"
            )
            
            return strength
        
        except Exception as e:
            logger.error(f"❌ 체결강도 계산 오류 ({code}): {e}")
            return 100
    
    def get_average_strength(self, code: str, periods: int = 3) -> float:
        """최근 N개 평균 체결강도"""
        if code not in self.strength_history:
            return 100
        
        history = list(self.strength_history[code])
        if len(history) == 0:
            return 100
        
        recent = history[-periods:]
        return sum(s['strength'] for s in recent) / len(recent)
    
    def check_consecutive_strength(self, code: str, 
                                   min_strength: float = 150, 
                                   periods: int = 3) -> bool:
        """
        연속 N개 체결강도 체크
        
        Returns:
            True if 최근 N개가 모두 min_strength 이상
        """
        if code not in self.strength_history:
            return False
        
        history = list(self.strength_history[code])
        if len(history) < periods:
            return False
        
        recent = history[-periods:]
        return all(s['strength'] >= min_strength for s in recent)
    
    def get_history(self, code: str, count: int = 10) -> List[Dict]:
        """체결강도 이력 조회"""
        if code not in self.strength_history:
            return []
        
        return list(self.strength_history[code])[-count:]


# ============================================================================
# 3. 웹소켓 자동 재연결 클라이언트
# ============================================================================
class ReconnectableWebSocket:
    """
    자동 재연결 웹소켓 클라이언트
    
    Usage:
        ws_client = ReconnectableWebSocket(env)
        
        # 콜백 등록
        def on_tick(data):
            print(f"체결: {data}")
        
        ws_client.register_callback("H0STCNT0", on_tick)
        
        # 웹소켓 시작
        ws_client.start()
        
        # 구독 추가 (비동기)
        await ws_client.subscribe("H0STCNT0", "005930")
    """
    
    def __init__(self, env, max_reconnect=5, reconnect_delay=5):
        self.env = env
        self.ws = None
        self.is_running = False
        
        # 콜백 및 구독 관리
        self.callbacks = {}
        self.subscriptions = []  # [(tr_id, tr_key), ...]
        
        # 재연결 설정
        self.max_reconnect = max_reconnect
        self.reconnect_delay = reconnect_delay
        
        logger.info("✅ ReconnectableWebSocket 초기화")
    
    async def connect(self):
        """웹소켓 연결 (자동 재연결)"""
        reconnect_count = 0
        
        while self.is_running and reconnect_count < self.max_reconnect:
            try:
                url = self.env.ws_url
                logger.info(
                    f"🔌 웹소켓 연결 시도... "
                    f"({reconnect_count + 1}/{self.max_reconnect})"
                )
                
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=10
                ) as ws:
                    self.ws = ws
                    reconnect_count = 0  # 성공 시 리셋
                    
                    logger.info("✅ 웹소켓 연결 성공")
                    
                    # 기존 구독 재등록
                    if self.subscriptions:
                        await self.resubscribe()
                    
                    # 메시지 수신
                    await self.receive_messages()
            
            except websockets.exceptions.ConnectionClosed:
                logger.warning("⚠️ 웹소켓 연결 끊김")
                reconnect_count += 1
                
                if reconnect_count < self.max_reconnect:
                    logger.info(f"🔄 {self.reconnect_delay}초 후 재연결...")
                    await asyncio.sleep(self.reconnect_delay)
            
            except Exception as e:
                logger.error(f"❌ 웹소켓 오류: {e}")
                reconnect_count += 1
                await asyncio.sleep(self.reconnect_delay)
        
        if reconnect_count >= self.max_reconnect:
            logger.error("❌ 최대 재연결 횟수 초과")
    
    async def subscribe(self, tr_id: str, tr_key: str):
        """종목 구독"""
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
        subscription = (tr_id, tr_key)
        if subscription not in self.subscriptions:
            self.subscriptions.append(subscription)
        
        logger.info(f"📡 구독: {tr_id} - {tr_key}")
    
    async def unsubscribe(self, tr_id: str, tr_key: str):
        """구독 해제"""
        if not self.ws:
            return
        
        msg = {
            "header": {
                "approval_key": self.env.ws_key,
                "custtype": "P",
                "tr_type": "2",  # 구독 해제
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
        
        # 구독 목록에서 제거
        subscription = (tr_id, tr_key)
        if subscription in self.subscriptions:
            self.subscriptions.remove(subscription)
        
        logger.info(f"📡 구독 해제: {tr_id} - {tr_key}")
    
    async def resubscribe(self):
        """재연결 시 구독 재등록"""
        logger.info(f"🔄 {len(self.subscriptions)}개 구독 재등록...")
        
        for tr_id, tr_key in self.subscriptions:
            await self.subscribe(tr_id, tr_key)
            await asyncio.sleep(0.1)  # 과부하 방지
    
    async def receive_messages(self):
        """메시지 수신 처리"""
        async for raw in self.ws:
            try:
                # 데이터 메시지
                if raw[0] in ["0", "1"]:
                    parts = raw.split("|")
                    if len(parts) >= 4:
                        tr_id = parts[1]
                        data_str = parts[3]
                        
                        # 콜백 실행
                        if tr_id in self.callbacks:
                            self.callbacks[tr_id](data_str)
                
                # 시스템 메시지
                else:
                    msg = json.loads(raw)
                    
                    # PINGPONG
                    if msg.get("header", {}).get("tr_id") == "PINGPONG":
                        await self.ws.pong(raw)
                        logger.debug("🏓 PINGPONG")
            
            except Exception as e:
                logger.error(f"❌ 메시지 처리 오류: {e}")
    
    def register_callback(self, tr_id: str, callback):
        """콜백 함수 등록"""
        self.callbacks[tr_id] = callback
        logger.info(f"✅ 콜백 등록: {tr_id}")
    
    def start(self):
        """웹소켓 시작 (별도 스레드)"""
        import threading
        
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
# 사용 예시
# ============================================================================
if __name__ == "__main__":
    # 5분봉 생성 예시
    builder = CandleBuilder(timeframe_minutes=5)
    
    # 체결 틱 추가
    for i in range(100):
        candle = builder.add_tick(
            code="005930",
            price=60000 + i * 10,
            volume=100,
            timestamp=datetime.now()
        )
        
        if candle:
            print(f"완성 캔들: {candle}")
    
    # 체결강도 계산 예시
    calc = StrengthCalculator()
    
    asking_data = {
        'ASKP_RSQN1': 1000,
        'ASKP_RSQN2': 2000,
        'BIDP_RSQN1': 3000,
        'BIDP_RSQN2': 4000,
    }
    
    strength = calc.calculate("005930", asking_data)
    print(f"체결강도: {strength:.1f}%")
