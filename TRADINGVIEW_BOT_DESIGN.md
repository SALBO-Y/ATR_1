# 📊 트레이딩뷰 연동 자동매매 시스템 설계

**작성일**: 2026-01-19  
**전략**: 트레이딩뷰 알림 → 텔레그램 → 자동매수 → 자동익절/트레일링스탑

---

## 🎯 시스템 개요

### 핵심 아이디어
- ✅ **단순화**: 복잡한 실시간 분석 불필요
- ✅ **안정성**: 트레이딩뷰의 검증된 지표 활용
- ✅ **효율성**: API 호출 최소화 (폴링 없음)
- ✅ **확장성**: 다양한 전략 적용 가능

### 작동 흐름
```
트레이딩뷰 알림 
    ↓
텔레그램 웹훅
    ↓
매수 주문 (지정 금액)
    ↓
실시간 가격 모니터링
    ↓
┌─────────────────┬──────────────────┐
│ 3% 수익 시       │ 손절 시          │
│ 50% 익절        │ 전량 매도        │
│ 트레일링 스탑    │                 │
└─────────────────┴──────────────────┘
```

---

## 📋 상세 설계

### 1. 트레이딩뷰 알림 설정

#### 알림 메시지 포맷 (JSON)
```json
{
  "action": "buy",
  "symbol": "005930",
  "name": "삼성전자",
  "price": 60000,
  "strategy": "골든크로스",
  "timestamp": "2026-01-19T15:30:00"
}
```

#### 트레이딩뷰 알림 URL
```
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/sendMessage
```

**또는 중계 서버 사용 (권장)**:
```
https://your-webhook-server.com/tradingview-alert
```

---

### 2. 텔레그램 봇 구조

#### 2.1. 명령어 체계

| 명령어 | 기능 | 예시 |
|-------|------|------|
| `/start` | 봇 시작 | - |
| `/status` | 현재 상태 | 포지션, 잔고 |
| `/positions` | 보유 종목 | 종목별 수익률 |
| `/balance` | 잔고 조회 | 예수금, 총 평가액 |
| `/set_amount` | 매수 금액 설정 | `/set_amount 1000000` |
| `/set_profit` | 익절 비율 | `/set_profit 3` (3%) |
| `/set_trailing` | 트레일링 비율 | `/set_trailing 2` (2%) |
| `/on` | 자동매매 시작 | - |
| `/off` | 자동매매 중지 | - |
| `/help` | 도움말 | - |

#### 2.2. 알림 메시지

**진입 알림**:
```
🔔 [매수 신호]
종목: 삼성전자 (005930)
전략: 골든크로스
가격: 60,000원
수량: 16주
금액: 960,000원
시간: 15:30:00
```

**익절 알림**:
```
💰 [익절 완료]
종목: 삼성전자 (005930)
매수가: 60,000원
매도가: 61,800원
수익률: +3.0%
수익금: +28,800원
시간: 16:45:00
```

**트레일링 스탑 알림**:
```
📈 [트레일링 스탑 작동]
종목: 삼성전자 (005930)
고점: 62,000원
현재가: 60,760원 (-2%)
매도 실행
수익률: +1.27%
시간: 17:10:00
```

---

### 3. 매매 로직

#### 3.1. 진입 로직

```python
def on_tradingview_alert(alert_data):
    """트레이딩뷰 알림 처리"""
    
    # 1. 알림 검증
    if not validate_alert(alert_data):
        return
    
    # 2. 자동매매 활성화 체크
    if not is_trading_enabled():
        notify_telegram("⚠️ 자동매매 비활성화 상태")
        return
    
    # 3. 중복 진입 방지
    if has_position(alert_data['symbol']):
        notify_telegram(f"⚠️ {alert_data['name']} 이미 보유 중")
        return
    
    # 4. 잔고 확인
    balance = get_balance()
    buy_amount = get_setting('buy_amount')  # 예: 1,000,000원
    
    if balance < buy_amount:
        notify_telegram(f"❌ 잔고 부족: {balance:,}원")
        return
    
    # 5. 매수 주문
    result = buy_order(
        code=alert_data['symbol'],
        amount=buy_amount,
        price=alert_data['price']  # 지정가 또는 시장가
    )
    
    if result['success']:
        # 6. 포지션 생성
        position = {
            'code': alert_data['symbol'],
            'name': alert_data['name'],
            'buy_price': result['avg_price'],
            'quantity': result['quantity'],
            'entry_time': datetime.now(),
            'strategy': alert_data['strategy'],
            'status': 'active'
        }
        
        save_position(position)
        
        # 7. 텔레그램 알림
        notify_telegram(f"""
🔔 [매수 완료]
종목: {position['name']} ({position['code']})
가격: {position['buy_price']:,}원
수량: {position['quantity']:,}주
금액: {position['buy_price'] * position['quantity']:,}원
전략: {position['strategy']}
        """)
```

#### 3.2. 익절 로직

```python
def monitor_positions():
    """포지션 모니터링 (5초마다)"""
    
    positions = get_active_positions()
    
    for pos in positions:
        # 현재가 조회
        current_price = get_current_price(pos['code'])
        
        # 수익률 계산
        profit_rate = (current_price - pos['buy_price']) / pos['buy_price']
        
        # === 1단계 익절: 3% 달성 시 50% 매도 ===
        if profit_rate >= 0.03 and pos['status'] == 'active':
            sell_quantity = pos['quantity'] // 2
            
            result = sell_order(
                code=pos['code'],
                quantity=sell_quantity,
                price=current_price
            )
            
            if result['success']:
                # 포지션 업데이트
                pos['quantity'] -= sell_quantity
                pos['status'] = 'partial_sold'
                pos['peak_price'] = current_price
                pos['trailing_stop_price'] = current_price * 0.98  # -2%
                
                update_position(pos)
                
                notify_telegram(f"""
💰 [1차 익절 완료]
종목: {pos['name']} ({pos['code']})
매도: {sell_quantity:,}주 (50%)
가격: {current_price:,}원
수익률: +{profit_rate*100:.2f}%
잔여: {pos['quantity']:,}주 (트레일링 스탑 활성화)
                """)
        
        # === 2단계: 트레일링 스톱 ===
        if pos['status'] == 'partial_sold':
            # 고점 갱신
            if current_price > pos['peak_price']:
                pos['peak_price'] = current_price
                pos['trailing_stop_price'] = current_price * 0.98  # -2%
                update_position(pos)
            
            # 트레일링 스톱 발동
            if current_price <= pos['trailing_stop_price']:
                result = sell_order(
                    code=pos['code'],
                    quantity=pos['quantity'],
                    price=current_price
                )
                
                if result['success']:
                    final_profit_rate = (current_price - pos['buy_price']) / pos['buy_price']
                    
                    pos['status'] = 'closed'
                    update_position(pos)
                    
                    notify_telegram(f"""
📈 [트레일링 스톱 체결]
종목: {pos['name']} ({pos['code']})
고점: {pos['peak_price']:,}원
매도가: {current_price:,}원
최종 수익률: +{final_profit_rate*100:.2f}%
                    """)
        
        # === 손절 로직 ===
        if profit_rate <= -0.025:  # -2.5%
            result = sell_order(
                code=pos['code'],
                quantity=pos['quantity'],
                price=current_price
            )
            
            if result['success']:
                pos['status'] = 'stopped'
                update_position(pos)
                
                notify_telegram(f"""
🛑 [손절 체결]
종목: {pos['name']} ({pos['code']})
매수가: {pos['buy_price']:,}원
매도가: {current_price:,}원
손실률: {profit_rate*100:.2f}%
                """)
```

---

## 🛠️ 구현 파일 구조

```
tradingview_bot.py          # 메인 파일 (단일 파일)
├── Class: KISAuth          # 한투증권 인증
├── Class: KISOrder         # 주문 실행
├── Class: KISMarket        # 시세 조회
├── Class: PositionManager  # 포지션 관리
├── Class: TelegramBot      # 텔레그램 봇
└── Class: TradingSystem    # 메인 시스템
```

---

## 📊 설정 파일 (config.json)

```json
{
  "telegram": {
    "bot_token": "YOUR_BOT_TOKEN",
    "chat_id": "YOUR_CHAT_ID"
  },
  "kis": {
    "server": "vps"      // prod: 실전투자, vps: 모의투자
  },
  "trading": {
    "enabled": false,
    "buy_amount": 1000000,
    "profit_target": 0.03,
    "trailing_stop": 0.02,
    "stop_loss": 0.025,
    "check_interval": 5
  }
}
```

**참고**: 
- 계좌번호와 상품코드는 `kis_devlp.yaml`에서 자동으로 가져옵니다
- `server` 값에 따라 자동으로 계좌 선택:
  - `vps`: `my_paper_stock` + `my_prod` 사용
  - `prod`: `my_acct_stock` + `my_prod` 사용

---

## 🚀 트레이딩뷰 알림 설정 가이드

### 1. 알림 생성

1. 차트에서 지표 추가 (예: EMA 50/200 골든크로스)
2. 알림 아이콘 클릭
3. 조건 설정:
   - `EMA(50) crosses over EMA(200)`
4. 알림 동작: `Webhook URL`

### 2. Webhook URL 설정

#### Option A: 직접 텔레그램 (간단, 제한적)
```
https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>&text={{ticker}}+매수신호
```

#### Option B: 중계 서버 (권장, 유연함)
```
https://your-server.com/webhook
```

**메시지 본문**:
```json
{
  "action": "buy",
  "symbol": "{{ticker}}",
  "price": {{close}},
  "strategy": "골든크로스",
  "timestamp": "{{time}}"
}
```

---

## 🔧 중계 서버 (Flask) - 선택사항

```python
from flask import Flask, request
import requests

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = "YOUR_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"

@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    """트레이딩뷰 웹훅 수신"""
    
    # 1. 데이터 파싱
    data = request.json
    
    # 2. 검증
    if data.get('secret') != 'your-secret-key':
        return 'Unauthorized', 401
    
    # 3. 텔레그램으로 전달
    message = f"""
🔔 [트레이딩뷰 알림]
종목: {data['symbol']}
가격: {data['price']}
전략: {data['strategy']}
    """
    
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }
    )
    
    return 'OK', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

---

## 💡 장점

### 기존 방식 대비
| 항목 | 기존 (실시간 분석) | 새 방식 (트뷰 알림) |
|------|-------------------|-------------------|
| 복잡도 | 🔴 매우 높음 | 🟢 낮음 |
| API 호출 | 🔴 초당 수십회 | 🟢 초당 0.2회 |
| 안정성 | 🟡 중간 | 🟢 높음 |
| 전략 수정 | 🔴 코드 수정 필요 | 🟢 트뷰에서 클릭 |
| 확장성 | 🟡 제한적 | 🟢 무제한 |
| 비용 | 🔴 높음 (서버) | 🟢 낮음 |

### 핵심 장점
1. ✅ **단순함**: 복잡한 지표 계산 불필요
2. ✅ **안정성**: 트레이딩뷰의 검증된 백엔드
3. ✅ **유연성**: 전략 변경이 즉시 가능
4. ✅ **확장성**: 여러 전략 동시 운영 가능
5. ✅ **비용**: API 호출 최소화

---

## 📌 구현 우선순위

### Phase 1: 기본 기능 (1일)
- ✅ KIS API 인증
- ✅ 텔레그램 봇 기본 명령어
- ✅ 매수 주문 실행
- ✅ 잔고 조회

### Phase 2: 매매 로직 (1일)
- ✅ 포지션 관리
- ✅ 익절 로직 (3% 50% 매도)
- ✅ 트레일링 스톱
- ✅ 손절 로직

### Phase 3: 알림 연동 (0.5일)
- ✅ 트레이딩뷰 웹훅 수신
- ✅ JSON 파싱 및 검증
- ✅ 자동 매수 실행

### Phase 4: 고도화 (0.5일)
- ✅ 설정 파일 관리
- ✅ 로깅 및 성과 추적
- ✅ 에러 처리 강화

**총 예상 시간**: 3일

---

## 🎯 다음 단계

1. **즉시 구현 시작 여부 확인**
2. **텔레그램 봇 토큰 준비**
3. **트레이딩뷰 알림 전략 확인**
4. **매수 금액 등 설정값 확인**

준비되셨으면 바로 구현을 시작하겠습니다! 🚀
