# 🌍 국내+해외주식 자동매매 - 현재 상태 및 다음 단계

**작성일**: 2026-01-21  
**버전**: 3.0-beta (부분 구현)

---

## ✅ 완료된 작업

### 1. 핵심 클래스 구현 완료

#### KISOverseasMarket (해외주식 시세)
- ✅ `get_current_price()` - 현재가 조회
- ✅ `get_stock_name()` - 종목명 조회
- ✅ 거래소 지원: NASDAQ, NYSE, AMEX, 홍콩, 상해, 심천, 동경, 호치민, 하노이

#### KISOverseasOrder (해외주식 주문)
- ✅ `buy()` - USD 기반 매수
- ✅ `sell()` - 수량 기반 매도
- ✅ `get_balance()` - USD 잔고 조회
- ✅ API 매핑: TTTT1002U (매수), TTTT1006U (매도)

#### PositionManager (업그레이드)
- ✅ `market_type` 파라미터 추가
- ✅ `get_active_positions(market_type)` 필터링

#### TradingSystem (업그레이드)
- ✅ 국내/해외 객체 분리 초기화
- ✅ `process_buy_signal()` 시장 타입 지원

### 2. 설정 구조 변경
```json
{
  "trading": {
    "domestic": {
      "enabled": false,
      "buy_amount": 1000000
    },
    "overseas": {
      "enabled": false,
      "buy_amount": 1000
    }
  }
}
```

---

## 🚧 남은 작업

### 1. 텔레그램 봇 메뉴 (우선순위 높음)

**필요한 기능**:
- [ ] 콜백 핸들러 완성 (`handle_callback()`)
- [ ] 국내주식 메뉴 핸들러
  - [ ] 자동매매 시작/중지
  - [ ] 보유 종목 조회
  - [ ] 잔고 조회
- [ ] 해외주식 메뉴 핸들러
  - [ ] 자동매매 시작/중지
  - [ ] 보유 종목 조회 (USD)
  - [ ] 잔고 조회 (USD)

### 2. WebhookServer 업데이트

**필요한 변경**:
- [ ] `market` 파라미터 처리
- [ ] `exchange` 파라미터 처리
- [ ] 시장 타입별 라우팅

**현재**:
```python
data = {
  "action": "BUY",
  "ticker": "{{ticker}}"
}
```

**목표**:
```python
data = {
  "action": "BUY",
  "market": "overseas",  # 또는 "domestic"
  "ticker": "AAPL",
  "exchange": "NASDAQ"
}
```

### 3. 모니터링 스레드 분리

**필요한 변경**:
- [ ] 국내주식 모니터링 스레드
- [ ] 해외주식 모니터링 스레드
- [ ] 각각 독립적인 check_interval

---

## 🎯 즉시 가능한 작업

### 옵션 A: 수동 테스트

현재 코드로도 **Python 스크립트**로 직접 테스트 가능:

```python
# 해외주식 매수 테스트
from tradingview_bot import *

system = TradingSystem()

# 애플 매수 ($500)
result = system.overseas_order.buy("AAPL", 500, "NASDAQ")
print(result)

# 현재가 조회
price = system.overseas_market.get_current_price("AAPL", "NASDAQ")
print(f"AAPL: ${price}")

# 잔고 조회
balance = system.overseas_order.get_balance()
print(balance)
```

### 옵션 B: Webhook 부분 구현

WebhookServer에 market_type 처리만 추가하면 **부분 작동** 가능:

```python
# tradingview_bot.py의 WebhookServer.handle_webhook() 수정
def handle_webhook(self):
    data = request.get_json()
    
    action = data.get("action", "").upper()
    ticker = data.get("ticker", "")
    market = data.get("market", "domestic")  # 추가
    exchange = data.get("exchange", "KOSPI")  # 추가
    
    if action == "BUY" and ticker:
        name = (self.system.market.get_stock_name(ticker) 
                if market == "domestic" 
                else ticker)
        
        result = self.system.process_buy_signal(
            ticker, name, "TradingView", market, exchange  # 업데이트
        )
        
        # ... 나머지 로직
```

---

## 📋 3가지 선택지

### 선택지 1: 현재 상태로 사용 (빠름) ⏱️ 10분

**진행 방법**:
1. config.json 업데이트 (trading 구조 변경)
2. WebhookServer 수동 수정 (위 코드 참고)
3. 테스트

**가능한 기능**:
- ✅ 국내주식 자동매매 (기존과 동일)
- ✅ 해외주식 API 호출 (수동 테스트)
- ❌ 텔레그램 메뉴 (미완성)

---

### 선택지 2: Webhook만 완성 (중간) ⏱️ 1시간

**진행 방법**:
1. WebhookServer 완전 구현
2. 모니터링 스레드 분리
3. 통합 테스트

**가능한 기능**:
- ✅ 국내주식 완전 자동매매
- ✅ 해외주식 완전 자동매매
- ❌ 텔레그램 메뉴 (미완성)

**사용 방법**:
- 트레이딩뷰 Webhook으로 매매
- 텔레그램은 알림만

---

### 선택지 3: 완전 구현 (완벽) ⏱️ 3시간

**진행 방법**:
1. WebhookServer 완성
2. 텔레그램 콜백 핸들러 완성
3. 모니터링 스레드 분리
4. 전체 통합 테스트

**가능한 기능**:
- ✅ 국내주식 완전 자동매매
- ✅ 해외주식 완전 자동매매
- ✅ 텔레그램 메뉴 (국내/해외 분리)
- ✅ 독립적인 on/off 제어

**최종 결과**:
```
🤖 트레이딩뷰 자동매매 봇

[📊 시스템 상태]
[🇰🇷 국내주식] [🌎 해외주식]
[💰 전체 잔고]

국내: 활성화 ✅ | 해외: 비활성화 ❌
보유: 국내 2종목 | 해외 0종목
```

---

## 🎮 추천 방안

### 귀하의 상황 분석:
- ✅ PC 24시간 실행 가능
- ✅ ngrok 유료 플랜 사용
- ✅ 국내+해외 자동매매 원함
- ✅ 텔레그램 메뉴로 제어 원함

### 추천: **선택지 2 → 선택지 3**

**이유**:
1. **선택지 2 (1시간)**: Webhook 완성하면 자동매매는 즉시 작동
2. **선택지 3 (추가 2시간)**: 텔레그램 메뉴는 나중에 추가 가능

**진행 순서**:
```
1단계 (지금): 선택지 2 구현 (1시간)
   ↓
트레이딩뷰 Webhook으로 자동매매 테스트
   ↓
2단계 (나중): 선택지 3 완성 (2시간)
   ↓
텔레그램 메뉴로 편리한 제어
```

---

## 💡 빠른 시작 (선택지 2)

### 1. config.json 업데이트

```bash
cd /home/user/webapp
cp config.json config.json.backup
```

```json
{
  "telegram": {
    "bot_token": "8589662322:AAEeCIf0Poce5kmYD43zYwdYSp6MzTdwOOM",
    "chat_id": "5030462236"
  },
  "kis": {
    "server": "vps"
  },
  "trading": {
    "domestic": {
      "enabled": true,
      "buy_amount": 1000000,
      "profit_target": 0.03,
      "trailing_stop": 0.02,
      "stop_loss": 0.025,
      "check_interval": 5
    },
    "overseas": {
      "enabled": true,
      "buy_amount": 500,
      "profit_target": 0.03,
      "trailing_stop": 0.02,
      "stop_loss": 0.025,
      "check_interval": 5
    }
  },
  "webhook": {
    "enabled": true,
    "port": 8080,
    "secret_token": ""
  }
}
```

### 2. WebhookServer 업데이트

*저에게 요청하시면 즉시 완성해드립니다*

### 3. 테스트

```bash
# 국내주식
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"action":"BUY","market":"domestic","ticker":"005930"}'

# 해외주식
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"action":"BUY","market":"overseas","ticker":"AAPL","exchange":"NASDAQ"}'
```

---

## 🚀 어떻게 하시겠어요?

1. **선택지 1**: 현재 상태로 사용 (config만 수정)
2. **선택지 2**: Webhook 완성 (1시간, 추천)
3. **선택지 3**: 완전 구현 (3시간, 완벽)

**또는**:

4. **선택지 2+3**: 단계별 진행 (1시간 + 나중에 2시간)

**알려주세요!** 🤔
