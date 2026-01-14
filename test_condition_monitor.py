#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
조건검색 모니터링 테스트 시스템
==================================================
목적:
- 조건검색식 실행 결과를 주기적으로 모니터링
- 조회된 종목을 텔레그램으로 즉시 알림
- 실전매매 전 종목 발굴 타이밍 검증

사용법:
python test_condition_monitor.py
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Set
from collections import defaultdict

import pandas as pd

# 기존 auto_trading_system 모듈 import
sys.path.extend(['.', './examples_llm'])
import kis_auth as ka

# 텔레그램 봇
try:
    from telegram import Bot
    from telegram.error import TelegramError
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("Warning: python-telegram-bot not installed.")
    print("Install with: pip install python-telegram-bot>=20.0")

# ====================================================================================================
# 로깅 설정
# ====================================================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(f"condition_monitor_{datetime.now().strftime('%Y%m%d')}.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ====================================================================================================
# 설정
# ====================================================================================================

class MonitorConfig:
    """모니터링 설정"""

    # 환경 설정
    ENV_MODE = "demo"  # "real" 또는 "demo"
    PRODUCT_CODE = "01"

    # 조건검색식 설정
    CONDITION_NAME = ""  # 사용할 조건검색식 이름 (비워두면 첫번째 조건 사용)
    CONDITION_SEQ = ""

    # 모니터링 설정
    CHECK_INTERVAL = 10  # 조건검색 실행 주기 (초) - 실시간 감시

    # 텔레그램 설정
    TELEGRAM_BOT_TOKEN = ""
    TELEGRAM_CHAT_ID = ""
    TELEGRAM_ENABLED = False

    # 종목 추적 설정
    TRACK_PRICE_CHANGE = True  # 종목별 가격 변화 추적
    ALERT_NEW_STOCKS_ONLY = True  # 새로 편입된 종목만 알림 (False: 매번 전체 알림)


# ====================================================================================================
# 인증 관리
# ====================================================================================================

class AuthManager:
    """인증 관리 클래스"""

    def __init__(self, env_mode: str = "demo", product_code: str = "01"):
        self.env_mode = env_mode
        self.product_code = product_code
        # kis_auth.py가 인식하는 서버 모드로 변환
        self.server_mode = self._convert_env_mode(env_mode)

    def _convert_env_mode(self, env_mode: str) -> str:
        """환경 모드를 kis_auth.py가 인식하는 서버 모드로 변환"""
        mode_map = {
            "demo": "vps",      # 모의투자
            "paper": "vps",     # 모의투자
            "vps": "vps",       # 모의투자
            "real": "prod",     # 실전투자
            "prod": "prod",     # 실전투자
        }
        converted = mode_map.get(env_mode.lower(), "vps")
        if converted != env_mode:
            logger.info(f"환경 모드 변환: {env_mode} → {converted}")
        return converted

    def authenticate(self) -> bool:
        """인증 토큰 발급"""
        try:
            logger.info(f"인증 시작 (모드: {self.env_mode} → {self.server_mode})")

            # 디버그 모드 활성화
            ka._DEBUG = True

            # 설정 정보 확인 (민감 정보는 마스킹)
            logger.info(f"서버 모드: {self.server_mode}")
            logger.info(f"제품 코드: {self.product_code}")

            # kis_devlp.yaml 로드 확인
            cfg = ka._cfg
            if self.server_mode == "prod":
                app_key = cfg.get("my_app", "")
                app_secret = cfg.get("my_sec", "")
                account = cfg.get("my_acct_stock", "")
            else:
                app_key = cfg.get("paper_app", "")
                app_secret = cfg.get("paper_sec", "")
                account = cfg.get("my_paper_stock", "")

            # 마스킹된 정보 출력 (보안)
            logger.info(f"앱키: {app_key[:4]}{'*' * (len(app_key)-4) if len(app_key) > 4 else '없음'}")
            logger.info(f"앱시크릿: {app_secret[:4]}{'*' * (len(app_secret)-4) if len(app_secret) > 4 else '없음'}")
            logger.info(f"계좌번호: {account}")

            # 앱키/시크릿 유효성 검사
            if not app_key or app_key in ["앱키", "YOUR_APP_KEY", "PS실제앱키여기입력"]:
                logger.error(f"❌ 앱키가 설정되지 않았습니다. kis_devlp.yaml을 확인하세요.")
                logger.error(f"   현재 값: {app_key}")
                return False

            if not app_secret or app_secret in ["앱키 시크릿", "YOUR_APP_SECRET", "실제시크릿키여기입력"]:
                logger.error(f"❌ 앱시크릿이 설정되지 않았습니다. kis_devlp.yaml을 확인하세요.")
                logger.error(f"   현재 값: {app_secret}")
                return False

            if not account or account in ["증권계좌 8자리", "12345678"]:
                logger.warning(f"⚠️  계좌번호가 기본값입니다. kis_devlp.yaml을 확인하세요.")
                logger.warning(f"   현재 값: {account}")

            # 인증 실행
            logger.info("API 인증 요청 중...")
            ka.auth(svr=self.server_mode, product=self.product_code)

            # getTREnv() 결과 디버깅
            trenv = ka.getTREnv()
            logger.info(f"getTREnv() 결과: {trenv}")

            if trenv:
                logger.info(f"trenv 타입: {type(trenv)}")
                logger.info(f"trenv 속성: {dir(trenv)}")

                # my_token 확인
                if hasattr(trenv, 'my_token'):
                    token = trenv.my_token
                    if token:
                        logger.info(f"토큰 존재: {token[:10]}... (길이: {len(token)})")
                    else:
                        logger.error(f"❌ 토큰이 비어있습니다: {token}")
                else:
                    logger.error(f"❌ trenv에 my_token 속성이 없습니다")

                # 계좌 정보 확인
                if hasattr(trenv, 'my_acct'):
                    logger.info(f"계좌번호: {trenv.my_acct}")
                if hasattr(trenv, 'my_prod'):
                    logger.info(f"상품코드: {trenv.my_prod}")
            else:
                logger.error(f"❌ getTREnv()가 None을 반환했습니다")

            if trenv and trenv.my_token:
                logger.info(f"✅ 인증 성공 - 계좌: {trenv.my_acct}-{trenv.my_prod}")
                return True
            else:
                logger.error("❌ 인증 실패 - 토큰 발급 실패")
                return False

        except Exception as e:
            logger.error(f"인증 오류: {e}")
            return False


# ====================================================================================================
# 조건검색 관리
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
# 종목 정보 조회
# ====================================================================================================

class StockInfoManager:
    """종목 정보 관리 클래스"""

    def __init__(self, env_mode: str = "demo"):
        self.env_mode = env_mode

    def get_stock_price(self, stock_code: str) -> Dict:
        """종목 현재가 조회 (코스피/코스닥 자동 판단)"""
        try:
            # 코스피(J), 코스닥(Q) 순서로 시도
            for market_div in ['J', 'Q']:
                params = {
                    "FID_COND_MRKT_DIV_CODE": market_div,
                    "FID_INPUT_ISCD": stock_code
                }

                res = ka._url_fetch(
                    "/uapi/domestic-stock/v1/quotations/inquire-price",
                    "FHKST01010100",
                    "",
                    params
                )

                if res.isOK():
                    output = res.getBody().output
                    return {
                        "code": stock_code,
                        "name": output.get("prdy_vrss_sign", ""),  # 종목명은 별도 조회 필요
                        "current_price": int(output.get("stck_prpr", 0)),  # 현재가
                        "change_rate": float(output.get("prdy_ctrt", 0)),  # 전일대비율
                        "change_price": int(output.get("prdy_vrss", 0)),  # 전일대비
                        "volume": int(output.get("acml_vol", 0)),  # 누적거래량
                        "high_price": int(output.get("stck_hgpr", 0)),  # 고가
                        "low_price": int(output.get("stck_lwpr", 0)),  # 저가
                        "market": "코스피" if market_div == 'J' else "코스닥",  # 시장 정보 추가
                    }

            # 두 시장 모두에서 조회 실패
            logger.error(f"종목가격 조회 실패 (모든 시장): {stock_code}")
            return None

        except Exception as e:
            logger.error(f"종목가격 조회 오류: {e}")
            return None


# ====================================================================================================
# 텔레그램 알림
# ====================================================================================================

class TelegramNotifier:
    """텔레그램 알림 클래스 (단순 알림용)"""

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
        if not self.bot or not MonitorConfig.TELEGRAM_ENABLED:
            return

        try:
            asyncio.run(self._async_send_message(message))
        except Exception as e:
            logger.error(f"텔레그램 메시지 전송 실패: {e}")

    async def _async_send_message(self, message: str):
        """비동기 메시지 전송"""
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='HTML'
            )
            logger.debug("텔레그램 메시지 전송 완료")
        except TelegramError as e:
            logger.error(f"텔레그램 API 오류: {e}")


# ====================================================================================================
# 조건검색 모니터링 시스템
# ====================================================================================================

class ConditionMonitorSystem:
    """조건검색 모니터링 시스템"""

    def __init__(self):
        self.auth_manager = AuthManager(
            env_mode=MonitorConfig.ENV_MODE,
            product_code=MonitorConfig.PRODUCT_CODE
        )
        self.condition_manager = ConditionSearchManager()
        self.stock_info_manager = StockInfoManager(env_mode=MonitorConfig.ENV_MODE)
        self.telegram = TelegramNotifier(
            bot_token=MonitorConfig.TELEGRAM_BOT_TOKEN,
            chat_id=MonitorConfig.TELEGRAM_CHAT_ID
        )

        self.is_running = False
        self.previous_stocks: Set[str] = set()  # 이전 조회 종목 저장
        self.stock_prices: Dict[str, Dict] = {}  # 종목별 가격 정보 저장

    def initialize(self) -> bool:
        """시스템 초기화"""
        try:
            logger.info("="*80)
            logger.info("조건검색 모니터링 테스트 시스템 시작")
            logger.info("="*80)

            # 인증
            if not self.auth_manager.authenticate():
                logger.error("인증 실패 - 시스템 종료")
                return False

            # 조건검색식 목록 조회
            conditions = self.condition_manager.get_condition_list()
            if conditions.empty:
                logger.error("조건검색식이 없습니다 - 시스템 종료")
                return False

            # 조건검색식 표시
            logger.info("\n사용 가능한 조건검색식:")
            for idx, row in conditions.iterrows():
                logger.info(f"  [{idx}] {row['condition_name']} (seq: {row['seq']})")

            logger.info("시스템 초기화 완료")
            return True

        except Exception as e:
            logger.error(f"시스템 초기화 오류: {e}")
            return False

    def start(self):
        """모니터링 시작"""
        try:
            if not self.initialize():
                return

            self.is_running = True

            # 텔레그램 시작 알림
            self.telegram.send_message(
                "🔍 <b>조건검색 모니터링 시작</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"환경: {MonitorConfig.ENV_MODE.upper()}\n"
                f"주기: {MonitorConfig.CHECK_INTERVAL}초\n"
                f"시작시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            # 모니터링 루프
            self._monitoring_loop()

        except KeyboardInterrupt:
            logger.info("사용자에 의한 종료")
            self.stop()
        except Exception as e:
            logger.error(f"시스템 실행 오류: {e}")
            self.stop()

    def stop(self):
        """모니터링 중지"""
        logger.info("조건검색 모니터링 시스템 종료 중...")
        self.is_running = False
        self.telegram.send_message(
            "🛑 <b>조건검색 모니터링 종료</b>\n"
            f"종료시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        logger.info("조건검색 모니터링 시스템 종료 완료")

    def _monitoring_loop(self):
        """모니터링 메인 루프"""
        logger.info(f"\n모니터링 시작 - {MonitorConfig.CHECK_INTERVAL}초 주기로 조건검색 실행")

        while self.is_running:
            try:
                current_time = datetime.now()
                logger.info(f"\n{'='*80}")
                logger.info(f"조건검색 실행 [{current_time.strftime('%Y-%m-%d %H:%M:%S')}]")
                logger.info(f"{'='*80}")

                # 조건검색 실행
                stock_codes = self.condition_manager.search_stocks(
                    seq=MonitorConfig.CONDITION_SEQ,
                    condition_name=MonitorConfig.CONDITION_NAME
                )

                if not stock_codes:
                    logger.info("조회된 종목 없음")
                    time.sleep(MonitorConfig.CHECK_INTERVAL)
                    continue

                # 현재 조회된 종목 세트
                current_stocks = set(stock_codes)

                # 새로 편입된 종목 확인
                new_stocks = current_stocks - self.previous_stocks
                removed_stocks = self.previous_stocks - current_stocks

                # 알림 전송
                if MonitorConfig.ALERT_NEW_STOCKS_ONLY:
                    # 새로 편입된 종목만 알림
                    if new_stocks:
                        self._send_stock_alert(list(new_stocks), is_new=True)
                    if removed_stocks:
                        logger.info(f"제외된 종목: {len(removed_stocks)}개 - {removed_stocks}")
                else:
                    # 전체 종목 알림
                    self._send_stock_alert(stock_codes, is_new=False)

                # 이전 종목 업데이트
                self.previous_stocks = current_stocks

                # 대기
                logger.info(f"\n다음 조회까지 {MonitorConfig.CHECK_INTERVAL}초 대기...")
                time.sleep(MonitorConfig.CHECK_INTERVAL)

            except Exception as e:
                logger.error(f"모니터링 루프 오류: {e}")
                time.sleep(5)

    def _send_stock_alert(self, stock_codes: List[str], is_new: bool = True):
        """종목 알림 전송"""
        try:
            if not stock_codes:
                return

            # 제목
            title = "🆕 <b>새로운 조건검색 종목 발견!</b>" if is_new else "📋 <b>조건검색 종목 현황</b>"

            message = (
                f"{title}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"발견시간: {datetime.now().strftime('%H:%M:%S')}\n"
                f"종목수: {len(stock_codes)}개\n\n"
            )

            # 종목별 정보 조회 및 표시
            for idx, code in enumerate(stock_codes[:10], 1):  # 최대 10개만 표시
                stock_info = self.stock_info_manager.get_stock_price(code)

                if stock_info:
                    current_price = stock_info['current_price']
                    change_rate = stock_info['change_rate']
                    market = stock_info.get('market', '')  # 시장 정보 추가

                    # 이전 가격과 비교 (가격 추적 활성화된 경우)
                    price_change_info = ""
                    if MonitorConfig.TRACK_PRICE_CHANGE and code in self.stock_prices:
                        prev_price = self.stock_prices[code]['current_price']
                        if prev_price > 0:
                            price_diff = current_price - prev_price
                            price_diff_rate = (price_diff / prev_price) * 100
                            if price_diff != 0:
                                emoji = "📈" if price_diff > 0 else "📉"
                                price_change_info = f"\n  {emoji} 변화: {price_diff:+,}원 ({price_diff_rate:+.2f}%)"

                    # 가격 정보 저장
                    self.stock_prices[code] = stock_info

                    # 등락 이모지
                    emoji = "🔺" if change_rate > 0 else "🔻" if change_rate < 0 else "➖"

                    # 시장 표시
                    market_badge = f"[{market}] " if market else ""

                    message += (
                        f"{emoji} <b>{idx}. {market_badge}{code}</b>\n"
                        f"  현재가: {current_price:,}원\n"
                        f"  전일대비: {change_rate:+.2f}%{price_change_info}\n\n"
                    )

                    # API 호출 제한 고려
                    time.sleep(0.05)
                else:
                    message += f"❓ {idx}. {code} (정보 조회 실패)\n\n"

            if len(stock_codes) > 10:
                message += f"... 외 {len(stock_codes) - 10}개 종목\n"

            # 로그 출력
            logger.info(f"\n종목 알림:\n{message}")

            # 텔레그램 전송
            self.telegram.send_message(message)

        except Exception as e:
            logger.error(f"종목 알림 전송 오류: {e}")


# ====================================================================================================
# 설정 파일 로드
# ====================================================================================================

def load_config():
    """설정 파일 로드"""
    config_file = "trading_config.yaml"
    if os.path.exists(config_file):
        try:
            import yaml
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.load(f, Loader=yaml.FullLoader)

            # 설정 적용
            MonitorConfig.ENV_MODE = config.get('env_mode', MonitorConfig.ENV_MODE)
            MonitorConfig.CONDITION_NAME = config.get('condition_name', '')
            MonitorConfig.CONDITION_SEQ = config.get('condition_seq', '')
            MonitorConfig.TELEGRAM_BOT_TOKEN = config.get('telegram_bot_token', '')
            MonitorConfig.TELEGRAM_CHAT_ID = config.get('telegram_chat_id', '')
            MonitorConfig.TELEGRAM_ENABLED = config.get('telegram_enabled', False)

            logger.info(f"설정 파일 로드 완료: {config_file}")
        except Exception as e:
            logger.warning(f"설정 파일 로드 실패: {e}")


# ====================================================================================================
# 메인 실행
# ====================================================================================================

def main():
    """메인 함수"""

    # 설정 파일 로드
    load_config()

    # 사용자 입력으로 설정 변경 (옵션)
    print("\n" + "="*80)
    print("조건검색 모니터링 테스트 시스템")
    print("="*80)
    print(f"\n현재 설정:")
    print(f"  환경: {MonitorConfig.ENV_MODE}")
    print(f"  조건검색식: {MonitorConfig.CONDITION_NAME or '(첫번째 조건 사용)'}")
    print(f"  주기: {MonitorConfig.CHECK_INTERVAL}초")
    print(f"  텔레그램: {'활성화' if MonitorConfig.TELEGRAM_ENABLED else '비활성화'}")
    print(f"  새 종목만 알림: {'예' if MonitorConfig.ALERT_NEW_STOCKS_ONLY else '아니오'}")
    print(f"  가격 변화 추적: {'예' if MonitorConfig.TRACK_PRICE_CHANGE else '아니오'}")

    # 설정 변경
    change = input("\n설정을 변경하시겠습니까? (y/N): ").strip().lower()
    if change == 'y':
        interval = input(f"조회 주기(초) [{MonitorConfig.CHECK_INTERVAL}]: ").strip()
        if interval:
            MonitorConfig.CHECK_INTERVAL = int(interval)

        alert_new = input(f"새 종목만 알림? (y/N) [{'Y' if MonitorConfig.ALERT_NEW_STOCKS_ONLY else 'N'}]: ").strip().lower()
        if alert_new == 'y':
            MonitorConfig.ALERT_NEW_STOCKS_ONLY = True
        elif alert_new == 'n':
            MonitorConfig.ALERT_NEW_STOCKS_ONLY = False

    print(f"\n모니터링을 시작합니다...")
    print(f"종료하려면 Ctrl+C를 누르세요.\n")

    # 모니터링 시스템 생성 및 시작
    system = ConditionMonitorSystem()
    system.start()


if __name__ == "__main__":
    main()
