#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
트레이딩뷰 연동 자동매매 시스템
- 트레이딩뷰 알림 → 텔레그램 → 자동매수
- 3% 익절 (50% 매도) + 트레일링 스톱
- 한국투자증권 API 연동
"""

import os
import sys
import json
import time
import logging
import threading
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

import yaml

# 텔레그램
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
    TELEGRAM_OK = True
except:
    TELEGRAM_OK = False
    print("⚠️ python-telegram-bot 설치 필요: pip install python-telegram-bot")

# ============================================================================
# 로깅 설정
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
# 설정 파일
# ============================================================================
CONFIG_FILE = "config.json"
YAML_FILE = "kis_devlp.yaml"
POSITION_FILE = "positions.json"

# 기본 설정
DEFAULT_CONFIG = {
    "telegram": {
        "bot_token": "",
        "chat_id": ""
    },
    "kis": {
        "server": "vps"  # prod: 실전투자, vps: 모의투자
    },
    "trading": {
        "enabled": False,
        "buy_amount": 1000000,
        "profit_target": 0.03,
        "trailing_stop": 0.02,
        "stop_loss": 0.025,
        "check_interval": 5
    }
}


# ============================================================================
# KIS 인증
# ============================================================================
class KISAuth:
    """한국투자증권 인증 관리"""
    
    def __init__(self, yaml_cfg, server="vps"):
        self.yaml_cfg = yaml_cfg
        self.server = server
        
        # 서버 설정
        if server == "prod":
            self.base_url = yaml_cfg["prod"]
            self.app_key = yaml_cfg["my_app"]
            self.app_secret = yaml_cfg["my_sec"]
        else:
            self.base_url = yaml_cfg["vps"]
            self.app_key = yaml_cfg["paper_app"]
            self.app_secret = yaml_cfg["paper_sec"]
        
        self.token = None
        self.token_expire = None
        
        # 토큰 파일 경로
        self.token_dir = os.path.join(os.path.expanduser("~"), "KIS", "config")
        os.makedirs(self.token_dir, exist_ok=True)
        self.token_file = os.path.join(self.token_dir, f"KIS{datetime.today().strftime('%Y%m%d')}")
        
        logger.info(f"✅ KISAuth 초기화 ({server})")
    
    def get_token(self) -> str:
        """토큰 발급 또는 재사용"""
        # 기존 토큰 확인
        if self.token and self.token_expire and datetime.now() < self.token_expire:
            return self.token
        
        # 파일에서 토큰 읽기
        token = self._read_token_from_file()
        if token:
            self.token = token
            return token
        
        # 새 토큰 발급
        return self._issue_new_token()
    
    def _read_token_from_file(self) -> Optional[str]:
        """토큰 파일 읽기"""
        try:
            if not os.path.exists(self.token_file):
                return None
            
            with open(self.token_file, encoding="UTF-8") as f:
                data = yaml.load(f, Loader=yaml.FullLoader)
            
            if not data or 'token' not in data:
                return None
            
            # 만료 시간 확인
            expire_dt = datetime.strptime(str(data['valid-date']), "%Y-%m-%d %H:%M:%S")
            if expire_dt <= datetime.now():
                logger.info("⚠️ 토큰 만료")
                return None
            
            self.token_expire = expire_dt
            logger.info(f"✅ 기존 토큰 사용 (만료: {expire_dt})")
            return data['token']
        
        except Exception as e:
            logger.warning(f"⚠️ 토큰 파일 읽기 실패: {e}")
            return None
    
    def _issue_new_token(self) -> str:
        """새 토큰 발급"""
        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"Content-Type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        
        try:
            res = requests.post(url, headers=headers, json=body)
            
            if res.status_code == 200:
                data = res.json()
                self.token = data["access_token"]
                
                # 만료 시간 파싱
                expire_str = data["access_token_token_expired"]
                self.token_expire = datetime.strptime(expire_str, "%Y-%m-%d %H:%M:%S")
                
                # 토큰 저장
                with open(self.token_file, "w", encoding="utf-8") as f:
                    f.write(f"token: {self.token}\n")
                    f.write(f"valid-date: {self.token_expire}\n")
                
                logger.info(f"✅ 새 토큰 발급 성공 (만료: {self.token_expire})")
                return self.token
            else:
                logger.error(f"❌ 토큰 발급 실패: {res.text}")
                raise Exception("Token acquisition failed")
        
        except Exception as e:
            logger.error(f"❌ 토큰 발급 오류: {e}")
            raise


# ============================================================================
# KIS 시세 조회
# ============================================================================
class KISMarket:
    """한국투자증권 시세 조회"""
    
    def __init__(self, auth: KISAuth, yaml_cfg):
        self.auth = auth
        self.yaml_cfg = yaml_cfg
    
    def get_current_price(self, code: str) -> Optional[float]:
        """현재가 조회"""
        url = f"{self.auth.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.auth.get_token()}",
            "appkey": self.auth.app_key,
            "appsecret": self.auth.app_secret,
            "tr_id": "FHKST01010100",
            "custtype": "P"
        }
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": code
        }
        
        try:
            res = requests.get(url, headers=headers, params=params)
            
            if res.status_code == 200:
                data = res.json()
                if data["rt_cd"] == "0":
                    price = float(data["output"]["stck_prpr"])
                    return price
        
        except Exception as e:
            logger.error(f"❌ 현재가 조회 오류 ({code}): {e}")
        
        return None


# ============================================================================
# KIS 주문
# ============================================================================
class KISOrder:
    """한국투자증권 주문 실행"""
    
    def __init__(self, auth: KISAuth, yaml_cfg, config):
        self.auth = auth
        self.yaml_cfg = yaml_cfg
        self.config = config
        
        # kis_devlp.yaml에서 계좌 정보 가져오기
        if auth.server == "prod":
            self.account = yaml_cfg["my_acct_stock"]
        else:
            self.account = yaml_cfg["my_paper_stock"]
        
        self.product = yaml_cfg["my_prod"]
    
    def buy(self, code: str, amount: int) -> Dict:
        """매수 주문 (금액 기준)"""
        # 현재가 조회
        market = KISMarket(self.auth, self.yaml_cfg)
        current_price = market.get_current_price(code)
        
        if not current_price:
            return {"success": False, "error": "현재가 조회 실패"}
        
        # 수량 계산
        quantity = int(amount / current_price)
        
        if quantity == 0:
            return {"success": False, "error": "매수 가능 수량 부족"}
        
        # API 호출
        url = f"{self.auth.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        
        # TR ID 설정
        if self.auth.server == "prod":
            tr_id = "TTTC0802U"  # 실전 매수 (현금)
        else:
            tr_id = "VTTC0802U"  # 모의 매수
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.auth.get_token()}",
            "appkey": self.auth.app_key,
            "appsecret": self.auth.app_secret,
            "tr_id": tr_id,
            "custtype": "P"
        }
        
        body = {
            "CANO": self.account,
            "ACNT_PRDT_CD": self.product,
            "PDNO": code,
            "ORD_DVSN": "01",  # 시장가
            "ORD_QTY": str(quantity),
            "ORD_UNPR": "0"
        }
        
        try:
            res = requests.post(url, headers=headers, json=body)
            
            if res.status_code == 200:
                data = res.json()
                
                if data["rt_cd"] == "0":
                    logger.info(f"✅ 매수 주문 성공: {code} {quantity}주")
                    return {
                        "success": True,
                        "code": code,
                        "quantity": quantity,
                        "price": current_price,
                        "order_no": data["output"]["ODNO"]
                    }
                else:
                    logger.error(f"❌ 매수 주문 실패: {data['msg1']}")
                    return {"success": False, "error": data["msg1"]}
            else:
                logger.error(f"❌ API 호출 실패: {res.status_code}")
                return {"success": False, "error": res.text}
        
        except Exception as e:
            logger.error(f"❌ 매수 주문 오류: {e}")
            return {"success": False, "error": str(e)}
    
    def sell(self, code: str, quantity: int) -> Dict:
        """매도 주문"""
        url = f"{self.auth.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        
        # TR ID 설정
        if self.auth.server == "prod":
            tr_id = "TTTC0801U"  # 실전 매도
        else:
            tr_id = "VTTC0801U"  # 모의 매도
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.auth.get_token()}",
            "appkey": self.auth.app_key,
            "appsecret": self.auth.app_secret,
            "tr_id": tr_id,
            "custtype": "P"
        }
        
        body = {
            "CANO": self.account,
            "ACNT_PRDT_CD": self.product,
            "PDNO": code,
            "ORD_DVSN": "01",  # 시장가
            "ORD_QTY": str(quantity),
            "ORD_UNPR": "0"
        }
        
        try:
            res = requests.post(url, headers=headers, json=body)
            
            if res.status_code == 200:
                data = res.json()
                
                if data["rt_cd"] == "0":
                    logger.info(f"✅ 매도 주문 성공: {code} {quantity}주")
                    return {
                        "success": True,
                        "code": code,
                        "quantity": quantity,
                        "order_no": data["output"]["ODNO"]
                    }
                else:
                    logger.error(f"❌ 매도 주문 실패: {data['msg1']}")
                    return {"success": False, "error": data["msg1"]}
            else:
                return {"success": False, "error": res.text}
        
        except Exception as e:
            logger.error(f"❌ 매도 주문 오류: {e}")
            return {"success": False, "error": str(e)}
    
    def get_balance(self) -> Dict:
        """잔고 조회"""
        url = f"{self.auth.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        
        if self.auth.server == "prod":
            tr_id = "TTTC8434R"
        else:
            tr_id = "VTTC8434R"
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.auth.get_token()}",
            "appkey": self.auth.app_key,
            "appsecret": self.auth.app_secret,
            "tr_id": tr_id,
            "custtype": "P"
        }
        
        params = {
            "CANO": self.account,
            "ACNT_PRDT_CD": self.product,
            "AFHR_FLPR_YN": "N",
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
                
                if data["rt_cd"] == "0":
                    output2 = data["output2"][0] if data["output2"] else {}
                    
                    return {
                        "success": True,
                        "cash": int(output2.get("dnca_tot_amt", "0")),
                        "total_value": int(output2.get("tot_evlu_amt", "0")),
                        "stocks": data["output1"]
                    }
        
        except Exception as e:
            logger.error(f"❌ 잔고 조회 오류: {e}")
        
        return {"success": False}


# ============================================================================
# 포지션 관리
# ============================================================================
class PositionManager:
    """포지션 관리"""
    
    def __init__(self):
        self.positions = {}
        self.load_positions()
    
    def load_positions(self):
        """포지션 파일 읽기"""
        if os.path.exists(POSITION_FILE):
            try:
                with open(POSITION_FILE, 'r', encoding='utf-8') as f:
                    self.positions = json.load(f)
                logger.info(f"✅ 포지션 로드: {len(self.positions)}개")
            except:
                self.positions = {}
    
    def save_positions(self):
        """포지션 파일 저장"""
        with open(POSITION_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.positions, f, ensure_ascii=False, indent=2)
    
    def add_position(self, code: str, name: str, buy_price: float, quantity: int, strategy: str):
        """포지션 추가"""
        self.positions[code] = {
            "code": code,
            "name": name,
            "buy_price": buy_price,
            "quantity": quantity,
            "strategy": strategy,
            "entry_time": datetime.now().isoformat(),
            "status": "active",
            "peak_price": buy_price
        }
        self.save_positions()
    
    def has_position(self, code: str) -> bool:
        """포지션 존재 여부"""
        return code in self.positions
    
    def get_active_positions(self) -> List[Dict]:
        """활성 포지션 목록"""
        return [p for p in self.positions.values() if p["status"] in ["active", "partial_sold"]]
    
    def update_position(self, code: str, updates: Dict):
        """포지션 업데이트"""
        if code in self.positions:
            self.positions[code].update(updates)
            self.save_positions()
    
    def close_position(self, code: str):
        """포지션 종료"""
        if code in self.positions:
            self.positions[code]["status"] = "closed"
            self.save_positions()


# ============================================================================
# 텔레그램 봇
# ============================================================================
class TelegramBot:
    """텔레그램 봇"""
    
    def __init__(self, config, system):
        if not TELEGRAM_OK:
            raise Exception("python-telegram-bot not installed")
        
        self.config = config
        self.system = system
        self.token = config["telegram"]["bot_token"]
        self.chat_id = config["telegram"]["chat_id"]
        
        self.app = Application.builder().token(self.token).build()
        
        # 명령어 등록
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("positions", self.cmd_positions))
        self.app.add_handler(CommandHandler("balance", self.cmd_balance))
        self.app.add_handler(CommandHandler("on", self.cmd_on))
        self.app.add_handler(CommandHandler("off", self.cmd_off))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        
        # 트레이딩뷰 알림 수신 (텍스트 메시지)
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_alert))
        
        logger.info("✅ TelegramBot 초기화")
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """봇 시작"""
        await update.message.reply_text(
            "🤖 트레이딩뷰 자동매매 봇\n\n"
            "명령어:\n"
            "/status - 현재 상태\n"
            "/positions - 보유 종목\n"
            "/balance - 잔고 조회\n"
            "/on - 자동매매 시작\n"
            "/off - 자동매매 중지\n"
            "/help - 도움말"
        )
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """상태 조회"""
        enabled = self.config["trading"]["enabled"]
        positions = self.system.position_mgr.get_active_positions()
        
        status_text = "✅ 활성화" if enabled else "❌ 비활성화"
        
        await update.message.reply_text(
            f"📊 시스템 상태\n\n"
            f"자동매매: {status_text}\n"
            f"활성 포지션: {len(positions)}개\n"
            f"매수 금액: {self.config['trading']['buy_amount']:,}원\n"
            f"익절 목표: {self.config['trading']['profit_target']*100}%\n"
            f"트레일링: {self.config['trading']['trailing_stop']*100}%"
        )
    
    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """포지션 조회"""
        positions = self.system.position_mgr.get_active_positions()
        
        if not positions:
            await update.message.reply_text("📊 활성 포지션이 없습니다")
            return
        
        text = "📊 보유 종목\n\n"
        
        for pos in positions:
            current_price = self.system.market.get_current_price(pos["code"])
            if current_price:
                profit_rate = (current_price - pos["buy_price"]) / pos["buy_price"]
                
                text += f"[{pos['code']}] {pos['name']}\n"
                text += f"  매수가: {pos['buy_price']:,.0f}원\n"
                text += f"  현재가: {current_price:,.0f}원\n"
                text += f"  수익률: {profit_rate*100:+.2f}%\n"
                text += f"  수량: {pos['quantity']:,}주\n"
                text += f"  상태: {pos['status']}\n\n"
        
        await update.message.reply_text(text)
    
    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """잔고 조회"""
        result = self.system.order.get_balance()
        
        if result["success"]:
            await update.message.reply_text(
                f"💰 잔고 조회\n\n"
                f"예수금: {result['cash']:,}원\n"
                f"총 평가액: {result['total_value']:,}원"
            )
        else:
            await update.message.reply_text("❌ 잔고 조회 실패")
    
    async def cmd_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """자동매매 시작"""
        self.config["trading"]["enabled"] = True
        self.system.save_config()
        await update.message.reply_text("✅ 자동매매 시작")
    
    async def cmd_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """자동매매 중지"""
        self.config["trading"]["enabled"] = False
        self.system.save_config()
        await update.message.reply_text("⏸️ 자동매매 중지")
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """도움말"""
        await update.message.reply_text(
            "📖 도움말\n\n"
            "1. 트레이딩뷰에서 알림 설정\n"
            "2. 알림 메시지를 이 봇으로 전송\n"
            "3. 자동 매수 실행\n"
            "4. 3% 익절 + 트레일링 스톱\n\n"
            "알림 형식:\n"
            "BUY 005930 삼성전자"
        )
    
    async def handle_alert(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """트레이딩뷰 알림 처리"""
        message = update.message.text.strip()
        
        logger.info(f"📨 알림 수신: {message}")
        
        # 메시지 파싱: "BUY 005930 삼성전자"
        parts = message.split()
        
        if len(parts) < 3:
            await update.message.reply_text("⚠️ 알림 형식 오류\n형식: BUY 종목코드 종목명")
            return
        
        action = parts[0].upper()
        code = parts[1]
        name = " ".join(parts[2:])
        
        if action != "BUY":
            await update.message.reply_text(f"⚠️ 지원하지 않는 동작: {action}")
            return
        
        # 매수 실행
        await update.message.reply_text(f"🔄 매수 주문 중...\n종목: {name} ({code})")
        
        result = self.system.process_buy_signal(code, name, "트레이딩뷰")
        
        if result["success"]:
            await update.message.reply_text(
                f"✅ 매수 완료\n\n"
                f"종목: {result['name']} ({result['code']})\n"
                f"가격: {result['price']:,.0f}원\n"
                f"수량: {result['quantity']:,}주\n"
                f"금액: {result['price'] * result['quantity']:,.0f}원"
            )
        else:
            await update.message.reply_text(f"❌ 매수 실패\n{result.get('error', '')}")
    
    def send_message(self, text: str):
        """메시지 전송"""
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            requests.post(url, json={"chat_id": self.chat_id, "text": text})
        except Exception as e:
            logger.error(f"❌ 텔레그램 메시지 전송 실패: {e}")
    
    def run(self):
        """봇 실행"""
        logger.info("🚀 텔레그램 봇 시작")
        self.app.run_polling()


# ============================================================================
# 메인 시스템
# ============================================================================
class TradingSystem:
    """트레이딩 시스템"""
    
    def __init__(self):
        # 설정 로드
        self.config = self.load_config()
        self.yaml_cfg = self.load_yaml()
        
        # KIS 초기화
        self.auth = KISAuth(self.yaml_cfg, self.config["kis"]["server"])
        self.market = KISMarket(self.auth, self.yaml_cfg)
        self.order = KISOrder(self.auth, self.yaml_cfg, self.config)
        
        # 포지션 관리
        self.position_mgr = PositionManager()
        
        # 텔레그램 봇
        self.telegram = None
        
        # 모니터링 스레드
        self.monitoring = False
        
        logger.info("✅ TradingSystem 초기화 완료")
    
    def load_config(self) -> Dict:
        """설정 로드"""
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # 기본 설정 생성
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
            return DEFAULT_CONFIG.copy()
    
    def save_config(self):
        """설정 저장"""
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
    
    def load_yaml(self) -> Dict:
        """YAML 로드"""
        with open(YAML_FILE, encoding="UTF-8") as f:
            return yaml.load(f, Loader=yaml.FullLoader)
    
    def process_buy_signal(self, code: str, name: str, strategy: str) -> Dict:
        """매수 신호 처리"""
        # 자동매매 활성화 체크
        if not self.config["trading"]["enabled"]:
            return {"success": False, "error": "자동매매 비활성화"}
        
        # 중복 진입 방지
        if self.position_mgr.has_position(code):
            return {"success": False, "error": "이미 보유 중"}
        
        # 매수 주문
        buy_amount = self.config["trading"]["buy_amount"]
        result = self.order.buy(code, buy_amount)
        
        if result["success"]:
            # 포지션 생성
            self.position_mgr.add_position(
                code=code,
                name=name,
                buy_price=result["price"],
                quantity=result["quantity"],
                strategy=strategy
            )
            
            return {
                "success": True,
                "code": code,
                "name": name,
                "price": result["price"],
                "quantity": result["quantity"]
            }
        
        return result
    
    def monitor_positions(self):
        """포지션 모니터링"""
        while self.monitoring:
            try:
                positions = self.position_mgr.get_active_positions()
                
                for pos in positions:
                    # 현재가 조회
                    current_price = self.market.get_current_price(pos["code"])
                    
                    if not current_price:
                        continue
                    
                    # 수익률 계산
                    profit_rate = (current_price - pos["buy_price"]) / pos["buy_price"]
                    
                    # === 1단계 익절: 3% ===
                    if profit_rate >= self.config["trading"]["profit_target"] and pos["status"] == "active":
                        sell_quantity = pos["quantity"] // 2
                        
                        result = self.order.sell(pos["code"], sell_quantity)
                        
                        if result["success"]:
                            self.position_mgr.update_position(pos["code"], {
                                "quantity": pos["quantity"] - sell_quantity,
                                "status": "partial_sold",
                                "peak_price": current_price,
                                "trailing_stop_price": current_price * (1 - self.config["trading"]["trailing_stop"])
                            })
                            
                            if self.telegram:
                                self.telegram.send_message(
                                    f"💰 [1차 익절]\n"
                                    f"종목: {pos['name']}\n"
                                    f"수익률: +{profit_rate*100:.2f}%\n"
                                    f"매도: {sell_quantity}주 (50%)\n"
                                    f"잔여: {pos['quantity'] - sell_quantity}주"
                                )
                    
                    # === 2단계: 트레일링 스톱 ===
                    if pos["status"] == "partial_sold":
                        # 고점 갱신
                        if current_price > pos["peak_price"]:
                            self.position_mgr.update_position(pos["code"], {
                                "peak_price": current_price,
                                "trailing_stop_price": current_price * (1 - self.config["trading"]["trailing_stop"])
                            })
                        
                        # 트레일링 스톱 발동
                        if current_price <= pos["trailing_stop_price"]:
                            result = self.order.sell(pos["code"], pos["quantity"])
                            
                            if result["success"]:
                                self.position_mgr.close_position(pos["code"])
                                
                                final_profit = (current_price - pos["buy_price"]) / pos["buy_price"]
                                
                                if self.telegram:
                                    self.telegram.send_message(
                                        f"📈 [트레일링 스톱]\n"
                                        f"종목: {pos['name']}\n"
                                        f"고점: {pos['peak_price']:,.0f}원\n"
                                        f"매도가: {current_price:,.0f}원\n"
                                        f"최종 수익률: +{final_profit*100:.2f}%"
                                    )
                    
                    # === 손절 ===
                    if profit_rate <= -self.config["trading"]["stop_loss"]:
                        result = self.order.sell(pos["code"], pos["quantity"])
                        
                        if result["success"]:
                            self.position_mgr.close_position(pos["code"])
                            
                            if self.telegram:
                                self.telegram.send_message(
                                    f"🛑 [손절]\n"
                                    f"종목: {pos['name']}\n"
                                    f"손실률: {profit_rate*100:.2f}%"
                                )
                
                # 대기
                time.sleep(self.config["trading"]["check_interval"])
            
            except Exception as e:
                logger.error(f"❌ 모니터링 오류: {e}")
                time.sleep(5)
    
    def start_monitoring(self):
        """모니터링 시작"""
        if not self.monitoring:
            self.monitoring = True
            thread = threading.Thread(target=self.monitor_positions, daemon=True)
            thread.start()
            logger.info("🚀 포지션 모니터링 시작")
    
    def run(self):
        """시스템 실행"""
        # 텔레그램 봇 초기화
        try:
            self.telegram = TelegramBot(self.config, self)
        except Exception as e:
            logger.error(f"❌ 텔레그램 봇 초기화 실패: {e}")
            return
        
        # 모니터링 시작
        self.start_monitoring()
        
        # 봇 실행
        self.telegram.run()


# ============================================================================
# 메인
# ============================================================================
def main():
    print("=" * 80)
    print("트레이딩뷰 연동 자동매매 시스템")
    print("=" * 80)
    
    # 설정 파일 확인
    if not os.path.exists(CONFIG_FILE):
        print(f"\n⚠️ {CONFIG_FILE} 파일이 없습니다.")
        print("기본 설정 파일을 생성합니다...\n")
    
    if not os.path.exists(YAML_FILE):
        print(f"\n❌ {YAML_FILE} 파일이 없습니다.")
        print("kis_devlp.yaml 파일을 먼저 설정해주세요.\n")
        return
    
    # 시스템 실행
    try:
        system = TradingSystem()
        system.run()
    except KeyboardInterrupt:
        print("\n\n시스템 종료")
    except Exception as e:
        logger.error(f"❌ 시스템 오류: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
