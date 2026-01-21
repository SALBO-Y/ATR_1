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

# Flask (Webhook 서버용)
try:
    from flask import Flask, request, jsonify
    FLASK_OK = True
except:
    FLASK_OK = False
    print("⚠️ Flask 설치 필요: pip install flask")

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
        "domestic": {
            "enabled": False,
            "buy_amount": 1000000,
            "profit_target": 0.03,
            "trailing_stop": 0.02,
            "stop_loss": 0.025,
            "check_interval": 5
        },
        "overseas": {
            "enabled": False,
            "buy_amount": 1000,  # USD
            "profit_target": 0.03,
            "trailing_stop": 0.02,
            "stop_loss": 0.025,
            "check_interval": 5
        }
    },
    "webhook": {
        "enabled": True,
        "port": 8080,
        "secret_token": ""  # 보안을 위한 토큰 (선택)
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
    
    def get_stock_name(self, code: str) -> str:
        """종목명 조회 (마스터 조회 API 사용)"""
        url = f"{self.auth.base_url}/uapi/domestic-stock/v1/quotations/search-stock-info"
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.auth.get_token()}",
            "appkey": self.auth.app_key,
            "appsecret": self.auth.app_secret,
            "tr_id": "CTPF1002R",
            "custtype": "P"
        }
        
        params = {
            "PRDT_TYPE_CD": "300",  # 주식
            "PDNO": code
        }
        
        try:
            res = requests.get(url, headers=headers, params=params)
            
            if res.status_code == 200:
                data = res.json()
                if data["rt_cd"] == "0" and data.get("output"):
                    # 종목명 추출
                    name = data["output"].get("prdt_name", "")
                    if name:
                        return name
        
        except Exception as e:
            logger.debug(f"종목명 조회 API 1차 실패, 2차 시도 중... ({code})")
        
        # 2차 시도: 현재가 조회 API에서 종목명 추출
        try:
            url = f"{self.auth.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
            
            headers["tr_id"] = "FHKST01010100"
            
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code
            }
            
            res = requests.get(url, headers=headers, params=params)
            
            if res.status_code == 200:
                data = res.json()
                if data["rt_cd"] == "0":
                    # 한글종목명 필드 확인
                    name = data["output"].get("hts_kor_isnm", "")
                    if name:
                        return name
        
        except Exception as e:
            logger.error(f"❌ 종목명 조회 오류 ({code}): {e}")
        
        # 실패 시 종목코드 반환
        return code
    
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
# 해외주식 시세 조회
# ============================================================================
class KISOverseasMarket:
    """한국투자증권 해외주식 시세 조회"""
    
    def __init__(self, auth: KISAuth, yaml_cfg):
        self.auth = auth
        self.yaml_cfg = yaml_cfg
    
    def get_stock_name(self, code: str, exchange: str = "NASDAQ") -> str:
        """해외 종목명 조회"""
        # 간단히 종목코드 반환 (해외는 종목코드가 곧 티커)
        return code
    
    def get_current_price(self, code: str, exchange: str = "NASDAQ") -> Optional[float]:
        """해외주식 현재가 조회"""
        url = f"{self.auth.base_url}/uapi/overseas-price/v1/quotations/price"
        
        # 거래소 코드 매핑
        exchange_map = {
            "NASDAQ": "NAS",
            "NYSE": "NYS",
            "AMEX": "AMS",
            "홍콩": "HKS",
            "상해": "SHS",
            "심천": "SZS",
            "동경": "TSE",
            "호치민": "HSX",
            "하노이": "HNX"
        }
        
        excd = exchange_map.get(exchange, "NAS")
        
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.auth.get_token()}",
            "appkey": self.auth.app_key,
            "appsecret": self.auth.app_secret,
            "tr_id": "HHDFS00000300",  # 해외주식 현재가
            "custtype": "P"
        }
        
        params = {
            "AUTH": "",
            "EXCD": excd,
            "SYMB": code
        }
        
        try:
            res = requests.get(url, headers=headers, params=params)
            
            if res.status_code == 200:
                data = res.json()
                if data["rt_cd"] == "0":
                    price = float(data["output"]["last"])
                    return price
        
        except Exception as e:
            logger.error(f"❌ 해외주식 현재가 조회 오류 ({code}): {e}")
        
        return None


# ============================================================================
# 해외주식 주문
# ============================================================================
class KISOverseasOrder:
    """한국투자증권 해외주식 주문 실행"""
    
    def __init__(self, auth: KISAuth, yaml_cfg, config):
        self.auth = auth
        self.yaml_cfg = yaml_cfg
        self.config = config
        
        # kis_devlp.yaml에서 계좌 정보 가져오기
        if auth.server == "prod":
            self.account = yaml_cfg.get("my_acct_stock", "")
        else:
            self.account = yaml_cfg.get("my_paper_stock", "")
        
        self.product = yaml_cfg.get("my_prod", "01")
        self.market = KISOverseasMarket(auth, yaml_cfg)
    
    def buy(self, code: str, amount: float, exchange: str = "NASDAQ") -> Dict:
        """해외주식 매수"""
        # 현재가 조회
        current_price = self.market.get_current_price(code, exchange)
        
        if not current_price:
            return {"success": False, "error": "현재가 조회 실패"}
        
        # 수량 계산 (USD 금액 / 주가)
        quantity = int(amount / current_price)
        
        if quantity <= 0:
            return {"success": False, "error": "수량 계산 오류"}
        
        # 거래소 코드 매핑
        exchange_map = {
            "NASDAQ": "NASD",
            "NYSE": "NYSE",
            "AMEX": "AMEX",
            "홍콩": "SEHK",
            "상해": "SHAA",
            "심천": "SZAA",
            "동경": "TKSE",
            "호치민": "HOSE",
            "하노이": "HNSE"
        }
        
        ovrs_excg_cd = exchange_map.get(exchange, "NASD")
        
        url = f"{self.auth.base_url}/uapi/overseas-stock/v1/trading/order"
        
        # TR ID
        if self.auth.server == "prod":
            tr_id = "TTTT1002U"  # 실전 매수
        else:
            tr_id = "VTTT1002U"  # 모의 매수
        
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
            "OVRS_EXCG_CD": ovrs_excg_cd,
            "PDNO": code,
            "ORD_DVSN": "00",  # 지정가
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": str(current_price),
            "ORD_SVR_DVSN_CD": "0"  # 기본
        }
        
        try:
            res = requests.post(url, headers=headers, json=body)
            
            if res.status_code == 200:
                data = res.json()
                
                if data["rt_cd"] == "0":
                    logger.info(f"✅ 해외주식 매수 성공: {code} {quantity}주 @ ${current_price}")
                    
                    return {
                        "success": True,
                        "code": code,
                        "price": current_price,
                        "quantity": quantity,
                        "order_id": data["output"].get("ODNO", "")
                    }
                else:
                    logger.error(f"❌ 해외주식 매수 실패: {data.get('msg1', 'Unknown error')}")
                    return {"success": False, "error": data.get("msg1", "Unknown error")}
        
        except Exception as e:
            logger.error(f"❌ 해외주식 매수 오류: {e}")
            return {"success": False, "error": str(e)}
        
        return {"success": False}
    
    def sell(self, code: str, quantity: int, exchange: str = "NASDAQ") -> Dict:
        """해외주식 매도"""
        # 현재가 조회
        current_price = self.market.get_current_price(code, exchange)
        
        if not current_price:
            return {"success": False, "error": "현재가 조회 실패"}
        
        # 거래소 코드 매핑
        exchange_map = {
            "NASDAQ": "NASD",
            "NYSE": "NYSE",
            "AMEX": "AMEX",
            "홍콩": "SEHK",
            "상해": "SHAA",
            "심천": "SZAA",
            "동경": "TKSE",
            "호치민": "HOSE",
            "하노이": "HNSE"
        }
        
        ovrs_excg_cd = exchange_map.get(exchange, "NASD")
        
        url = f"{self.auth.base_url}/uapi/overseas-stock/v1/trading/order"
        
        # TR ID
        if self.auth.server == "prod":
            tr_id = "TTTT1006U"  # 실전 매도
        else:
            tr_id = "VTTT1006U"  # 모의 매도
        
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
            "OVRS_EXCG_CD": ovrs_excg_cd,
            "PDNO": code,
            "ORD_DVSN": "00",  # 지정가
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": str(current_price),
            "ORD_SVR_DVSN_CD": "0"
        }
        
        try:
            res = requests.post(url, headers=headers, json=body)
            
            if res.status_code == 200:
                data = res.json()
                
                if data["rt_cd"] == "0":
                    logger.info(f"✅ 해외주식 매도 성공: {code} {quantity}주 @ ${current_price}")
                    
                    return {
                        "success": True,
                        "code": code,
                        "price": current_price,
                        "quantity": quantity
                    }
                else:
                    logger.error(f"❌ 해외주식 매도 실패: {data.get('msg1', 'Unknown error')}")
                    return {"success": False, "error": data.get("msg1", "Unknown error")}
        
        except Exception as e:
            logger.error(f"❌ 해외주식 매도 오류: {e}")
            return {"success": False, "error": str(e)}
        
        return {"success": False}
    
    def get_balance(self) -> Dict:
        """해외주식 잔고 조회"""
        url = f"{self.auth.base_url}/uapi/overseas-stock/v1/trading/inquire-balance"
        
        # TR ID
        if self.auth.server == "prod":
            tr_id = "TTTS3012R"  # 실전
        else:
            tr_id = "VTTS3012R"  # 모의
        
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
            "OVRS_EXCG_CD": "NASD",  # 기본 나스닥
            "TR_CRCY_CD": "USD",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": ""
        }
        
        try:
            res = requests.get(url, headers=headers, params=params)
            
            if res.status_code == 200:
                data = res.json()
                
                if data["rt_cd"] == "0":
                    output2 = data["output2"] if data["output2"] else {}
                    
                    return {
                        "success": True,
                        "cash": float(output2.get("frcr_dncl_amt_2", "0")),  # USD 예수금
                        "total_value": float(output2.get("tot_asst_amt", "0")),  # 총자산
                        "stocks": data["output1"]
                    }
        
        except Exception as e:
            logger.error(f"❌ 해외주식 잔고 조회 오류: {e}")
        
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
    
    def add_position(self, code: str, name: str, buy_price: float, quantity: int, strategy: str, market_type: str = "domestic", exchange: str = "KOSPI"):
        """포지션 추가"""
        self.positions[code] = {
            "code": code,
            "name": name,
            "buy_price": buy_price,
            "quantity": quantity,
            "strategy": strategy,
            "market_type": market_type,  # domestic or overseas
            "exchange": exchange,  # KOSPI, NASDAQ, etc.
            "entry_time": datetime.now().isoformat(),
            "status": "active",
            "peak_price": buy_price
        }
        self.save_positions()
    
    def has_position(self, code: str) -> bool:
        """포지션 존재 여부"""
        return code in self.positions
    
    def get_active_positions(self, market_type: str = None) -> List[Dict]:
        """활성 포지션 목록"""
        positions = [p for p in self.positions.values() if p["status"] in ["active", "partial_sold"]]
        
        if market_type:
            positions = [p for p in positions if p.get("market_type", "domestic") == market_type]
        
        return positions
    
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
        
        # 콜백 쿼리 핸들러 (버튼 클릭)
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # 트레이딩뷰 알림 수신 (텍스트 메시지)
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_alert))
        
        logger.info("✅ TelegramBot 초기화")
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """봇 시작"""
        keyboard = [
            [InlineKeyboardButton("📊 시스템 상태", callback_data="status")],
            [
                InlineKeyboardButton("🇰🇷 국내주식", callback_data="domestic_menu"),
                InlineKeyboardButton("🌎 해외주식", callback_data="overseas_menu")
            ],
            [InlineKeyboardButton("💰 전체 잔고", callback_data="balance_all")],
            [InlineKeyboardButton("❓ 도움말", callback_data="help")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🤖 트레이딩뷰 자동매매 봇\n\n"
            "국내주식 + 해외주식 자동매매\n\n"
            "📱 아래 버튼을 선택하세요:",
            reply_markup=reply_markup
        )
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """상태 조회"""
        domestic_enabled = self.config["trading"]["domestic"]["enabled"]
        overseas_enabled = self.config["trading"]["overseas"]["enabled"]
        
        domestic_positions = self.system.position_mgr.get_active_positions("domestic")
        overseas_positions = self.system.position_mgr.get_active_positions("overseas")
        
        domestic_status = "✅ 활성화" if domestic_enabled else "❌ 비활성화"
        overseas_status = "✅ 활성화" if overseas_enabled else "❌ 비활성화"
        
        await update.message.reply_text(
            f"📊 시스템 상태\n\n"
            f"🇰🇷 국내주식: {domestic_status}\n"
            f"   포지션: {len(domestic_positions)}개\n"
            f"   매수금액: {self.config['trading']['domestic']['buy_amount']:,}원\n\n"
            f"🌎 해외주식: {overseas_status}\n"
            f"   포지션: {len(overseas_positions)}개\n"
            f"   매수금액: ${self.config['trading']['overseas']['buy_amount']:,.0f}\n\n"
            f"익절: {self.config['trading']['domestic']['profit_target']*100}%\n"
            f"손절: {self.config['trading']['domestic']['stop_loss']*100}%"
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
            "🇰🇷 국내주식: KOSPI, KOSDAQ\n"
            "🌎 해외주식: NASDAQ, NYSE, AMEX 등\n\n"
            "트레이딩뷰 Webhook 메시지:\n"
            "국내: {\"action\":\"BUY\",\"market\":\"domestic\",\"ticker\":\"005930\"}\n"
            "해외: {\"action\":\"BUY\",\"market\":\"overseas\",\"ticker\":\"AAPL\",\"exchange\":\"NASDAQ\"}\n\n"
            "명령어:\n"
            "/start - 메인 메뉴\n"
            "/status - 시스템 상태"
        )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """콜백 쿼리 처리 (버튼 클릭)"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        # 메인 메뉴
        if data == "status":
            await self.callback_status(query)
        elif data == "domestic_menu":
            await self.callback_domestic_menu(query)
        elif data == "overseas_menu":
            await self.callback_overseas_menu(query)
        elif data == "balance_all":
            await self.callback_balance_all(query)
        elif data == "help":
            await self.callback_help(query)
        
        # 국내주식 메뉴
        elif data == "domestic_on":
            await self.callback_domestic_on(query)
        elif data == "domestic_off":
            await self.callback_domestic_off(query)
        elif data == "domestic_positions":
            await self.callback_domestic_positions(query)
        elif data == "domestic_balance":
            await self.callback_domestic_balance(query)
        
        # 해외주식 메뉴
        elif data == "overseas_on":
            await self.callback_overseas_on(query)
        elif data == "overseas_off":
            await self.callback_overseas_off(query)
        elif data == "overseas_positions":
            await self.callback_overseas_positions(query)
        elif data == "overseas_balance":
            await self.callback_overseas_balance(query)
        
        # 뒤로 가기
        elif data == "back_main":
            await self.callback_back_main(query)
    
    # ========== 메인 메뉴 콜백 ==========
    
    async def callback_status(self, query):
        """시스템 상태"""
        domestic_enabled = self.config["trading"]["domestic"]["enabled"]
        overseas_enabled = self.config["trading"]["overseas"]["enabled"]
        
        domestic_positions = self.system.position_mgr.get_active_positions("domestic")
        overseas_positions = self.system.position_mgr.get_active_positions("overseas")
        
        domestic_status = "✅ 활성화" if domestic_enabled else "❌ 비활성화"
        overseas_status = "✅ 활성화" if overseas_enabled else "❌ 비활성화"
        
        text = (
            f"📊 시스템 상태\n\n"
            f"🇰🇷 국내주식: {domestic_status}\n"
            f"   포지션: {len(domestic_positions)}개\n"
            f"   매수금액: {self.config['trading']['domestic']['buy_amount']:,}원\n\n"
            f"🌎 해외주식: {overseas_status}\n"
            f"   포지션: {len(overseas_positions)}개\n"
            f"   매수금액: ${self.config['trading']['overseas']['buy_amount']:,.0f}\n\n"
            f"익절: {self.config['trading']['domestic']['profit_target']*100}%\n"
            f"손절: {self.config['trading']['domestic']['stop_loss']*100}%"
        )
        
        keyboard = [[InlineKeyboardButton("◀️ 메인 메뉴", callback_data="back_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    async def callback_domestic_menu(self, query):
        """국내주식 메뉴"""
        enabled = self.config["trading"]["domestic"]["enabled"]
        status = "✅ 활성화" if enabled else "❌ 비활성화"
        
        keyboard = [
            [
                InlineKeyboardButton("✅ 자동매매 시작", callback_data="domestic_on"),
                InlineKeyboardButton("⏸️ 자동매매 중지", callback_data="domestic_off")
            ],
            [InlineKeyboardButton("📊 보유 종목", callback_data="domestic_positions")],
            [InlineKeyboardButton("💰 잔고 조회", callback_data="domestic_balance")],
            [InlineKeyboardButton("◀️ 메인 메뉴", callback_data="back_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🇰🇷 국내주식 메뉴\n\n"
            f"현재 상태: {status}\n"
            f"매수 금액: {self.config['trading']['domestic']['buy_amount']:,}원",
            reply_markup=reply_markup
        )
    
    async def callback_overseas_menu(self, query):
        """해외주식 메뉴"""
        enabled = self.config["trading"]["overseas"]["enabled"]
        status = "✅ 활성화" if enabled else "❌ 비활성화"
        
        keyboard = [
            [
                InlineKeyboardButton("✅ 자동매매 시작", callback_data="overseas_on"),
                InlineKeyboardButton("⏸️ 자동매매 중지", callback_data="overseas_off")
            ],
            [InlineKeyboardButton("📊 보유 종목 (USD)", callback_data="overseas_positions")],
            [InlineKeyboardButton("💰 잔고 조회 (USD)", callback_data="overseas_balance")],
            [InlineKeyboardButton("◀️ 메인 메뉴", callback_data="back_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🌎 해외주식 메뉴\n\n"
            f"현재 상태: {status}\n"
            f"매수 금액: ${self.config['trading']['overseas']['buy_amount']:,.0f}",
            reply_markup=reply_markup
        )
    
    async def callback_balance_all(self, query):
        """전체 잔고 조회"""
        # 국내주식 잔고
        domestic_result = self.system.order.get_balance()
        
        # 해외주식 잔고
        overseas_result = self.system.overseas_order.get_balance()
        
        text = "💰 전체 잔고\n\n"
        
        if domestic_result["success"]:
            text += (
                f"🇰🇷 국내주식\n"
                f"   예수금: {domestic_result['cash']:,}원\n"
                f"   평가액: {domestic_result['total_value']:,}원\n\n"
            )
        else:
            text += "🇰🇷 국내주식: 조회 실패\n\n"
        
        if overseas_result["success"]:
            text += (
                f"🌎 해외주식\n"
                f"   예수금: ${overseas_result['cash']:,.2f}\n"
                f"   평가액: ${overseas_result['total_value']:,.2f}"
            )
        else:
            text += "🌎 해외주식: 조회 실패"
        
        keyboard = [[InlineKeyboardButton("◀️ 메인 메뉴", callback_data="back_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    async def callback_help(self, query):
        """도움말"""
        text = (
            "📖 도움말\n\n"
            "🇰🇷 국내주식: KOSPI, KOSDAQ\n"
            "🌎 해외주식: NASDAQ, NYSE, AMEX 등\n\n"
            "트레이딩뷰 Webhook:\n"
            "국내: {\"action\":\"BUY\",\"market\":\"domestic\",\"ticker\":\"005930\"}\n"
            "해외: {\"action\":\"BUY\",\"market\":\"overseas\",\"ticker\":\"AAPL\",\"exchange\":\"NASDAQ\"}"
        )
        
        keyboard = [[InlineKeyboardButton("◀️ 메인 메뉴", callback_data="back_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    # ========== 국내주식 콜백 ==========
    
    async def callback_domestic_on(self, query):
        """국내주식 자동매매 시작"""
        self.config["trading"]["domestic"]["enabled"] = True
        self.system.save_config()
        
        await query.answer("✅ 국내주식 자동매매 시작")
        await self.callback_domestic_menu(query)
    
    async def callback_domestic_off(self, query):
        """국내주식 자동매매 중지"""
        self.config["trading"]["domestic"]["enabled"] = False
        self.system.save_config()
        
        await query.answer("⏸️ 국내주식 자동매매 중지")
        await self.callback_domestic_menu(query)
    
    async def callback_domestic_positions(self, query):
        """국내주식 포지션 조회"""
        positions = self.system.position_mgr.get_active_positions("domestic")
        
        if not positions:
            text = "📊 국내주식\n\n활성 포지션이 없습니다"
        else:
            text = f"📊 국내주식 보유 종목 ({len(positions)}개)\n\n"
            
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
        
        keyboard = [[InlineKeyboardButton("◀️ 국내주식 메뉴", callback_data="domestic_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    async def callback_domestic_balance(self, query):
        """국내주식 잔고 조회"""
        result = self.system.order.get_balance()
        
        if result["success"]:
            text = (
                f"💰 국내주식 잔고\n\n"
                f"예수금: {result['cash']:,}원\n"
                f"총 평가액: {result['total_value']:,}원\n"
                f"보유 종목: {len(result.get('stocks', []))}개"
            )
        else:
            text = "❌ 국내주식 잔고 조회 실패"
        
        keyboard = [[InlineKeyboardButton("◀️ 국내주식 메뉴", callback_data="domestic_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    # ========== 해외주식 콜백 ==========
    
    async def callback_overseas_on(self, query):
        """해외주식 자동매매 시작"""
        self.config["trading"]["overseas"]["enabled"] = True
        self.system.save_config()
        
        await query.answer("✅ 해외주식 자동매매 시작")
        await self.callback_overseas_menu(query)
    
    async def callback_overseas_off(self, query):
        """해외주식 자동매매 중지"""
        self.config["trading"]["overseas"]["enabled"] = False
        self.system.save_config()
        
        await query.answer("⏸️ 해외주식 자동매매 중지")
        await self.callback_overseas_menu(query)
    
    async def callback_overseas_positions(self, query):
        """해외주식 포지션 조회"""
        positions = self.system.position_mgr.get_active_positions("overseas")
        
        if not positions:
            text = "📊 해외주식 (USD)\n\n활성 포지션이 없습니다"
        else:
            text = f"📊 해외주식 보유 종목 ({len(positions)}개)\n\n"
            
            for pos in positions:
                # 거래소 정보 가져오기 (기본: NASDAQ)
                exchange = pos.get("exchange", "NASDAQ")
                current_price = self.system.overseas_market.get_current_price(pos["code"], exchange)
                
                if current_price:
                    profit_rate = (current_price - pos["buy_price"]) / pos["buy_price"]
                    
                    text += f"[{pos['code']}] {pos['name']}\n"
                    text += f"  매수가: ${pos['buy_price']:.2f}\n"
                    text += f"  현재가: ${current_price:.2f}\n"
                    text += f"  수익률: {profit_rate*100:+.2f}%\n"
                    text += f"  수량: {pos['quantity']:,}주\n"
                    text += f"  상태: {pos['status']}\n\n"
        
        keyboard = [[InlineKeyboardButton("◀️ 해외주식 메뉴", callback_data="overseas_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    async def callback_overseas_balance(self, query):
        """해외주식 잔고 조회"""
        result = self.system.overseas_order.get_balance()
        
        if result["success"]:
            text = (
                f"💰 해외주식 잔고 (USD)\n\n"
                f"예수금: ${result['cash']:,.2f}\n"
                f"총 평가액: ${result['total_value']:,.2f}\n"
                f"보유 종목: {len(result.get('stocks', []))}개"
            )
        else:
            text = "❌ 해외주식 잔고 조회 실패"
        
        keyboard = [[InlineKeyboardButton("◀️ 해외주식 메뉴", callback_data="overseas_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    # ========== 공통 콜백 ==========
    
    async def callback_back_main(self, query):
        """메인 메뉴로 돌아가기"""
        keyboard = [
            [InlineKeyboardButton("📊 시스템 상태", callback_data="status")],
            [
                InlineKeyboardButton("🇰🇷 국내주식", callback_data="domestic_menu"),
                InlineKeyboardButton("🌎 해외주식", callback_data="overseas_menu")
            ],
            [InlineKeyboardButton("💰 전체 잔고", callback_data="balance_all")],
            [InlineKeyboardButton("❓ 도움말", callback_data="help")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🤖 트레이딩뷰 자동매매 봇\n\n"
            "국내주식 + 해외주식 자동매매\n\n"
            "📱 아래 버튼을 선택하세요:",
            reply_markup=reply_markup
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
        
        # 국내주식
        self.market = KISMarket(self.auth, self.yaml_cfg)
        self.order = KISOrder(self.auth, self.yaml_cfg, self.config)
        
        # 해외주식
        self.overseas_market = KISOverseasMarket(self.auth, self.yaml_cfg)
        self.overseas_order = KISOverseasOrder(self.auth, self.yaml_cfg, self.config)
        
        # 포지션 관리
        self.position_mgr = PositionManager()
        
        # 텔레그램 봇
        self.telegram = None
        
        # 모니터링 스레드
        self.monitoring = False
        
        logger.info("✅ TradingSystem 초기화 완료 (국내+해외)")
    
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
    
    def process_buy_signal(self, code: str, name: str, strategy: str, market_type: str = "domestic", exchange: str = "KOSPI") -> Dict:
        """매수 신호 처리"""
        # 시장 타입별 설정 확인
        if market_type == "domestic":
            trading_config = self.config["trading"]["domestic"]
        else:
            trading_config = self.config["trading"]["overseas"]
        
        # 자동매매 활성화 체크
        if not trading_config["enabled"]:
            return {"success": False, "error": f"{market_type} 자동매매 비활성화"}
        
        # 중복 진입 방지
        if self.position_mgr.has_position(code):
            return {"success": False, "error": "이미 보유 중"}
        
        # 매수 주문 (시장 타입에 따라)
        buy_amount = trading_config["buy_amount"]
        
        if market_type == "domestic":
            result = self.order.buy(code, buy_amount)
        else:
            result = self.overseas_order.buy(code, buy_amount, exchange)
        
        if result["success"]:
            # 포지션 생성
            self.position_mgr.add_position(
                code=code,
                name=name,
                buy_price=result["price"],
                quantity=result["quantity"],
                strategy=strategy,
                market_type=market_type,
                exchange=exchange
            )
            
            return {
                "success": True,
                "code": code,
                "name": name,
                "price": result["price"],
                "quantity": result["quantity"],
                "market_type": market_type,
                "exchange": exchange
            }
        
        return result
        
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
    
    def run(self, webhook_mode=False):
        """시스템 실행"""
        # 텔레그램 봇 초기화
        try:
            self.telegram = TelegramBot(self.config, self)
        except Exception as e:
            logger.error(f"❌ 텔레그램 봇 초기화 실패: {e}")
            if not webhook_mode:
                return
        
        # 모니터링 시작
        self.start_monitoring()
        
        # Webhook 모드가 아니면 봇 실행
        if not webhook_mode:
            self.telegram.run()


# ============================================================================
# Webhook 서버
# ============================================================================
class WebhookServer:
    """트레이딩뷰 Webhook 서버"""
    
    def __init__(self, system: TradingSystem):
        self.system = system
        self.config = system.config
        self.app = Flask(__name__)
        
        # 로깅 제거 (Flask 기본 로그 비활성화)
        import logging as flask_logging
        flask_log = flask_logging.getLogger('werkzeug')
        flask_log.setLevel(flask_logging.ERROR)
        
        # 라우트 등록
        self.app.add_url_rule('/webhook', 'webhook', self.handle_webhook, methods=['POST'])
        self.app.add_url_rule('/health', 'health', self.health_check, methods=['GET'])
        
        logger.info("🌐 Webhook 서버 초기화 완료")
    
    def handle_webhook(self):
        """Webhook 요청 처리"""
        try:
            data = request.get_json()
            
            if not data:
                return jsonify({"status": "error", "message": "Invalid JSON"}), 400
            
            # 보안 토큰 확인
            secret_token = self.config["webhook"].get("secret_token", "")
            if secret_token:
                if data.get("token") != secret_token:
                    logger.warning("⚠️ Webhook 토큰 불일치")
                    return jsonify({"status": "error", "message": "Unauthorized"}), 401
            
            # 액션 파싱
            action = data.get("action", "").upper()
            ticker = data.get("ticker", "")
            price = data.get("price", "")
            time_str = data.get("time", "")
            
            # BUY 신호 처리
            if action == "BUY" and ticker:
                logger.info(f"🚀 Webhook 매수 신호: {ticker}")
                
                # 종목명 조회
                name = self.system.market.get_stock_name(ticker)
                
                # 매수 실행
                result = self.system.process_buy_signal(ticker, name, "TradingView")
                
                if result["success"]:
                    # 텔레그램 알림
                    if self.system.telegram:
                        try:
                            self.system.telegram.send_message(
                                f"🚀 매수 체결 (Webhook)\n\n"
                                f"종목: [{ticker}] {name}\n"
                                f"가격: {result['price']:,}원\n"
                                f"수량: {result['quantity']:,}주\n"
                                f"금액: {result['price']*result['quantity']:,}원"
                            )
                        except:
                            pass
                    
                    return jsonify({
                        "status": "success",
                        "message": f"Buy signal received for {ticker}",
                        "data": {
                            "code": ticker,
                            "name": name,
                            "price": result['price'],
                            "quantity": result['quantity']
                        }
                    })
                else:
                    return jsonify({
                        "status": "error",
                        "message": result.get("error", "Buy failed")
                    }), 400
            
            return jsonify({"status": "error", "message": "Invalid action"}), 400
        
        except Exception as e:
            logger.error(f"❌ Webhook 처리 오류: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
    
    def health_check(self):
        """헬스 체크"""
        return jsonify({
            "status": "ok",
            "service": "TradingView Bot Webhook",
            "enabled": self.config["trading"]["enabled"],
            "positions": len(self.system.position_mgr.get_active_positions())
        })
    
    def run(self):
        """서버 실행"""
        port = self.config["webhook"].get("port", 8080)
        
        logger.info(f"🌐 Webhook 서버 시작: http://0.0.0.0:{port}/webhook")
        logger.info(f"💡 헬스 체크: http://0.0.0.0:{port}/health")
        
        # 별도 스레드에서 텔레그램 봇 실행
        if self.system.telegram:
            bot_thread = threading.Thread(target=self.system.telegram.run, daemon=True)
            bot_thread.start()
            logger.info("📱 텔레그램 봇 시작...")
        
        # Flask 서버 실행
        self.app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)


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
        
        # Webhook 모드 확인
        webhook_enabled = system.config.get("webhook", {}).get("enabled", False)
        
        if webhook_enabled and FLASK_OK:
            logger.info("🚀 Webhook 모드로 시작...")
            
            # Webhook 서버 실행
            webhook_server = WebhookServer(system)
            webhook_server.run()
        else:
            if webhook_enabled and not FLASK_OK:
                logger.warning("⚠️ Flask 설치 필요: pip install flask")
                logger.info("🔄 일반 모드로 실행...")
            
            # 일반 모드 (텔레그램만)
            system.run()
    
    except KeyboardInterrupt:
        print("\n\n시스템 종료")
    except Exception as e:
        logger.error(f"❌ 시스템 오류: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
