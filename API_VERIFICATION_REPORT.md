# 📋 한국투자증권 API 연동 검증 보고서

**작성일**: 2026-01-19  
**검증 대상**: `advanced_scalping_realtime.py` 및 `realtime_modules.py`  
**검증 기준**: 한국투자증권 공식 API 예제 코드 비교

---

## 🎯 검증 요약

### ✅ 전체 평가: **작동 불가 (Critical Issues Found)**

| 카테고리 | 상태 | 심각도 | 설명 |
|---------|------|--------|------|
| 인증 (Authentication) | ❌ **미구현** | 🔴 Critical | 토큰 발급/갱신 로직 없음 |
| REST API 호출 구조 | ❌ **부적합** | 🔴 Critical | 공식 API 호출 방식 미준수 |
| WebSocket 연결 | ⚠️ **부분 구현** | 🟡 Major | 기본 구조만 존재, 핵심 로직 누락 |
| 데이터 파싱 | ❌ **미구현** | 🔴 Critical | 실시간 데이터 파싱 로직 없음 |
| 주문 실행 | ❌ **미구현** | 🔴 Critical | 주문 API 호출 로직 없음 |
| 잔고 조회 | ❌ **미구현** | 🔴 Critical | 잔고 조회 API 없음 |

**결론**: 현재 코드는 **실제 API 연동이 불가능한 상태**입니다. 골격만 있고 핵심 구현이 누락되었습니다.

---

## 🔍 상세 검증 결과

### 1. ❌ 인증 (Authentication) - Critical

#### 공식 API 방식 (`kis_auth.py`)
```python
# 1. 토큰 발급
def oauth_token():
    url = f"{_TRENV.my_url}/oauth2/tokenP"
    headers = {
        "Content-Type": "application/json"
    }
    body = {
        "grant_type": "client_credentials",
        "appkey": _TRENV.my_app,
        "appsecret": _TRENV.my_sec
    }
    res = requests.post(url, headers=headers, json=body)
    token = res.json()["access_token"]
    return token

# 2. API 호출 시 토큰 포함
def _url_fetch(api_url, tr_id, tr_cont, params, postFlag=False):
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {_TRENV.my_token}",
        "appkey": _TRENV.my_app,
        "appsecret": _TRENV.my_sec,
        "tr_id": tr_id,
        "custtype": "P"
    }
    # ... API 호출 ...
```

#### 현재 코드 (`advanced_scalping_realtime.py`)
```python
class KISAuth:
    def __init__(self, cfg):
        self.cfg = cfg
        self.token = None
        # ❌ 토큰 발급 로직 없음
        # ❌ 자동 갱신 로직 없음
        # ❌ 토큰 만료 체크 없음
```

**문제점**:
- ✗ 토큰 발급 API (`/oauth2/tokenP`) 호출 로직 없음
- ✗ 토큰 저장/읽기 로직 없음 (`token_tmp` 파일 관리)
- ✗ 토큰 만료 시 자동 재발급 없음 (유효기간 24시간)
- ✗ WebSocket 접속키 발급 로직 없음 (`/oauth2/Approval`)

**영향**: API 호출 자체가 불가능 (401 Unauthorized 에러 발생)

---

### 2. ❌ REST API 호출 구조 - Critical

#### 공식 API 방식 (주문 예시)
```python
def order_cash(env_dv, ord_dv, cano, acnt_prdt_cd, pdno, ord_dvsn, ord_qty, ord_unpr, excg_id_dvsn_cd):
    API_URL = "/uapi/domestic-stock/v1/trading/order-cash"
    
    # TR ID 설정 (실전/모의 구분)
    if env_dv == "real":
        if ord_dv == "sell":
            tr_id = "TTTC0011U"  # 실전 매도
        elif ord_dv == "buy":
            tr_id = "TTTC0012U"  # 실전 매수
    elif env_dv == "demo":
        if ord_dv == "sell":
            tr_id = "VTTC0011U"  # 모의 매도
        elif ord_dv == "buy":
            tr_id = "VTTC0012U"  # 모의 매수
    
    # Body 파라미터 (대문자 필수!)
    params = {
        "CANO": cano,
        "ACNT_PRDT_CD": acnt_prdt_cd,
        "PDNO": pdno,
        "ORD_DVSN": ord_dvsn,  # 00:지정가, 01:시장가
        "ORD_QTY": ord_qty,
        "ORD_UNPR": ord_unpr
    }
    
    # API 호출
    res = ka._url_fetch(API_URL, tr_id, "", params, postFlag=True)
    return res
```

#### 현재 코드
```python
class OrderManager:
    def buy(self, code, price, quantity):
        # ❌ API 호출 로직 없음
        # ❌ TR ID 설정 없음
        # ❌ 헤더 구성 없음
        pass  # 빈 구현
    
    def sell(self, code, price, quantity):
        # ❌ 마찬가지로 미구현
        pass
```

**문제점**:
- ✗ `ka._url_fetch()` 공식 함수 미사용
- ✗ TR ID 매핑 로직 없음 (TTTC0012U, VTTC0012U 등)
- ✗ Body 파라미터 대문자 규칙 미준수
- ✗ 해시키 (Hash Key) 생성 로직 없음

---

### 3. ❌ 잔고 조회 API - Critical

#### 공식 API 방식
```python
def inquire_balance(env_dv, cano, acnt_prdt_cd, ...):
    API_URL = "/uapi/domestic-stock/v1/trading/inquire-balance"
    
    if env_dv == "real":
        tr_id = "TTTC8434R"
    elif env_dv == "demo":
        tr_id = "VTTC8434R"
    
    params = {
        "CANO": cano,
        "ACNT_PRDT_CD": acnt_prdt_cd,
        "AFHR_FLPR_YN": "N",
        "INQR_DVSN": "02",  # 종목별
        "UNPR_DVSN": "01",
        "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "00"
    }
    
    res = ka._url_fetch(API_URL, tr_id, "", params)
    df1 = pd.DataFrame(res.getBody().output1)  # 종목별 잔고
    df2 = pd.DataFrame(res.getBody().output2)  # 계좌 요약
    return df1, df2
```

#### 현재 코드
```python
# ❌ 잔고 조회 로직 아예 없음
# 텔레그램에서 잔고 조회 시 어떻게 동작??
```

**문제점**:
- ✗ 잔고 조회 API 호출 로직 없음
- ✗ 매수가능금액 조회 없음
- ✗ 보유 종목 목록 조회 불가

---

### 4. ⚠️ WebSocket 구현 - Major Issues

#### 공식 API 방식
```python
async def connect_websocket():
    # 1. 접속키 발급 (/oauth2/Approval)
    url = f"{_TRENV.my_url}/oauth2/Approval"
    body = {
        "grant_type": "client_credentials",
        "appkey": _TRENV.my_app,
        "secretkey": _TRENV.my_sec
    }
    res = requests.post(url, json=body)
    approval_key = res.json()["approval_key"]
    
    # 2. WebSocket 연결
    async with websockets.connect(_TRENV.my_url_ws) as ws:
        # 3. 구독 메시지 전송
        msg = {
            "header": {
                "approval_key": approval_key,
                "custtype": "P",
                "tr_type": "1",  # 구독
                "content-type": "utf-8"
            },
            "body": {
                "input": {
                    "tr_id": "H0STCNT0",  # 실시간 체결가
                    "tr_key": "005930"     # 종목코드
                }
            }
        }
        await ws.send(json.dumps(msg))
        
        # 4. 데이터 수신 및 파싱
        async for data in ws:
            if data[0] in ["0", "1"]:  # 실시간 데이터
                parts = data.split("|")
                tr_id = parts[1]
                encrypted_data = parts[3]
                
                # AES256 복호화 (암호화된 경우)
                if parts[0] == "1":
                    decrypted = aes_cbc_base64_dec(approval_key, encrypted_data)
                    parsed_data = parse_stock_data(decrypted)
```

#### 현재 코드
```python
class WebSocketClient:
    async def connect(self):
        url = self.env.ws_url
        async with websockets.connect(url) as ws:
            self.ws = ws
            await self.receive_messages()
    
    async def subscribe(self, tr_id, tr_key):
        msg = {
            "header": {
                "approval_key": self.env.ws_key,  # ❌ ws_key가 None
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
        await self.ws.send(json.dumps(msg))
    
    async def receive_messages(self):
        async for raw in self.ws:
            parts = raw.split("|")
            tr_id = parts[1]
            data = parts[3]
            # ❌ 복호화 로직 없음
            # ❌ 데이터 파싱 없음
            self.callbacks[tr_id](data)  # 원본 문자열 그대로 전달
```

**문제점**:
- ⚠️ WebSocket 접속키 발급 로직 없음 (self.env.ws_key가 None)
- ⚠️ AES256 복호화 로직 없음 (암호화 데이터 처리 불가)
- ⚠️ 실시간 데이터 파싱 로직 없음
- ⚠️ PINGPONG 응답 구현 불완전

---

### 5. ❌ 실시간 데이터 파싱 - Critical

#### 공식 API 데이터 구조 (체결가 H0STCNT0)
```python
# 웹소켓 수신 데이터 형식
"0|H0STCNT0|005930|AES256_암호화된_Base64_문자열..."

# 복호화 후 데이터 ('^' 구분자)
"MKSC_SHRN_ISCD^STCK_CNTG_HOUR^STCK_PRPR^PRDY_VRSS^PRDY_VRSS_SIGN^CNTG_VOL^..."
"005930^153010^60000^+100^2^1000^..."

# 파싱 결과
columns = ["MKSC_SHRN_ISCD", "STCK_CNTG_HOUR", "STCK_PRPR", "PRDY_VRSS", ...]
data = {
    "MKSC_SHRN_ISCD": "005930",    # 종목코드
    "STCK_CNTG_HOUR": "153010",    # 체결시각
    "STCK_PRPR": "60000",          # 현재가
    "CNTG_VOL": "1000",            # 체결량
    ...
}
```

#### 현재 코드
```python
def on_tick(self, code, price, volume, timestamp):
    # ❌ 웹소켓 수신 데이터를 어떻게 받았는지 불명확
    # ❌ AES256 복호화 안됨
    # ❌ '^' 구분자 파싱 안됨
    # ❌ 데이터 타입 변환 (str→int, str→float) 안됨
    
    self.current_price[code] = price  # price 값이 어디서 온거지?
```

**문제점**:
- ✗ AES256-CBC 복호화 함수 없음 (`aes_cbc_base64_dec`)
- ✗ '^' 구분자 데이터 파싱 로직 없음
- ✗ 컬럼 매핑 (columns) 없음
- ✗ 데이터 타입 변환 없음

---

### 6. ❌ 5분봉 생성 로직 - 데이터 소스 불명

#### 현재 코드
```python
class CandleBuilder:
    def add_tick(self, code, price, volume, timestamp):
        # 틱 데이터를 받아서 5분봉 생성
        # ❌ 그런데 이 price, volume을 어디서 받는지 불명
        # ❌ 웹소켓 파싱이 안되는데 어떻게 데이터가 들어오나?
```

**문제점**:
- 웹소켓 파싱이 안되므로 `add_tick()` 호출 자체가 불가능
- 실시간 체결가 수신 → 파싱 → `add_tick()` 호출 흐름이 구현되지 않음

---

### 7. ❌ 종목 필터링 (TIER 1) - API 미연동

#### 필요한 API (예시)
```python
# 1. 일봉 데이터 조회
inquire_daily_itemchartprice(
    fid_input_iscd="005930",
    fid_input_date_1="20240101",
    fid_input_date_2="20240131",
    fid_period_div_code="D"  # 일봉
)

# 2. 종목 기본 정보 조회
inquire_price(fid_input_iscd="005930")  # 시가총액, 거래대금 등

# 3. 이동평균선 계산 (자체 구현)
prices = [60000, 61000, 62000, ...]
ma50 = calculate_ma(prices, 50)
ma200 = calculate_ma(prices, 200)
```

#### 현재 코드
```python
# ❌ TIER 1 필터링 로직 아예 없음
# 일봉 조회 API 호출 없음
# 시가총액/거래대금 조회 없음
# 골든크로스 판단 로직 없음
```

---

## 🛠️ 수정 필요 사항 (우선순위별)

### 🔴 Priority 1: Critical (즉시 수정 필수)

#### 1. KISAuth 클래스 - 토큰 관리
```python
class KISAuth:
    def __init__(self, cfg):
        self.cfg = cfg
        self.base_url = cfg["prod"] if not cfg.get("is_paper") else cfg["vps"]
        self.token = None
        self.token_expire = None
        self.ws_key = None
        self.ws_key_expire = None
    
    def get_token(self):
        """토큰 발급 또는 재발급"""
        # 만료 체크
        if self.token and datetime.now() < self.token_expire:
            return self.token
        
        # 토큰 발급
        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"Content-Type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.cfg["my_app"],
            "appsecret": self.cfg["my_sec"]
        }
        
        res = requests.post(url, headers=headers, json=body)
        if res.status_code == 200:
            data = res.json()
            self.token = data["access_token"]
            self.token_expire = datetime.strptime(data["access_token_token_expired"], "%Y-%m-%d %H:%M:%S")
            
            # 토큰 파일 저장
            self._save_token(self.token, self.token_expire)
            
            logger.info(f"✅ 토큰 발급 성공 (만료: {self.token_expire})")
            return self.token
        else:
            logger.error(f"❌ 토큰 발급 실패: {res.text}")
            raise Exception("Token acquisition failed")
    
    def get_ws_key(self):
        """WebSocket 접속키 발급"""
        if self.ws_key and datetime.now() < self.ws_key_expire:
            return self.ws_key
        
        url = f"{self.base_url}/oauth2/Approval"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.cfg["my_app"],
            "secretkey": self.cfg["my_sec"]
        }
        
        res = requests.post(url, json=body)
        if res.status_code == 200:
            self.ws_key = res.json()["approval_key"]
            self.ws_key_expire = datetime.now() + timedelta(hours=24)
            logger.info("✅ WebSocket 접속키 발급 성공")
            return self.ws_key
        else:
            raise Exception("WebSocket key acquisition failed")
    
    def _save_token(self, token, expire_time):
        """토큰 파일 저장 (~/.KIS/config/KIS20260119)"""
        token_file = os.path.join(CONFIG_ROOT, f"KIS{datetime.today().strftime('%Y%m%d')}")
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(f"token: {token}\n")
            f.write(f"valid-date: {expire_time}\n")
```

#### 2. OrderManager 클래스 - 주문 API 연동
```python
class OrderManager:
    def __init__(self, auth, cfg):
        self.auth = auth
        self.cfg = cfg
        self.base_url = cfg["prod"] if not cfg.get("is_paper") else cfg["vps"]
        self.is_paper = cfg.get("is_paper", False)
        self.account = cfg["my_acct_stock"]
        self.product = cfg["my_prod"]
    
    def buy(self, code, price, quantity):
        """매수 주문"""
        api_url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        
        # TR ID 설정
        if self.is_paper:
            tr_id = "VTTC0012U"  # 모의투자 매수
        else:
            tr_id = "TTTC0012U"  # 실전투자 매수
        
        # 헤더 구성
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.auth.get_token()}",
            "appkey": self.cfg["my_app"],
            "appsecret": self.cfg["my_sec"],
            "tr_id": tr_id,
            "custtype": "P"
        }
        
        # Body 파라미터 (반드시 대문자!)
        body = {
            "CANO": self.account,
            "ACNT_PRDT_CD": self.product,
            "PDNO": code,
            "ORD_DVSN": "00" if price > 0 else "01",  # 00:지정가, 01:시장가
            "ORD_QTY": str(quantity),
            "ORD_UNPR": str(int(price))
        }
        
        # API 호출
        res = requests.post(api_url, headers=headers, json=body)
        
        if res.status_code == 200:
            data = res.json()
            if data["rt_cd"] == "0":  # 성공
                order_no = data["output"]["ODNO"]
                logger.info(f"✅ 매수 주문 성공: {code} {quantity}주 @ {price}원 (주문번호: {order_no})")
                return {"success": True, "order_no": order_no}
            else:
                logger.error(f"❌ 매수 주문 실패: {data['msg1']}")
                return {"success": False, "error": data["msg1"]}
        else:
            logger.error(f"❌ API 호출 실패: {res.status_code} {res.text}")
            return {"success": False, "error": res.text}
    
    def sell(self, code, price, quantity):
        """매도 주문 (매수와 유사, tr_id만 다름)"""
        # ... (매수와 동일한 구조, tr_id만 TTTC0011U/VTTC0011U로 변경)
```

#### 3. WebSocket 데이터 파싱
```python
from base64 import b64decode
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

def aes_cbc_base64_dec(key, iv, cipher_text):
    """AES256 복호화"""
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
    decrypted = unpad(cipher.decrypt(b64decode(cipher_text)), AES.block_size)
    return decrypted.decode('utf-8')

class WebSocketClient:
    async def receive_messages(self):
        async for raw in self.ws:
            try:
                # 실시간 데이터
                if raw[0] in ["0", "1"]:
                    parts = raw.split("|")
                    tr_id = parts[1]
                    tr_key = parts[2]
                    data_str = parts[3]
                    
                    # 복호화 (암호화된 경우)
                    if raw[0] == "1":
                        iv = self.ws_key[:16]  # 앞 16자리가 IV
                        data_str = aes_cbc_base64_dec(self.ws_key, iv, data_str)
                    
                    # 데이터 파싱 ('^' 구분자)
                    values = data_str.split("^")
                    
                    # TR ID별 컬럼 매핑
                    if tr_id == "H0STCNT0":  # 실시간 체결가
                        columns = ["MKSC_SHRN_ISCD", "STCK_CNTG_HOUR", "STCK_PRPR", "PRDY_VRSS", "CNTG_VOL", ...]
                        parsed_data = dict(zip(columns, values))
                        
                        # 콜백 호출 (파싱된 데이터 전달)
                        if tr_id in self.callbacks:
                            self.callbacks[tr_id](parsed_data)
                    
                    elif tr_id == "H0STASP0":  # 실시간 호가
                        columns = ["ASKP1", "BIDP1", "ASKP_RSQN1", "BIDP_RSQN1", ...]
                        parsed_data = dict(zip(columns, values))
                        
                        if tr_id in self.callbacks:
                            self.callbacks[tr_id](parsed_data)
                
                # 시스템 메시지
                else:
                    msg = json.loads(raw)
                    if msg.get("header", {}).get("tr_id") == "PINGPONG":
                        await self.ws.pong(raw.encode())
            
            except Exception as e:
                logger.error(f"❌ 메시지 처리 오류: {e}")
```

#### 4. MarketData 클래스 수정
```python
class MarketData:
    def on_tick_callback(self, parsed_data):
        """WebSocket 체결가 콜백"""
        code = parsed_data["MKSC_SHRN_ISCD"]
        price = float(parsed_data["STCK_PRPR"])
        volume = int(parsed_data["CNTG_VOL"])
        
        # 시각 파싱 (HHMMSS)
        time_str = parsed_data["STCK_CNTG_HOUR"]
        timestamp = datetime.strptime(f"{datetime.today().strftime('%Y%m%d')}{time_str}", "%Y%m%d%H%M%S")
        
        # 5분봉 생성
        self.on_tick(code, price, volume, timestamp)
    
    def on_asking_price_callback(self, parsed_data):
        """WebSocket 호가 콜백"""
        code = parsed_data["MKSC_SHRN_ISCD"]
        
        # 체결강도 계산
        self.on_asking_price(code, parsed_data)
```

---

### 🟡 Priority 2: Major (기능 완성을 위해 필요)

#### 5. 잔고 조회 API
```python
def get_balance(self):
    """잔고 조회"""
    api_url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
    
    tr_id = "VTTC8434R" if self.is_paper else "TTTC8434R"
    
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {self.auth.get_token()}",
        "appkey": self.cfg["my_app"],
        "appsecret": self.cfg["my_sec"],
        "tr_id": tr_id,
        "custtype": "P"
    }
    
    params = {
        "CANO": self.account,
        "ACNT_PRDT_CD": self.product,
        "AFHR_FLPR_YN": "N",
        "INQR_DVSN": "02",  # 종목별
        "UNPR_DVSN": "01",
        "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "00",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": ""
    }
    
    res = requests.get(api_url, headers=headers, params=params)
    
    if res.status_code == 200:
        data = res.json()
        return data["output1"], data["output2"]  # 종목별, 계좌요약
    else:
        logger.error(f"❌ 잔고 조회 실패: {res.text}")
        return [], {}
```

#### 6. 일봉 데이터 조회 (TIER 1 필터링용)
```python
def get_daily_chart(self, code, start_date, end_date):
    """일봉 조회"""
    api_url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {self.auth.get_token()}",
        "appkey": self.cfg["my_app"],
        "appsecret": self.cfg["my_sec"],
        "tr_id": "FHKST03010100",
        "custtype": "P"
    }
    
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": code,
        "FID_INPUT_DATE_1": start_date,
        "FID_INPUT_DATE_2": end_date,
        "FID_PERIOD_DIV_CODE": "D",  # 일봉
        "FID_ORG_ADJ_PRC": "0"
    }
    
    res = requests.get(api_url, headers=headers, params=params)
    
    if res.status_code == 200:
        data = res.json()
        df = pd.DataFrame(data["output2"])
        return df
    else:
        return pd.DataFrame()
```

---

## 📊 수정 작업량 추정

| 항목 | 현재 라인 수 | 추가 필요 | 수정 필요 | 예상 시간 |
|------|-------------|---------|---------|----------|
| KISAuth | 0 | 150 | 0 | 3시간 |
| OrderManager | 50 | 200 | 50 | 5시간 |
| WebSocket 파싱 | 100 | 250 | 100 | 6시간 |
| 잔고 조회 | 0 | 100 | 0 | 2시간 |
| 일봉 조회 | 0 | 100 | 0 | 2시간 |
| TIER 1 필터링 | 0 | 300 | 0 | 6시간 |
| 통합 테스트 | - | - | - | 8시간 |
| **총계** | **150** | **1,100** | **150** | **32시간** |

---

## 🎯 즉시 확인 가능한 테스트

### 테스트 1: 토큰 발급 테스트
```bash
cd /home/user/webapp
python3 << 'EOF'
import requests
import yaml

with open("kis_devlp.yaml", encoding="UTF-8") as f:
    cfg = yaml.load(f, yaml.FullLoader)

url = f"{cfg['vps']}/oauth2/tokenP"
body = {
    "grant_type": "client_credentials",
    "appkey": cfg["paper_app"],
    "appsecret": cfg["paper_sec"]
}

res = requests.post(url, json=body)
print(f"Status: {res.status_code}")
print(f"Response: {res.json()}")
EOF
```

**예상 결과**:
- ✅ 성공 시: `{"access_token": "ey...", "token_type": "Bearer", ...}`
- ❌ 실패 시: `{"error": "invalid_client", ...}` → API 키 확인 필요

### 테스트 2: 현재 코드 실행 테스트
```bash
cd /home/user/webapp
python3 advanced_scalping_realtime.py
```

**예상 에러**:
```
❌ AttributeError: 'NoneType' object has no attribute 'my_token'
❌ KeyError: 'ws_key'
❌ 401 Unauthorized
```

---

## 📌 최종 결론

### 현재 상태
- **구현률**: 약 15% (골격만 존재)
- **실행 가능 여부**: ❌ **불가능**
- **API 연동 상태**: ❌ **미연동**

### 필요 작업
1. 🔴 **Critical (32시간)**: 인증, REST API, WebSocket 파싱, 주문/잔고 조회
2. 🟡 **Major (16시간)**: TIER 1 필터링, 일봉 조회, 기술지표 계산
3. 🟢 **Minor (8시간)**: 텔레그램 메뉴 개선, 로깅 강화, 예외 처리

### 총 개발 시간
- **최소**: 32시간 (Critical만)
- **권장**: 56시간 (Critical + Major + Minor)

### 권장 사항
**현재 코드를 폐기하고 새로 작성하는 것을 권장합니다.**

이유:
1. 기존 예제 코드(`examples_llm`, `examples_user`)가 이미 완벽하게 작동함
2. 현재 코드는 API 구조를 잘못 이해한 상태로 작성됨
3. 수정보다 새로 작성이 더 빠르고 안전함

**새로 작성 시 참고할 파일**:
- `/home/user/webapp/examples_user/kis_auth.py` (인증)
- `/home/user/webapp/examples_llm/domestic_stock/order_cash/order_cash.py` (주문)
- `/home/user/webapp/examples_llm/domestic_stock/inquire_balance/inquire_balance.py` (잔고)
- `/home/user/webapp/examples_user/domestic_stock/domestic_stock_functions_ws.py` (웹소켓)

---

**검증 완료일**: 2026-01-19  
**검증자**: AI Code Assistant  
**참조 문서**: 한국투자증권 Open API 공식 GitHub  
