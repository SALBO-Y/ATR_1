"""
=============================================================================
SALBO ATS Trading Bot - v5 Real
실전계좌 + KIS 공식 마스터 파일 + DRY_RUN 모드

주요 개선사항 (v4 → v5):
1. ✅ KIS 공식 마스터 파일 다운로드 (KOSPI/KOSDAQ)
2. ✅ DRY_RUN 모드 (주문 없이 스캔만 테스트)
3. ✅ 실전계좌 지원 (IS_PAPER_TRADING=false)
4. ✅ 종목 필터링 개선 (ETF/우선주/관리종목 제외)
5. ✅ 캐시 및 로그 시스템 강화

사용 방법:
    # 1. DRY_RUN 모드 (주문 없이 스캔만)
    python main_v5_real.py --dry-run
    
    # 2. 실전 자동매매
    python main_v5_real.py
    
    # 3. 삼성전자 10주 테스트 (주문 실행)
    python main_v5_real.py --test-buy

중지:
    Ctrl+C

버전: v5.0 Real (2026-01-09)
=============================================================================
"""

import os
import sys
import asyncio
import signal
import json
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.connection import create_connection
import pandas as pd
import urllib.request
import zipfile
import ssl
import socket
from datetime import datetime as dt, time as dtime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import deque
import logging
from logging.handlers import RotatingFileHandler

# IPv4 강제 설정 (IPv6 문제 해결)
def _create_connection_ipv4_only(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
    """IPv4만 사용하도록 강제하는 소켓 생성 함수"""
    host, port = address
    err = None
    for res in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
        af, socktype, proto, canonname, sa = res
        sock = None
        try:
            sock = socket.socket(af, socktype, proto)
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(sa)
            return sock
        except socket.error as _:
            err = _
            if sock is not None:
                sock.close()
    if err is not None:
        raise err
    else:
        raise socket.error("getaddrinfo returns an empty list")

# IPv4 강제 적용
create_connection_original = create_connection
create_connection = _create_connection_ipv4_only

# Windows 콘솔 UTF-8 인코딩
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# .env 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️  python-dotenv not installed")

# =============================================================================
# [1] 설정
# =============================================================================

class Config:
    """통합 설정"""
    
    # 모의/실전 선택
    IS_PAPER_TRADING = os.getenv("IS_PAPER_TRADING", "true").lower() == "true"
    DRY_RUN_MODE = os.getenv("DRY_RUN_MODE", "false").lower() == "true"  # 주문 없이 스캔만
    
    # API URL
    REAL_URL_BASE = "https://openapi.koreainvestment.com:9943"
    PAPER_URL_BASE = "https://openapivts.koreainvestment.com:29443"
    URL_BASE = PAPER_URL_BASE if IS_PAPER_TRADING else REAL_URL_BASE
    
    # WebSocket URL
    REAL_WS_URL = "ws://ops.koreainvestment.com:21000"
    PAPER_WS_URL = "ws://ops.koreainvestment.com:31000"
    WS_URL = PAPER_WS_URL if IS_PAPER_TRADING else REAL_WS_URL
    
    # API 인증
    APP_KEY = os.getenv("KIS_APP_KEY", "")
    APP_SECRET = os.getenv("KIS_APP_SECRET", "")
    
    # 계좌 (자동 선택)
    if IS_PAPER_TRADING:
        ACC_NO = os.getenv("KIS_PAPER_ACC_NO", "")
        ACC_PRDT_CD = os.getenv("KIS_PAPER_ACC_PRDT_CD", "01")
    else:
        ACC_NO = os.getenv("KIS_REAL_ACC_NO", "")
        ACC_PRDT_CD = os.getenv("KIS_REAL_ACC_PRDT_CD", "01")
    
    # 텔레그램
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
    TELEGRAM_ENABLED = TELEGRAM_TOKEN and TELEGRAM_CHAT_ID
    
    # 거래 설정
    MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "2"))
    RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.02"))
    MAX_ACCOUNT_RISK = float(os.getenv("MAX_ACCOUNT_RISK", "0.06"))
    
    # API 속도 제한
    API_CALL_LIMIT = int(os.getenv("API_CALL_LIMIT", "20"))
    API_CALL_PERIOD = float(os.getenv("API_CALL_PERIOD", "1.0"))
    
    # 전략 파라미터
    VOLUME_SURGE_THRESHOLD = float(os.getenv("VOLUME_SURGE_THRESHOLD", "3.0"))
    MOMENTUM_STRENGTH_MIN = 120.0
    MOMENTUM_AB_RATIO_MIN = 1.5
    STOP_LOSS_MIN = 0.97
    
    # 트레일링
    TRAILING_ACTIVATION = 2.5
    TRAILING_RATE_LOW = 0.985
    TRAILING_RATE_HIGH = 0.99
    TRAILING_THRESHOLD = 4.0
    
    # WebSocket
    USE_WEBSOCKET = os.getenv("USE_WEBSOCKET", "true").lower() == "true"
    USE_EXECUTION_NOTIFIER = os.getenv("USE_EXECUTION_NOTIFIER", "true").lower() == "true"
    
    # HTS ID (체결통보용)
    HTS_ID = os.getenv("KIS_HTS_ID", "")
    
    # 스캔 설정
    SCAN_MODE = "all"
    SCAN_BATCH_SIZE = int(os.getenv("SCAN_BATCH_SIZE", "20"))
    VOLUME_CACHE_TTL = 300
    
    # 로깅
    LOG_DIR = Path("logs")
    LOG_DIR.mkdir(exist_ok=True)
    
    # TR_ID 자동 선택
    @classmethod
    def get_tr_id(cls, tr_type: str) -> str:
        """TR_ID 자동 선택"""
        common = {
            'price': 'FHKST01010100',
            'askbid': 'FHKST01010200',
            'chart': 'FHKST03010100',
            'stock_info': 'CTPF1604R',  # 종목정보조회 (실전만)
        }
        
        if tr_type in common:
            return common[tr_type]
        
        if cls.IS_PAPER_TRADING:
            trading = {
                'buy': 'VTTC0802U',
                'sell': 'VTTC0801U',
                'balance': 'VTTC8908R',
                'execution_notify': 'H0STCNI9',  # 모의투자 체결통보
            }
        else:
            trading = {
                'buy': 'TTTC0802U',
                'sell': 'TTTC0801U',
                'balance': 'TTTC8908R',
                'execution_notify': 'H0STCNI0',  # 실전 체결통보
            }
        
        return trading.get(tr_type, '')
    
    @classmethod
    def validate(cls):
        """설정 검증"""
        errors = []
        
        if not cls.APP_KEY:
            errors.append("❌ KIS_APP_KEY required")
        if not cls.APP_SECRET:
            errors.append("❌ KIS_APP_SECRET required")
        if not cls.ACC_NO:
            errors.append(f"❌ {'KIS_PAPER_ACC_NO' if cls.IS_PAPER_TRADING else 'KIS_REAL_ACC_NO'} required")
        
        if errors:
            print("\n⚠️  Configuration Errors:")
            for err in errors:
                print(f"  {err}")
            raise ValueError("Check .env file")
        
        print("=" * 70)
        print(f"🤖 SALBO ATS v4 - {'🧪 PAPER' if cls.IS_PAPER_TRADING else '💰 REAL'} TRADING")
        print("=" * 70)
        print(f"{'🔗 REST API:':<20} {cls.URL_BASE}")
        print(f"{'⚡ WebSocket:':<20} {'✅ Enabled' if cls.USE_WEBSOCKET else '❌ Disabled'}")
        print(f"{'💼 Account:':<20} {cls.ACC_NO}")
        print(f"{'📈 Max Positions:':<20} {cls.MAX_POSITIONS}")
        print(f"{'🎯 Scan Mode:':<20} FULL MARKET (실제 API)")
        print(f"{'📊 Batch Size:':<20} {cls.SCAN_BATCH_SIZE} stocks/batch")
        print(f"{'🔥 Volume Surge:':<20} {cls.VOLUME_SURGE_THRESHOLD}x average")
        print("=" * 70)
        print()


# =============================================================================
# [2] 로깅
# =============================================================================

def setup_logging():
    """로깅 설정"""
    logger = logging.getLogger('TradingBot')
    logger.setLevel(logging.INFO)
    
    fh = RotatingFileHandler(
        Config.LOG_DIR / 'trading.log',
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding='utf-8'
    )
    fh.setLevel(logging.INFO)
    
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    
    fmt = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger

logger = setup_logging()


# =============================================================================
# [3] Rate Limiter
# =============================================================================

class RateLimiter:
    """API 속도 제한"""
    
    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self.calls = deque()
    
    def __call__(self, func):
        def wrapper(*args, **kwargs):
            now = time.time()
            
            while self.calls and self.calls[0] <= now - self.period:
                self.calls.popleft()
            
            if len(self.calls) >= self.max_calls:
                sleep_time = self.period - (now - self.calls[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
            
            self.calls.append(time.time())
            return func(*args, **kwargs)
        
        return wrapper

rate_limiter = RateLimiter(Config.API_CALL_LIMIT, Config.API_CALL_PERIOD)


# =============================================================================
# [4] 텔레그램
# =============================================================================

class TelegramNotifier:
    """텔레그램 알림"""
    
    def __init__(self):
        self.enabled = Config.TELEGRAM_ENABLED
        self.token = Config.TELEGRAM_TOKEN
        self.chat_id = Config.TELEGRAM_CHAT_ID
    
    async def send(self, message: str):
        """메시지 전송"""
        if not self.enabled:
            return
        
        try:
            import aiohttp
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            
            async with aiohttp.ClientSession() as session:
                await session.post(url, json=payload)
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

telegram = TelegramNotifier()


# =============================================================================
# [5] API 클라이언트
# =============================================================================

class KISApiClient:
    """한국투자증권 API"""
    
    def __init__(self):
        self.access_token = None
        self.token_expired = 0
    
    @rate_limiter
    def get_access_token(self):
        """토큰 발급"""
        now = time.time()
        
        if self.access_token and now < self.token_expired:
            return self.access_token
        
        url = f"{Config.URL_BASE}/oauth2/tokenP"  # KIS 공식: /oauth2/tokenP (P 필수!)
        body = {
            "grant_type": "client_credentials",
            "appkey": Config.APP_KEY,
            "appsecret": Config.APP_SECRET
        }
        
        try:
            res = requests.post(url, json=body, timeout=10)
            res.raise_for_status()
            
            data = res.json()
            self.access_token = data["access_token"]
            self.token_expired = now + (23 * 3600)
            
            logger.info("✅ Token obtained")
            return self.access_token
        
        except Exception as e:
            logger.error(f"❌ Token failed: {e}")
            raise
    
    def _get_header(self, tr_id: str) -> dict:
        """헤더 생성"""
        return {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": Config.APP_KEY,
            "appsecret": Config.APP_SECRET,
            "tr_id": tr_id,
            "custtype": "P"
        }
    
    @rate_limiter
    def _request(self, method: str, path: str, tr_id: str, **kwargs):
        """공통 요청"""
        url = f"{Config.URL_BASE}{path}"
        headers = self._get_header(tr_id)
        
        try:
            if method == "GET":
                res = requests.get(url, headers=headers, timeout=10, **kwargs)
            else:
                res = requests.post(url, headers=headers, timeout=10, **kwargs)
            
            res.raise_for_status()
            return res.json()
        
        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ HTTP {e.response.status_code}: {path}")
            raise
        except Exception as e:
            logger.error(f"❌ Request failed: {path} - {e}")
            raise
    
    def get_account_balance(self) -> float:
        """잔고 조회"""
        path = "/uapi/domestic-stock/v1/trading/inquire-psbl-order"
        tr_id = Config.get_tr_id('balance')
        
        params = {
            "CANO": Config.ACC_NO,
            "ACNT_PRDT_CD": Config.ACC_PRDT_CD,
            "PDNO": "005930",
            "ORD_UNPR": "0",
            "ORD_DVSN": "01",
            "CMA_EVLU_AMT_ICLD_YN": "Y",
            "OVRS_ICLD_YN": "N"
        }
        
        try:
            data = self._request("GET", path, tr_id, params=params)
            
            if 'output' not in data:
                logger.error(f"❌ Unexpected response: {list(data.keys())}")
                return 0
            
            output = data['output']
            
            for field in ['ord_psbl_cash', 'ord_able_cash', 'nrcvb_buy_amt']:
                if field in output:
                    balance = float(output[field])
                    logger.info(f"💰 Balance: {balance:,.0f}원")
                    return balance
            
            logger.warning(f"⚠️  Balance fields not found")
            return 0
        
        except Exception as e:
            logger.error(f"❌ Get balance failed: {e}")
            return 0
    
    def get_current_price(self, code: str) -> dict:
        """현재가 조회"""
        path = "/uapi/domestic-stock/v1/quotations/inquire-price"
        tr_id = Config.get_tr_id('price')
        
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": code
        }
        
        data = self._request("GET", path, tr_id, params=params)
        output = data['output']
        
        return {
            'price': float(output['stck_prpr']),
            'volume': int(output.get('acml_vol', 0)),
            'strength': float(output.get('stck_cntg_strn', 0))
        }
    
    def get_ohlcv(self, code: str, period: str = "D", count: int = 100) -> pd.DataFrame:
        """OHLCV 조회"""
        path = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        tr_id = Config.get_tr_id('chart')
        
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": code,
            "fid_input_date_1": "",
            "fid_input_date_2": "",
            "fid_period_div_code": period,
            "fid_org_adj_prc": "0"
        }
        
        data = self._request("GET", path, tr_id, params=params)
        output = data.get('output2', [])
        
        if not output:
            raise ValueError(f"No data for {code}")
        
        df = pd.DataFrame(output[:count])
        df = df[['stck_bsop_date', 'stck_clpr', 'stck_hgpr', 'stck_lwpr', 'stck_oprc', 'acml_vol']]
        df.columns = ['date', 'close', 'high', 'low', 'open', 'volume']
        
        for col in ['close', 'high', 'low', 'open', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df.iloc[::-1].reset_index(drop=True)
    
    def buy_order(self, code: str, qty: int) -> dict:
        """시장가 매수"""
        path = "/uapi/domestic-stock/v1/trading/order-cash"
        tr_id = Config.get_tr_id('buy')
        
        body = {
            "CANO": Config.ACC_NO,
            "ACNT_PRDT_CD": Config.ACC_PRDT_CD,
            "PDNO": code,
            "ORD_DVSN": "01",
            "ORD_QTY": str(qty),
            "ORD_UNPR": "0"
        }
        
        data = self._request("POST", path, tr_id, data=json.dumps(body))
        
        if data.get("rt_cd") == "0":
            logger.info(f"✅ Buy: {code} {qty}주")
        else:
            logger.error(f"❌ Buy failed: {data.get('msg1')}")
        
        return data
    
    def sell_order(self, code: str, qty: int) -> dict:
        """시장가 매도"""
        path = "/uapi/domestic-stock/v1/trading/order-cash"
        tr_id = Config.get_tr_id('sell')
        
        body = {
            "CANO": Config.ACC_NO,
            "ACNT_PRDT_CD": Config.ACC_PRDT_CD,
            "PDNO": code,
            "ORD_DVSN": "01",
            "ORD_QTY": str(qty),
            "ORD_UNPR": "0"
        }
        
        data = self._request("POST", path, tr_id, data=json.dumps(body))
        
        if data.get("rt_cd") == "0":
            logger.info(f"✅ Sell: {code} {qty}주")
        else:
            logger.error(f"❌ Sell failed: {data.get('msg1')}")
        
        return data


    def get_websocket_key(self) -> Optional[str]:
        """WebSocket 접속키 발급"""
        try:
            path = "/oauth2/Approval"
            headers = {
                "content-type": "application/json; charset=utf-8"
            }
            
            body = {
                "grant_type": "client_credentials",
                "appkey": Config.APP_KEY,
                "secretkey": Config.APP_SECRET
            }
            
            response = requests.post(
                f"{Config.URL_BASE}{path}",
                headers=headers,
                json=body,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                approval_key = data.get("approval_key")
                
                if approval_key:
                    logger.info("✅ WebSocket key obtained")
                    return approval_key
            
            logger.error(f"❌ WebSocket key failed: {response.status_code}")
            return None
        
        except Exception as e:
            logger.error(f"❌ WebSocket key error: {e}")
            return None


api_client = KISApiClient()


# =============================================================================
# [6] 거래량 급증 감지
# =============================================================================

class VolumeAnalyzer:
    """거래량 급증 감지"""
    
    def __init__(self):
        self.volume_cache = {}
    
    def is_volume_surge(self, code: str, current_volume: int) -> Tuple[bool, float]:
        """거래량 급증 여부"""
        try:
            avg_volume = self._get_average_volume(code)
            
            if avg_volume == 0:
                return False, 0
            
            surge_ratio = current_volume / avg_volume
            threshold = Config.VOLUME_SURGE_THRESHOLD
            
            if surge_ratio >= threshold:
                logger.info(f"🔥 Volume surge: {code} ({surge_ratio:.1f}배)")
                return True, surge_ratio
            
            return False, surge_ratio
        
        except Exception as e:
            logger.debug(f"Volume surge check failed [{code}]: {e}")
            return False, 0
    
    def _get_average_volume(self, code: str) -> int:
        """평균 거래량 (캐시)"""
        if code in self.volume_cache:
            cached = self.volume_cache[code]
            if time.time() - cached['time'] < Config.VOLUME_CACHE_TTL:
                return cached['avg']
        
        try:
            df = api_client.get_ohlcv(code, period="D", count=5)
            
            if df is None or len(df) < 3:
                return 0
            
            avg_volume = int(df['volume'].iloc[-3:].mean())
            
            self.volume_cache[code] = {
                'avg': avg_volume,
                'time': time.time()
            }
            
            return avg_volume
        
        except Exception as e:
            logger.debug(f"Get avg volume failed [{code}]: {e}")
            return 0

volume_analyzer = VolumeAnalyzer()

# =============================================================================
# [5.5] 실시간 체결통보
# =============================================================================

class ExecutionNotifier:
    """실시간 체결통보 WebSocket"""
    
    def __init__(self):
        self.ws = None
        self.approval_key = None
        self.is_connected = False
        self.reconnect_delay = 5
        self.last_key_time = 0
        self.key_ttl = 23 * 3600  # 23시간
    
    async def ensure_approval_key(self):
        """접속키 확인 및 갱신"""
        now = time.time()
        
        if self.approval_key and (now - self.last_key_time < self.key_ttl):
            return True
        
        logger.info("🔑 Getting WebSocket approval key...")
        self.approval_key = api_client.get_websocket_key()
        
        if self.approval_key:
            self.last_key_time = now
            return True
        
        return False
    
    async def connect_and_subscribe(self):
        """연결 및 체결통보 구독 (v5.1: 재시도 로직 추가)"""
        max_retries = 3
        retry_delay = 5  # 초
        
        for attempt in range(max_retries):
            try:
                import websockets
                
                if not await self.ensure_approval_key():
                    logger.error("❌ No approval key")
                    return
                
                logger.info(f"🔌 Connecting to {Config.WS_URL} (attempt {attempt+1}/{max_retries})...")
                
                async with websockets.connect(Config.WS_URL, ping_interval=None) as ws:
                    self.ws = ws
                    self.is_connected = True
                    
                    # 체결통보 등록
                    tr_id = Config.get_tr_id('execution_notify')
                    tr_key = f"{Config.ACC_NO}{Config.ACC_PRDT_CD}"
                    
                    register_msg = {
                        "header": {
                            "approval_key": self.approval_key,
                            "custtype": "P",
                            "tr_type": "1",
                            "content-type": "utf-8"
                        },
                        "body": {
                            "input": {
                                "tr_id": tr_id,
                                "tr_key": tr_key
                            }
                        }
                    }
                    
                    await ws.send(json.dumps(register_msg))
                    logger.info(f"✅ Subscribed execution notify: {tr_id} ({tr_key})")
                    
                    # 데이터 수신 루프
                    while True:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=30)
                            await self._handle_message(msg)
                        
                        except asyncio.TimeoutError:
                            continue
                        
                        except Exception as e:
                            logger.error(f"Receive error: {e}")
                            break
        
            except Exception as e:
                logger.error(f"❌ WebSocket error (attempt {attempt+1}/{max_retries}): {e}")
                
                if attempt < max_retries - 1:
                    logger.info(f"🔄 Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    
                    # 승인키 재발급 시도
                    self.approval_key = None
                    logger.info("🔑 Refreshing approval key...")
                else:
                    logger.error("❌ Max retries reached. WebSocket connection failed.")
                    raise
            
            finally:
                self.is_connected = False
                self.ws = None
    
    async def _handle_message(self, msg: str):
        """메시지 처리 (v5.1: 체결여부 구분 추가)"""
        try:
            data = json.loads(msg)
            
            if 'body' not in data:
                return
            
            output = data.get('body', {}).get('output', {})
            
            if not output:
                return
            
            # ★ 체결여부(CNTG_YN) 확인 (KIS 공식 샘플 기반)
            cntg_yn = output.get('CNTG_YN', '')
            
            if cntg_yn == "1":
                # 주문 접수 통보 (체결 전)
                logger.debug("📝 주문 접수 통보 (체결 대기)")
                return
            elif cntg_yn != "2":
                # 알 수 없는 상태
                logger.debug(f"⚠️ 알 수 없는 체결여부: {cntg_yn}")
                return
            
            # cntg_yn == "2": 실제 체결 통보만 처리
            
            # 필드 추출 (KIS 공식 샘플 컴럼 명세 기반)
            # 0:CUST_ID, 1:ACNT_NO, 2:ODER_NO, 3:ODER_QTY, 4:SELN_BYOV_CLS(매도매수),
            # 5:RCTF_CLS, 6:ODER_KIND, 7:ODER_COND, 8:STCK_SHRN_ISCD(종목코드),
            # 9:CNTG_QTY(체결수량), 10:CNTG_UNPR(체결단가), 11:STCK_CNTG_HOUR(체결시간),
            # 12:RFUS_YN(거부여부), 13:CNTG_YN(체결여부, 1:접수/2:체결), 14:ACPT_YN(접수여부)
            seln_byov_cls = output.get('SELN_BYOV_CLS', '')  # 매도매수 구분
            stock_code = output.get('STK_SHRN_ISCD', '')      # 종목코드
            order_no = output.get('ODER_NO', '')              # 주문번호
            rctf_qty = int(output.get('RCTF_QTY', 0))        # 접수(체결)수량
            rctf_unpr = int(output.get('RCTF_UNPR', 0))      # 접수(체결)단가
            rctf_amt = int(output.get('RCTF_AMT', 0))        # 접수(체결)금액
            prdt_name = output.get('PRDT_NAME', stock_code)  # 상품명(종목명)
            rctf_dt = output.get('RCTF_DT', '')
            rctf_tm = output.get('RCTF_TM', '')
            
            if rctf_qty == 0:
                return
            
            # 매수/매도 구분
            trade_type = "매수" if seln_byov_cls == "02" else "매도"
            emoji = "🎉" if seln_byov_cls == "02" else "💰"
            
            # 로그
            logger.info(
                f"{emoji} {trade_type} 체결: {stock_code} ({prdt_name}) "
                f"{rctf_qty}주 @ {rctf_unpr:,}원 = {rctf_amt:,}원"
            )
            
            # 텔레그램 알림
            await telegram.send(
                f"{emoji} <b>{trade_type} 체결 완료!</b>\n\n"
                f"📌 종목: {prdt_name} ({stock_code})\n"
                f"💰 체결가: {rctf_unpr:,}원\n"
                f"📊 수량: {rctf_qty}주\n"
                f"💵 금액: {rctf_amt:,}원\n"
                f"⏰ 시각: {rctf_tm[:2]}:{rctf_tm[2:4]}:{rctf_tm[4:6]}"
            )
            
            # 매수 체결인 경우 포지션 업데이트
            if seln_byov_cls == "02":
                await self._update_position(stock_code, rctf_qty, rctf_unpr)
        
        except Exception as e:
            logger.error(f"❌ Handle message error: {e}")
    
    async def _update_position(self, code: str, qty: int, price: int):
        """포지션 업데이트 (매수 체결 시)"""
        try:
            if code in position_manager.positions:
                pos = position_manager.positions[code]
                pos['quantity'] = qty
                pos['entry_price'] = price
                pos['highest_price'] = price
                
                logger.info(f"✅ Position updated: {code}")
        
        except Exception as e:
            logger.error(f"Position update error: {e}")
    
    async def start(self):
        """시작"""
        logger.info("🚀 Starting ExecutionNotifier...")
        
        while True:
            try:
                await self.connect_and_subscribe()
            
            except Exception as e:
                logger.error(f"❌ ExecutionNotifier error: {e}")
            
            logger.info(f"⏳ Reconnecting in {self.reconnect_delay}s...")
            await asyncio.sleep(self.reconnect_delay)

execution_notifier = ExecutionNotifier()





# =============================================================================
# [7] 시장 스캐너 (실제 API 연동) ★
# =============================================================================


# ========================================
# KIS 공식 마스터 파일 다운로드 함수
# ========================================

def download_kis_master_files(base_dir="data/master"):
    
    Path(base_dir).mkdir(parents=True, exist_ok=True)
    
    # SSL 인증서 검증 우회
    ssl._create_default_https_context = ssl._create_unverified_context
    
    results = {}
    
    # KOSPI 다운로드
    try:
        logger.info("📥 KOSPI 마스터 파일 다운로드 중...")
        kospi_zip = f"{base_dir}/kospi_code.zip"
        urllib.request.urlretrieve(
            "https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip",
            kospi_zip
        )
        
        # 압축 해제
        with zipfile.ZipFile(kospi_zip, 'r') as zip_ref:
            zip_ref.extractall(base_dir)
        
        # ZIP 파일 삭제
        if os.path.exists(kospi_zip):
            os.remove(kospi_zip)
        
        logger.info("✅ KOSPI 다운로드 완료")
        results['kospi'] = True
    
    except Exception as e:
        logger.error(f"❌ KOSPI 다운로드 실패: {e}")
        results['kospi'] = False
    
    # KOSDAQ 다운로드
    try:
        logger.info("📥 KOSDAQ 마스터 파일 다운로드 중...")
        kosdaq_zip = f"{base_dir}/kosdaq_code.zip"
        urllib.request.urlretrieve(
            "https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip",
            kosdaq_zip
        )
        
        # 압축 해제
        with zipfile.ZipFile(kosdaq_zip, 'r') as zip_ref:
            zip_ref.extractall(base_dir)
        
        # ZIP 파일 삭제
        if os.path.exists(kosdaq_zip):
            os.remove(kosdaq_zip)
        
        logger.info("✅ KOSDAQ 다운로드 완료")
        results['kosdaq'] = True
    
    except Exception as e:
        logger.error(f"❌ KOSDAQ 다운로드 실패: {e}")
        results['kosdaq'] = False
    
    return results


def parse_kospi_master(base_dir="data/master"):
    
    file_name = f"{base_dir}/kospi_code.mst"
    
    if not os.path.exists(file_name):
        logger.error(f"❌ {file_name} 파일이 없습니다")
        return []
    
    try:
        stocks = []
        
        with open(file_name, mode="r", encoding="cp949") as f:
            for row in f:
                # 기본 정보 추출
                code = row[0:9].rstrip()  # 단축코드
                name = row[21:21+40].strip()  # 한글명
                
                # 6자리 숫자 코드만
                if len(code) != 6 or not code.isdigit():
                    continue
                
                # 추가 정보 (고정폭 파일 끝부분)
                tail = row[-228:]
                
                # 관리종목 여부 (위치 36)
                is_managed = tail[36:37]  # Y/N
                
                # 우선주 여부 (위치 53)
                preferred = tail[53:54]  # Y/N
                
                # ETF 여부 (위치 12)
                is_etf = tail[12:13]  # Y/N
                
                # 필터링
                if is_managed == 'Y':
                    continue  # 관리종목 제외
                if preferred == 'Y':
                    continue  # 우선주 제외
                if is_etf == 'Y':
                    continue  # ETF 제외
                
                stocks.append({
                    'code': code,
                    'name': name,
                    'market': 'KOSPI'
                })
        
        logger.info(f"✅ KOSPI: {len(stocks)}개 종목 파싱 완료")
        return stocks
    
    except Exception as e:
        logger.error(f"❌ KOSPI 파싱 실패: {e}")
        return []


def parse_kosdaq_master(base_dir="data/master"):
    
    file_name = f"{base_dir}/kosdaq_code.mst"
    
    if not os.path.exists(file_name):
        logger.error(f"❌ {file_name} 파일이 없습니다")
        return []
    
    try:
        stocks = []
        
        with open(file_name, mode="r", encoding="cp949") as f:
            for row in f:
                # 기본 정보 추출
                code = row[0:9].rstrip()  # 단축코드
                name = row[21:21+40].strip()  # 한글종목명
                
                # 6자리 숫자 코드만
                if len(code) != 6 or not code.isdigit():
                    continue
                
                # 추가 정보 (고정폭 파일 끝부분)
                tail = row[-222:]
                
                # 관리종목 여부 (위치 32)
                is_managed = tail[32:33]  # Y/N
                
                # 우선주 여부 (위치 49)
                preferred = tail[49:50]  # Y/N
                
                # ETF 여부 (위치 8)
                is_etf = tail[8:9]  # Y/N
                
                # 필터링
                if is_managed == 'Y':
                    continue  # 관리종목 제외
                if preferred == 'Y':
                    continue  # 우선주 제외
                if is_etf == 'Y':
                    continue  # ETF 제외
                
                stocks.append({
                    'code': code,
                    'name': name,
                    'market': 'KOSDAQ'
                })
        
        logger.info(f"✅ KOSDAQ: {len(stocks)}개 종목 파싱 완료")
        return stocks
    
    except Exception as e:
        logger.error(f"❌ KOSDAQ 파싱 실패: {e}")
        return []


def get_all_stocks_from_kis(base_dir="data/master"):
    
    # 1. 다운로드
    download_results = download_kis_master_files(base_dir)
    
    if not download_results.get('kospi') and not download_results.get('kosdaq'):
        logger.error("❌ 모든 마스터 파일 다운로드 실패")
        return []
    
    # 2. 파싱
    kospi_stocks = parse_kospi_master(base_dir) if download_results.get('kospi') else []
    kosdaq_stocks = parse_kosdaq_master(base_dir) if download_results.get('kosdaq') else []
    
    # 3. 합치기
    all_stocks = kospi_stocks + kosdaq_stocks
    
    logger.info(f"✅ 총 {len(all_stocks)}개 종목 (KOSPI: {len(kospi_stocks)}, KOSDAQ: {len(kosdaq_stocks)})")
    
    return all_stocks
class MarketScanner:
    """전체 시장 스캔 - 다중 소스 지원 (KIS API + KRX + 캐시)"""
    
    # 방법 1: 한국투자증권 API (우선순위 1)
    KIS_MASTER_ENDPOINT = "/uapi/domestic-stock/v1/quotations/inquire-itemcode-list"
    
    # 방법 2: KRX 데이터 (우선순위 2) 
    KRX_API_URL = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    
    # 방법 3: 예전 URL (백업용)
    OLD_MASTER_URLS = {
        'kospi': 'https://new.real.download.dws.co.kr/common/master/kospi_code.mst',
        'kosdaq': 'https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst'
    }
    
    def __init__(self, cache_dir: str = "data/cache", api_client=None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.api_client = api_client  # KISApiClient 인스턴스
        self.all_stocks = []
        self.stock_info = {}
        self.last_updated = 0
        self.cache_ttl = 3600
    
    def get_all_stocks(self) -> List[str]:
        """전체 거래 가능 종목 조회 - KIS 공식 마스터 파일 우선 (v5)"""
        now = time.time()
        
        # 캐시 확인
        if self.all_stocks and (now - self.last_updated < self.cache_ttl):
            logger.info(f"📦 Using cached: {len(self.all_stocks)} stocks")
            return self.all_stocks
        
        logger.info("🔍 Fetching stock list from multiple sources...")
        
        all_stocks = []
        
        # ★ 방법 1: KIS 공식 마스터 파일 다운로드 (최우선) ★
        logger.info("1️⃣ Trying KIS Official Master Files...")
        stocks = get_all_kis_stocks(base_dir=str(self.cache_dir / "master"))
        if stocks:
            all_stocks = stocks
            logger.info(f"✅ KIS Official: {len(stocks)} stocks")
            self._save_to_cache(all_stocks)  # 캐시 저장
        
        # 방법 2: KIS API 시도 (TR_ID: CTPF1002R)
        if not all_stocks and self.api_client:
            logger.info("2️⃣ Trying KIS API...")
            codes = self._fetch_from_kis_api()
            if codes:
                all_stocks = [{'code': c, 'name': '', 'market': ''} for c in codes]
                logger.info(f"✅ KIS API: {len(codes)} stocks")
        
        # 방법 3: KRX 데이터 시도
        if not all_stocks:
            logger.info("3️⃣ Trying KRX data...")
            codes = self._fetch_from_krx()
            if codes:
                all_stocks = [{'code': c, 'name': '', 'market': ''} for c in codes]
                logger.info(f"✅ KRX: {len(codes)} stocks")
        
        # 방법 4: 기존 URL 시도 (백업)
        if not all_stocks:
            logger.info("4️⃣ Trying old master files...")
            temp_codes = []
            for market, url in self.OLD_MASTER_URLS.items():
                codes = self._download_and_parse(market, url)
                temp_codes.extend(codes)
                logger.info(f"✅ {market.upper()}: {len(codes)} stocks")
            if temp_codes:
                all_stocks = [{'code': c, 'name': '', 'market': ''} for c in temp_codes]
        
        # 방법 5: 로컬 캐시 사용
        if not all_stocks:
            logger.warning("5️⃣ Using local cache (offline mode)...")
            cached = self._load_from_cache()
            if cached:
                all_stocks = cached
        
        # 방법 6: 하드코딩 종목 사용 (테스트용)
        if not all_stocks:
            logger.warning("6️⃣ Using hardcoded stocks (TEST MODE)...")
            hardcoded = self._get_hardcoded_stocks()
            all_stocks = [{'code': c, 'name': '', 'market': ''} for c in hardcoded]
        
        # 종목 코드만 추출 (기존 호환성 유지)
        stock_codes = [s['code'] if isinstance(s, dict) else s for s in all_stocks]
        
        # 필터링
        filtered = self._filter_stocks(stock_codes) if len(stock_codes) > 50 else stock_codes
        
        self.all_stocks = filtered if filtered else stock_codes
        self.last_updated = now
        
        # 종목 정보 딕셔너리 저장 (dict일 경우)
        for item in all_stocks:
            if isinstance(item, dict):
                self.stock_info[item['code']] = item
        
        logger.info(f"✅ Total: {len(self.all_stocks)} tradable stocks")
        return self.all_stocks
    
    def _fetch_from_kis_api(self) -> List[str]:
        """방법 1: 한국투자증권 API로 종목 조회"""
        try:
            # TR_ID: CTPF1002R (국내주식 종목 마스터)
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {self.api_client.access_token}",
                "appkey": Config.APP_KEY,
                "appsecret": Config.APP_SECRET,
                "tr_id": "CTPF1002R"
            }
            
            codes = []
            
            for market_code in ["J", "Q"]:  # J=KOSPI, Q=KOSDAQ
                params = {
                    "PRDT_TYPE_CD": market_code,
                    "PAGE_SIZE": "999"
                }
                
                response = requests.get(
                    f"{Config.URL_BASE}{self.KIS_MASTER_ENDPOINT}",
                    headers=headers,
                    params=params,
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('rt_cd') == '0':
                        items = data.get('output', [])
                        for item in items:
                            code = item.get('stk_code', '')
                            name = item.get('stk_name_kr', '')
                            if code and len(code) == 6:
                                self.stock_info[code] = {
                                    'name': name,
                                    'market': 'KOSPI' if market_code == 'J' else 'KOSDAQ',
                                    'type': '주식'
                                }
                                codes.append(code)
                
                time.sleep(0.1)
            
            if codes:
                # 캐시 저장
                cache_file = self.cache_dir / "api_master.json"
                cache_file.write_text(json.dumps({
                    'codes': codes,
                    'info': self.stock_info,
                    'timestamp': time.time()
                }, ensure_ascii=False), encoding='utf-8')
            
            return codes
        
        except Exception as e:
            logger.error(f"❌ KIS API failed: {e}")
            return []
    
    def _fetch_from_krx(self) -> List[str]:
        """방법 2: KRX 데이터 조회"""
        try:
            codes = []
            
            for market_type in ["STK", "KSQ"]:
                data = {
                    "bld": "dbms/MDC/STAT/standard/MDCSTAT01901",
                    "locale": "ko_KR",
                    "mktId": market_type,
                    "share": "1",
                    "csvxls_isNo": "false"
                }
                
                response = requests.post(
                    self.KRX_API_URL,
                    data=data,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=10
                )
                
                if response.status_code == 200:
                    result = response.json()
                    items = result.get('OutBlock_1', [])
                    
                    for item in items:
                        code = item.get('ISU_SRT_CD', '')
                        name = item.get('ISU_ABBRV', '')
                        
                        if code and len(code) == 6 and code.isdigit():
                            self.stock_info[code] = {
                                'name': name,
                                'market': 'KOSPI' if market_type == 'STK' else 'KOSDAQ',
                                'type': '주식'
                            }
                            codes.append(code)
                
                time.sleep(0.5)
            
            if codes:
                # 캐시 저장
                cache_file = self.cache_dir / "krx_master.json"
                cache_file.write_text(json.dumps({
                    'codes': codes,
                    'info': self.stock_info,
                    'timestamp': time.time()
                }, ensure_ascii=False), encoding='utf-8')
            
            return codes
        
        except Exception as e:
            logger.error(f"❌ KRX data failed: {e}")
            return []
    
    def _download_and_parse(self, market: str, url: str) -> List[str]:
        """방법 3: 기존 마스터파일 다운로드 및 파싱 (백업)"""
        try:
            cache_file = self.cache_dir / f"{market}_master.txt"
            
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            content = response.content.decode('cp949', errors='ignore')
            cache_file.write_text(content, encoding='utf-8')
            
            codes = self._parse_master_file(content, market)
            return codes
        
        except Exception as e:
            logger.debug(f"Old URL failed [{market}]: {e}")
            return []
    
    def _save_to_cache(self, stocks: List[Dict]) -> None:
        """KIS 공식 마스터 파일 캐시 저장 (v5)"""
        try:
            cache_file = self.cache_dir / "kis_official_master.json"
            
            # 종목 정보 딕셔너리로 변환
            stock_dict = {s['code']: s for s in stocks if isinstance(s, dict)}
            
            data = {
                'updated': dt.now().isoformat(),
                'count': len(stocks),
                'codes': [s['code'] if isinstance(s, dict) else s for s in stocks],
                'info': stock_dict
            }
            
            cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            logger.info(f"✅ Saved {len(stocks)} stocks to cache")
        
        except Exception as e:
            logger.error(f"❌ Cache save failed: {e}")
    
    def _load_from_cache(self) -> List[str]:
        """방법 5: 로컬 캐시에서 로드 (최종 백업)"""
        codes = []
        
        # JSON 캐시 우선 (API/KRX)
        for cache_name in ["api_master.json", "krx_master.json"]:
            cache_file = self.cache_dir / cache_name
            if cache_file.exists():
                try:
                    data = json.loads(cache_file.read_text(encoding='utf-8'))
                    codes = data.get('codes', [])
                    self.stock_info = data.get('info', {})
                    logger.info(f"✅ Loaded from cache: {cache_name}")
                    return codes
                except Exception as e:
                    logger.error(f"Cache load error: {e}")
        
        # 텍스트 캐시 (구버전)
        for market in ['kospi', 'kosdaq']:
            cache_file = self.cache_dir / f"{market}_master.txt"
            if cache_file.exists():
                try:
                    content = cache_file.read_text(encoding='utf-8')
                    codes.extend(self._parse_master_file(content, market))
                except Exception as e:
                    logger.error(f"Text cache parse error: {e}")
        
        if codes:
            logger.info(f"✅ Loaded from text cache: {len(codes)} stocks")
        else:
            logger.error("❌ No cache available - please check network connection")
        
        return codes
    
    def _parse_master_file(self, content: str, market: str) -> List[str]:
        """마스터파일 파싱"""
        codes = []
        lines = content.strip().split('\n')
        
        for line in lines:
            if not line.strip():
                continue
            
            try:
                fields = line.split('|')
                
                if len(fields) < 4:
                    continue
                
                code = fields[0].strip()
                name = fields[1].strip()
                stock_type = fields[3].strip() if len(fields) > 3 else ''
                
                if len(code) != 6 or not code.isdigit():
                    continue
                
                self.stock_info[code] = {
                    'name': name,
                    'market': market.upper(),
                    'type': stock_type
                }
                
                codes.append(code)
            
            except Exception:
                continue
        
        return codes
    
    def _filter_stocks(self, codes: List[str]) -> List[str]:
        """종목 필터링"""
        filtered = []
        
        for code in codes:
            info = self.stock_info.get(code, {})
            name = info.get('name', '')
            stock_type = info.get('type', '')
            
            # 우선주 제외
            if code[-1] in ['5', '7', '9']:
                continue
            
            # ETF/ETN/스팩 제외
            exclude_keywords = ['ETF', 'ETN', 'SPAC', '스팩', '리츠']
            if any(kw in name for kw in exclude_keywords):
                continue
            
            # 증권 구분
            if stock_type and stock_type not in ['주식', '보통주', '']:
                continue
            
            filtered.append(code)
        
        return filtered
    
    def get_stock_info(self, code: str) -> Dict:
        """종목 정보 조회"""
        return self.stock_info.get(code, {
            'name': 'Unknown',
            'market': 'Unknown',
            'type': 'Unknown'
        })
    

    def _get_hardcoded_stocks(self) -> List[str]:
        """하드코딩 종목 리스트 (테스트용)"""
        stocks = {
            # 대형주
            '005930': {'name': '삼성전자', 'market': 'KOSPI', 'type': '주식'},
            '000660': {'name': 'SK하이닉스', 'market': 'KOSPI', 'type': '주식'},
            '035720': {'name': '카카오', 'market': 'KOSPI', 'type': '주식'},
            '051910': {'name': 'LG화학', 'market': 'KOSPI', 'type': '주식'},
            '035420': {'name': 'NAVER', 'market': 'KOSPI', 'type': '주식'},
            '006400': {'name': '삼성SDI', 'market': 'KOSPI', 'type': '주식'},
            '005380': {'name': '현대차', 'market': 'KOSPI', 'type': '주식'},
            '012330': {'name': '현대모비스', 'market': 'KOSPI', 'type': '주식'},
            '000270': {'name': '기아', 'market': 'KOSPI', 'type': '주식'},
            '207940': {'name': '삼성바이오로직스', 'market': 'KOSPI', 'type': '주식'},
            
            # 중형주
            '068270': {'name': '셀트리온', 'market': 'KOSPI', 'type': '주식'},
            '005490': {'name': 'POSCO홀딩스', 'market': 'KOSPI', 'type': '주식'},
            '003550': {'name': 'LG', 'market': 'KOSPI', 'type': '주식'},
            '096770': {'name': 'SK이노베이션', 'market': 'KOSPI', 'type': '주식'},
            '028260': {'name': '삼성물산', 'market': 'KOSPI', 'type': '주식'},
            '009150': {'name': '삼성전기', 'market': 'KOSPI', 'type': '주식'},
            '017670': {'name': 'SK텔레콤', 'market': 'KOSPI', 'type': '주식'},
            '032830': {'name': '삼성생명', 'market': 'KOSPI', 'type': '주식'},
            '015760': {'name': '한국전력', 'market': 'KOSPI', 'type': '주식'},
            '018260': {'name': '삼성에스디에스', 'market': 'KOSPI', 'type': '주식'},
            
            # KOSDAQ
            '247540': {'name': '에코프로비엠', 'market': 'KOSDAQ', 'type': '주식'},
            '086520': {'name': '에코프로', 'market': 'KOSDAQ', 'type': '주식'},
            '373220': {'name': 'LG에너지솔루션', 'market': 'KOSPI', 'type': '주식'},
            '066970': {'name': '엘앤에프', 'market': 'KOSDAQ', 'type': '주식'},
            '091990': {'name': '셀트리온헬스케어', 'market': 'KOSDAQ', 'type': '주식'},
            '036570': {'name': '엔씨소프트', 'market': 'KOSDAQ', 'type': '주식'},
            '293490': {'name': '카카오게임즈', 'market': 'KOSDAQ', 'type': '주식'},
            '251270': {'name': '넷마블', 'market': 'KOSDAQ', 'type': '주식'},
            '376300': {'name': '디어유', 'market': 'KOSDAQ', 'type': '주식'},
            '214150': {'name': '클래시스', 'market': 'KOSDAQ', 'type': '주식'},
        }
        
        # stock_info에 추가
        for code, info in stocks.items():
            self.stock_info[code] = info
        
        logger.info(f"📝 Loaded hardcoded stocks: {len(stocks)}")
        return list(stocks.keys())

    def get_market_stats(self) -> Dict:
        """시장 통계"""
        stats = {'total': len(self.all_stocks), 'kospi': 0, 'kosdaq': 0}
        
        for code in self.all_stocks:
            info = self.stock_info.get(code, {})
            market = info.get('market', '').lower()
            
            if market == 'kospi':
                stats['kospi'] += 1
            elif market == 'kosdaq':
                stats['kosdaq'] += 1
        
        return stats


    def get_stock_info_from_api(self, code: str) -> Dict:
        """종목정보 API로 조회 (실전만 지원)"""
        if Config.IS_PAPER_TRADING:
            # 모의투자는 미지원, 기존 캐시 사용
            return self.get_stock_info(code)
        
        try:
            tr_id = Config.get_tr_id('stock_info')
            
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {self.api_client.access_token}",
                "appkey": Config.APP_KEY,
                "appsecret": Config.APP_SECRET,
                "tr_id": tr_id
            }
            
            params = {
                "PRDT_TYPE_CD": "300",  # 주식
                "PDNO": code
            }
            
            response = requests.get(
                f"{Config.URL_BASE}/uapi/domestic-stock/v1/quotations/search-stock-info",
                headers=headers,
                params=params,
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('rt_cd') == '0':
                    output = data.get('output', {})
                    info = {
                        'name': output.get('prdt_name', code),
                        'market': output.get('mket_name', 'Unknown'),
                        'type': '주식'
                    }
                    
                    # 캐시 업데이트
                    self.stock_info[code] = info
                    
                    logger.debug(f"API stock info: {code} = {info['name']}")
                    return info
            
            logger.debug(f"API stock info failed: {code}")
        
        except Exception as e:
            logger.debug(f"Stock info API error [{code}]: {e}")
        
        # Fallback
        return self.get_stock_info(code)


# market_scanner는 TradingSystem.initialize()에서 생성됩니다 (api_client 필요)
market_scanner = None


# =============================================================================
# [8] 전략 판단
# =============================================================================

async def check_strategy(code: str, current_price: float, current_volume: int) -> dict:
    """전략 판단"""
    try:
        stop_loss = current_price * Config.STOP_LOSS_MIN
        
        return {
            'enter': True,
            'stop_loss': stop_loss,
            'meta': {
                'code': code,
                'price': current_price,
                'volume': current_volume
            }
        }
    
    except Exception as e:
        logger.error(f"Strategy check failed [{code}]: {e}")
        return {'enter': False, 'stop_loss': 0, 'meta': {}}


# =============================================================================
# [9] 포지션 관리
# =============================================================================

class PositionManager:
    """포지션 관리"""
    
    def __init__(self):
        self.positions = {}
        self.monitor_tasks = {}
    
    def can_open_position(self) -> bool:
        """포지션 진입 가능 여부"""
        return len(self.positions) < Config.MAX_POSITIONS
    
    def has_position(self, code: str) -> bool:
        """보유 여부"""
        return code in self.positions
    
    async def open_position(self, code: str, entry_price: float, stop_loss: float):
        """포지션 진입 (v5: DRY_RUN 모드 지원)"""
        try:
            balance = api_client.get_account_balance()
            
            if balance < 100000:
                logger.warning("⚠️  Insufficient balance")
                return
            
            risk_amount = balance * Config.RISK_PER_TRADE
            risk_per_share = entry_price - stop_loss
            
            if risk_per_share <= 0:
                return
            
            qty = int(risk_amount / risk_per_share)
            qty = max(1, min(qty, int(balance * 0.3 / entry_price)))
            
            # ★ DRY_RUN 모드 ★
            if Config.DRY_RUN_MODE:
                logger.info(f"🧪 DRY_RUN: 주문 스킨 [{code}] {qty}주 @ {entry_price:,}원")
                logger.info(f"  ↳ 손절가: {stop_loss:,}원 | 리스크: {risk_per_share:,}원/주 | 가용자금: {balance:,}원")
                
                # DRY_RUN에서도 테스트를 위해 포지션은 기록하지 않음 (모니터링만 테스트)
                return
            
            result = api_client.buy_order(code, qty)
            
            if result.get('rt_cd') != '0':
                return
            
            self.positions[code] = {
                'entry_price': entry_price,
                'quantity': qty,
                'remaining_qty': qty,
                'stop_loss': stop_loss,
                'highest_price': entry_price,
                'entry_time': dt.now()
            }
            
            task = asyncio.create_task(self._monitor_position(code))
            self.monitor_tasks[code] = task
            
            # 종목명 조회
            info = market_scanner.get_stock_info(code)
            stock_name = info.get('name', code)
            
            await telegram.send(
                f"✅ <b>포지션 진입</b>\n"
                f"종목: {code} ({stock_name})\n"
                f"가격: {entry_price:,}원\n"
                f"수량: {qty}주\n"
                f"손절: {stop_loss:,}원"
            )
            
            logger.info(f"✅ Position opened: {code} {qty}주 @ {entry_price:,}원")
        
        except Exception as e:
            logger.error(f"❌ Open position failed [{code}]: {e}")
    
    async def _monitor_position(self, code: str):
        """포지션 모니터링"""
        while code in self.positions:
            try:
                await asyncio.sleep(3)
                
                pos = self.positions[code]
                
                price_info = api_client.get_current_price(code)
                curr_price = price_info['price']
                
                if curr_price > pos['highest_price']:
                    pos['highest_price'] = curr_price
                
                profit_pct = (curr_price - pos['entry_price']) / pos['entry_price'] * 100
                
                # 손절
                if curr_price <= pos['stop_loss']:
                    logger.warning(f"🚨 Stop loss: {code}")
                    await self.close_position(code, curr_price, "손절")
                    continue
                
                # 트레일링
                if profit_pct >= Config.TRAILING_ACTIVATION:
                    if profit_pct >= Config.TRAILING_THRESHOLD:
                        trailing_rate = Config.TRAILING_RATE_HIGH
                    else:
                        trailing_rate = Config.TRAILING_RATE_LOW
                    
                    trailing_stop = pos['highest_price'] * trailing_rate
                    
                    if curr_price <= trailing_stop:
                        logger.info(f"🎯 Trailing: {code} (+{profit_pct:.2f}%)")
                        await self.close_position(code, curr_price, "트레일링")
                        continue
                
                logger.info(f"📊 {code}: {curr_price:,}원 ({profit_pct:+.2f}%)")
            
            except Exception as e:
                logger.error(f"Monitor error [{code}]: {e}")
                await asyncio.sleep(5)
    
    async def close_position(self, code: str, price: float, reason: str):
        """포지션 청산 (v5: DRY_RUN 모드 지원)"""
        if code not in self.positions:
            return
        
        try:
            pos = self.positions[code]
            qty = pos['remaining_qty']
            
            # ★ DRY_RUN 모드 ★
            if Config.DRY_RUN_MODE:
                pnl = (price - pos['entry_price']) * qty
                pnl_pct = (price / pos['entry_price'] - 1) * 100
                logger.info(f"🧪 DRY_RUN: 청산 스킨 [{code}] {qty}주 @ {price:,}원 | 사유: {reason} | 손익: {pnl:+,}원 ({pnl_pct:+.2f}%)")
                del self.positions[code]
                if code in self.monitor_tasks:
                    self.monitor_tasks[code].cancel()
                    del self.monitor_tasks[code]
                return
            
            result = api_client.sell_order(code, qty)
            
            if result.get('rt_cd') == '0':
                pnl = (price - pos['entry_price']) * qty
                pnl_pct = (price / pos['entry_price'] - 1) * 100
                
                emoji = "💰" if pnl > 0 else "📉"
                
                info = market_scanner.get_stock_info(code)
                stock_name = info.get('name', code)
                
                await telegram.send(
                    f"{emoji} <b>포지션 청산</b>\n"
                    f"종목: {code} ({stock_name})\n"
                    f"사유: {reason}\n"
                    f"진입: {pos['entry_price']:,}원\n"
                    f"청산: {price:,}원\n"
                    f"손익: {pnl:+,}원 ({pnl_pct:+.2f}%)"
                )
                
                logger.info(f"✅ Position closed: {code} {reason} {pnl:+,}원")
                
                del self.positions[code]
                
                if code in self.monitor_tasks:
                    self.monitor_tasks[code].cancel()
                    del self.monitor_tasks[code]
        
        except Exception as e:
            logger.error(f"❌ Close failed [{code}]: {e}")

position_manager = PositionManager()


# =============================================================================
# [10] 메인 시스템
# =============================================================================

class TradingSystem:
    """자동매매 시스템"""
    
    def __init__(self):
        self.is_running = False
        self.start_time = None
        self.scan_index = 0
    
    async def initialize(self):
        """초기화"""
        global market_scanner
        
        logger.info("=" * 70)
        logger.info("🚀 Trading System Initializing...")
        logger.info("=" * 70)
        
        Config.validate()
        
        token = api_client.get_access_token()
        if not token:
            raise Exception("❌ Token failed")
        
        # MarketScanner 초기화 (api_client 필요)
        market_scanner = MarketScanner(api_client=api_client)
        
        stocks = market_scanner.get_all_stocks()
        stats = market_scanner.get_market_stats()
        
        logger.info(f"📊 Market loaded:")
        logger.info(f"  Total:  {stats['total']:,} stocks")
        logger.info(f"  KOSPI:  {stats['kospi']:,} stocks")
        logger.info(f"  KOSDAQ: {stats['kosdaq']:,} stocks")
        
        await telegram.send(
            f"🚀 <b>SALBO ATS v5 시작</b>\n"
            f"모드: {'🧪 모의투자' if Config.IS_PAPER_TRADING else '💰 실전투자'}"
            + (" (👁️ DRY_RUN - 주문 비활성화)" if Config.DRY_RUN_MODE else "") + "\n"
            f"감시 종목: {stats['total']:,}개\n"
            f"  KOSPI: {stats['kospi']:,}개\n"
            f"  KOSDAQ: {stats['kosdaq']:,}개\n"
            f"최대 포지션: {Config.MAX_POSITIONS}개"
        )
        
        # ExecutionNotifier 시작
        if Config.USE_EXECUTION_NOTIFIER:
            asyncio.create_task(execution_notifier.start())
            logger.info("✅ ExecutionNotifier started")
        
        self.is_running = True
        logger.info("✅ Initialization complete")
    
    async def run(self):
        """메인 루프"""
        self.is_running = True
        self.start_time = dt.now()
        
        logger.info("🔄 Main loop started")
        
        while self.is_running:
            try:
                if not self._is_trading_time():
                    await asyncio.sleep(60)
                    continue
                
                if not position_manager.can_open_position():
                    await asyncio.sleep(10)
                    continue
                
                batch = self._get_next_batch()
                
                for code in batch:
                    try:
                        if position_manager.has_position(code):
                            continue
                        
                        price_info = api_client.get_current_price(code)
                        curr_price = price_info['price']
                        curr_volume = price_info['volume']
                        
                        is_surge, surge_ratio = volume_analyzer.is_volume_surge(code, curr_volume)
                        
                        if not is_surge:
                            continue
                        
                        logger.info(f"🔥 Volume surge: {code} ({surge_ratio:.1f}x)")
                        
                        signal = await check_strategy(code, curr_price, curr_volume)
                        
                        if signal['enter']:
                            logger.info(f"✅ Entry signal: {code} {curr_price:,}원")
                            
                            await position_manager.open_position(
                                code=code,
                                entry_price=curr_price,
                                stop_loss=signal['stop_loss']
                            )
                        
                        await asyncio.sleep(0.5)
                    
                    except Exception as e:
                        logger.error(f"Scan error [{code}]: {e}")
                        continue
                
                await asyncio.sleep(1)
            
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                await asyncio.sleep(5)
        
        logger.info("🛑 Main loop stopped")
    
    def _get_next_batch(self) -> List[str]:
        """다음 배치"""
        stocks = market_scanner.get_all_stocks()
        
        start = self.scan_index
        end = start + Config.SCAN_BATCH_SIZE
        
        batch = stocks[start:end]
        
        self.scan_index = end if end < len(stocks) else 0
        
        return batch
    
    def _is_trading_time(self) -> bool:
        """거래 시간 확인"""
        now = dt.now()
        
        if now.weekday() >= 5:
            return False
        
        start = now.replace(hour=9, minute=10, second=0, microsecond=0)
        end = now.replace(hour=15, minute=20, second=0, microsecond=0)
        
        return start <= now <= end
    
    async def shutdown(self):
        """종료"""
        logger.info("🛑 Shutting down...")
        
        self.is_running = False
        
        for code in list(position_manager.positions.keys()):
            try:
                price_info = api_client.get_current_price(code)
                await position_manager.close_position(code, price_info['price'], "시스템 종료")
            except Exception as e:
                logger.error(f"Shutdown close failed [{code}]: {e}")
        
        await telegram.send("🛑 <b>SALBO ATS 종료</b>")
        
        logger.info("✅ Shutdown complete")


# =============================================================================
# [11] 메인 실행
# =============================================================================

async def main():
    """메인"""
    system = TradingSystem()
    
    def signal_handler(sig, frame):
        logger.info("\n⚠️  Interrupt received")
        asyncio.create_task(system.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await system.initialize()
        await system.run()
    
    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await system.shutdown()


# ========================================
# TEST FUNCTIONS (테스트 함수)
# ========================================

async def test_buy_samsung_10shares():
    """
    삼성전자(005930) 10주 매수 주문 테스트
    
    실행 방법:
        python main_v4_final.py --test-buy
    
    주의사항:
        - 모의투자 계좌에서만 테스트하세요
        - .env에서 IS_PAPER_TRADING=true 확인 필수
        - 장 운영시간(09:00~15:30) 내에만 주문 가능
    """
    logger.info("="*60)
    logger.info("🧪 TEST: 삼성전자 10주 매수 주문 테스트")
    logger.info("="*60)
    
    try:
        # 1. API 클라이언트 초기화
        logger.info("\n[Step 1] API 클라이언트 초기화...")
        token = api_client.get_access_token()
        if not token:
            logger.error("❌ Token 발급 실패")
            return
        logger.info(f"✅ Token: {token[:20]}...")
        
        # 2. 계좌 정보 확인
        logger.info("\n[Step 2] 계좌 정보 확인...")
        logger.info(f"계좌번호: {Config.ACC_NO}-{Config.ACC_PRDT_CD}")
        logger.info(f"HTS ID: {Config.HTS_ID}")
        logger.info(f"모의투자: {Config.IS_PAPER_TRADING}")
        
        if not Config.IS_PAPER_TRADING:
            logger.warning("⚠️  WARNING: 실전투자 모드입니다!")
            logger.warning("⚠️  모의투자로 변경하려면 .env에서 IS_PAPER_TRADING=true 설정")
            response = input("\n실전투자 계좌에서 주문하시겠습니까? (yes/no): ")
            if response.lower() != 'yes':
                logger.info("❌ 테스트 취소")
                return
        
        # 3. 현재가 조회
        stock_code = "005930"  # 삼성전자
        logger.info(f"\n[Step 3] {stock_code} 현재가 조회...")
        
        price_data = api_client.get_current_price(stock_code)
        if not price_data:
            logger.error(f"❌ {stock_code} 현재가 조회 실패")
            return
        
        current_price = int(price_data.get('stck_prpr', 0))
        stock_name = price_data.get('prdt_name', stock_code)
        logger.info(f"✅ {stock_name}({stock_code}) 현재가: {current_price:,}원")
        
        # 4. 주문 수량 및 금액 확인
        order_qty = 10
        estimated_amount = current_price * order_qty
        logger.info(f"\n[Step 4] 주문 정보 확인")
        logger.info(f"주문 종목: {stock_name}({stock_code})")
        logger.info(f"주문 수량: {order_qty}주")
        logger.info(f"현재가: {current_price:,}원")
        logger.info(f"예상 금액: {estimated_amount:,}원")
        
        # 5. 최종 확인
        logger.info("\n[Step 5] 주문 실행 확인")
        response = input(f"\n'{stock_name}({stock_code})' {order_qty}주를 시장가로 매수하시겠습니까? (yes/no): ")
        if response.lower() != 'yes':
            logger.info("❌ 주문 취소")
            return
        
        # 6. 매수 주문 실행
        logger.info("\n[Step 6] 매수 주문 실행 중...")
        result = api_client.buy_order(stock_code, order_qty, current_price)
        
        if result and result.get('rt_cd') == '0':
            order_no = result.get('output', {}).get('ODNO', 'N/A')
            logger.info("="*60)
            logger.info("✅ 매수 주문 성공!")
            logger.info(f"주문번호: {order_no}")
            logger.info(f"종목: {stock_name}({stock_code})")
            logger.info(f"수량: {order_qty}주")
            logger.info(f"가격: {current_price:,}원")
            logger.info(f"금액: {estimated_amount:,}원")
            logger.info("="*60)
            
            # 텔레그램 알림
            if telegram:
                await telegram.send_message(
                    f"🧪 테스트 매수 주문 성공\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"📊 종목: {stock_name}({stock_code})\n"
                    f"💰 가격: {current_price:,}원\n"
                    f"📈 수량: {order_qty}주\n"
                    f"💵 금액: {estimated_amount:,}원\n"
                    f"🔢 주문번호: {order_no}\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"⚠️  모의투자: {Config.IS_PAPER_TRADING}"
                )
        else:
            error_msg = result.get('msg1', '알 수 없는 오류') if result else 'API 호출 실패'
            logger.error(f"❌ 매수 주문 실패: {error_msg}")
            logger.error(f"응답: {result}")
    
    except Exception as e:
        logger.error(f"❌ 테스트 실행 중 오류: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import sys
    
    # 명령줄 인자 확인
    if len(sys.argv) > 1:
        if sys.argv[1] == "--dry-run":
            # DRY_RUN 모드 활성화
            Config.DRY_RUN_MODE = True
            logger.info("🧪 DRY_RUN 모드 활성화: 주문 없이 스캔만 테스트")
            try:
                asyncio.run(main())
            except KeyboardInterrupt:
                print("\n👋 Bye!")
        
        elif sys.argv[1] == "--test-buy":
            # 테스트 모드: 삼성전자 10주 매수
            try:
                asyncio.run(test_buy_samsung_10shares())
            except KeyboardInterrupt:
                logger.info("\n👋 테스트 중단")
            except Exception as e:
                logger.error(f"❌ 테스트 실패: {e}")
                import traceback
                traceback.print_exc()
        
        else:
            print("❌ 잘못된 인자입니다.")
            print("사용법:")
            print("  python main_v5_real.py                # 일반 자동매매")
            print("  python main_v5_real.py --dry-run      # 주문 없이 스캔만")
            print("  python main_v5_real.py --test-buy     # 삼성전자 10주 테스트")
    
    else:
        # 일반 모드: 자동매매 시스템 실행
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print("\n👋 Bye!")
