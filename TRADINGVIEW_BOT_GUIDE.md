# 트레이딩뷰 자동매매 시스템 사용 가이드

**작성일**: 2026-01-19  
**파일**: `tradingview_bot.py`

---

## 🎯 시스템 개요

### 작동 방식
```
트레이딩뷰 알림 
    ↓
텔레그램으로 전송 (수동/자동)
    ↓
자동 매수 (설정 금액)
    ↓
실시간 모니터링 (5초 간격)
    ↓
┌────────────────┬──────────────┐
│ 3% 수익 시     │ 손절 시      │
│ 50% 익절      │ 전량 매도    │
│ 트레일링 스톱  │             │
└────────────────┴──────────────┘
```

---

## 📋 사전 준비

### 1. 환경 설정

#### Python 패키지 설치
```bash
pip install python-telegram-bot requests pyyaml pycryptodome
```

#### 파일 확인
```bash
ls -la
# 필요 파일:
# - tradingview_bot.py
# - kis_devlp.yaml (이미 존재)
# - config.json (자동 생성됨)
```

---

### 2. 텔레그램 봇 생성

#### 2.1. @BotFather와 대화
1. 텔레그램 검색: `@BotFather`
2. `/newbot` 입력
3. 봇 이름 입력: `My Trading Bot`
4. 봇 아이디 입력: `my_trading_bot` (고유해야 함)
5. **봇 토큰 저장**: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

#### 2.2. Chat ID 확인
1. 생성한 봇과 대화 시작 (`/start`)
2. 브라우저에서 접속:
   ```
   https://api.telegram.org/bot<봇토큰>/getUpdates
   ```
3. `"chat":{"id":987654321}` 부분에서 ID 확인
4. **Chat ID 저장**: `987654321`

---

### 3. config.json 설정

#### 첫 실행 시
```bash
python3 tradingview_bot.py
# config.json 자동 생성됨
```

#### config.json 수정
```json
{
  "telegram": {
    "bot_token": "123456789:ABCdefGHIjklMNOpqrsTUVwxyz",
    "chat_id": "987654321"
  },
  "kis": {
    "server": "vps",      // prod: 실전, vps: 모의
    "account": "12345678",
    "product": "01"
  },
  "trading": {
    "enabled": false,     // true: 자동매매 시작
    "buy_amount": 1000000,  // 매수 금액 (원)
    "profit_target": 0.03,  // 익절 목표 (3%)
    "trailing_stop": 0.02,  // 트레일링 (-2%)
    "stop_loss": 0.025,     // 손절 (-2.5%)
    "check_interval": 5     // 모니터링 간격 (초)
  }
}
```

---

## 🚀 실행 방법

### 1. 시스템 시작
```bash
cd /home/user/webapp
python3 tradingview_bot.py
```

**출력 예시**:
```
================================================================================
트레이딩뷰 연동 자동매매 시스템
================================================================================
✅ KISAuth 초기화 (vps)
✅ 기존 토큰 사용 (만료: 2026-01-20 15:30:00)
✅ TradingSystem 초기화 완료
✅ TelegramBot 초기화
🚀 포지션 모니터링 시작
🚀 텔레그램 봇 시작
```

### 2. 텔레그램에서 봇과 대화

#### 기본 명령어
```
/start   - 봇 시작
/status  - 현재 상태 확인
/on      - 자동매매 활성화
/off     - 자동매매 비활성화
/positions - 보유 종목 확인
/balance - 잔고 조회
/help    - 도움말
```

---

## 📊 트레이딩뷰 알림 설정

### 방법 1: 수동 전송 (간단, 추천)

#### 트레이딩뷰 알림 설정
1. 차트에서 지표 추가 (예: EMA 50/200)
2. 알림 생성
3. 조건 설정: `EMA(50) > EMA(200)` (골든크로스)
4. 알림 동작: **알림창 표시** 또는 **이메일**

#### 알림 발생 시
1. 트레이딩뷰에서 알림 확인
2. 종목 정보 확인
3. 텔레그램 봇으로 전송:
   ```
   BUY 005930 삼성전자
   ```

**형식**: `BUY [종목코드] [종목명]`

#### 봇 응답
```
🔄 매수 주문 중...
종목: 삼성전자 (005930)

✅ 매수 완료

종목: 삼성전자 (005930)
가격: 60,000원
수량: 16주
금액: 960,000원
```

---

### 방법 2: 자동 전송 (고급, 웹훅 필요)

#### 중계 서버 설정 (Flask)

**webhook_server.py**:
```python
from flask import Flask, request
import requests

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = "YOUR_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"

@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    data = request.json
    
    # 트레이딩뷰 → 텔레그램
    message = f"BUY {data['ticker']} {data['name']}"
    
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": message}
    )
    
    return 'OK', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

#### 트레이딩뷰 알림 설정
1. 알림 동작: **Webhook URL**
2. URL: `https://your-server.com/webhook`
3. 메시지 본문:
   ```json
   {
     "ticker": "{{ticker}}",
     "name": "종목명",
     "price": {{close}}
   }
   ```

---

## 💰 매매 로직 상세

### 1단계: 진입
- 트레이딩뷰 알림 수신
- 자동매매 활성화 확인
- 중복 진입 방지
- **시장가 매수** (설정 금액)

### 2단계: 1차 익절 (3%)
```python
if 수익률 >= 3%:
    50% 매도
    트레일링 스톱 활성화 (-2%)
```

**예시**:
- 매수가: 60,000원
- 3% 도달: 61,800원
- 16주 → 8주 매도 (익절)
- 잔여 8주: 트레일링 스톱

### 3단계: 트레일링 스톱
```python
고점 갱신:
    고점 = max(고점, 현재가)
    트레일링 가격 = 고점 × 0.98

if 현재가 <= 트레일링 가격:
    잔여 전량 매도
```

**예시**:
- 고점: 62,000원
- 트레일링: 60,760원 (-2%)
- 현재가 60,760원 이하 → 매도

### 손절
```python
if 수익률 <= -2.5%:
    전량 매도
```

---

## 📱 텔레그램 알림 예시

### 매수 알림
```
✅ 매수 완료

종목: 삼성전자 (005930)
가격: 60,000원
수량: 16주
금액: 960,000원
```

### 1차 익절 알림
```
💰 [1차 익절]
종목: 삼성전자
수익률: +3.00%
매도: 8주 (50%)
잔여: 8주
```

### 트레일링 스톱 알림
```
📈 [트레일링 스톱]
종목: 삼성전자
고점: 62,000원
매도가: 60,760원
최종 수익률: +1.27%
```

### 손절 알림
```
🛑 [손절]
종목: 삼성전자
손실률: -2.50%
```

---

## 🔧 설정 조정

### 매수 금액 변경
```bash
# config.json 수정
"buy_amount": 2000000  # 200만원
```

### 익절 비율 변경
```bash
"profit_target": 0.05  # 5%
```

### 트레일링 비율 변경
```bash
"trailing_stop": 0.03  # 3%
```

### 손절 비율 변경
```bash
"stop_loss": 0.03  # 3%
```

### 모니터링 간격 변경
```bash
"check_interval": 10  # 10초
```

---

## 🐛 문제 해결

### 봇이 응답하지 않음
```bash
# 1. config.json 확인
cat config.json

# 2. 텔레그램 토큰 확인
# bot_token, chat_id 정확한지 확인

# 3. 재시작
Ctrl+C (중지)
python3 tradingview_bot.py
```

### 매수 주문 실패
```bash
# 1. 잔고 확인
/balance

# 2. kis_devlp.yaml 확인
# 모의투자 계좌 설정 확인

# 3. 로그 확인
tail -f logs/trading_20260119.log
```

### 토큰 오류
```bash
# 토큰 파일 삭제 후 재발급
rm -rf ~/KIS/config/KIS*
python3 tradingview_bot.py
```

---

## 📊 성과 추적

### 포지션 파일
```bash
cat positions.json
```

**내용**:
```json
{
  "005930": {
    "code": "005930",
    "name": "삼성전자",
    "buy_price": 60000,
    "quantity": 16,
    "strategy": "트레이딩뷰",
    "entry_time": "2026-01-19T15:30:00",
    "status": "active",
    "peak_price": 60000
  }
}
```

### 로그 파일
```bash
tail -f logs/trading_20260119.log
```

---

## ⚠️ 주의사항

1. **모의투자로 충분히 테스트**
   - 최소 1주일 이상 모의투자
   - 전략 검증 후 실전 투자

2. **리스크 관리**
   - 종목당 1~2% 자본 배분 권장
   - 최대 5~10개 종목 동시 보유

3. **알림 검증**
   - 잘못된 종목코드 주의
   - 수동으로 확인 후 전송 권장

4. **시스템 모니터링**
   - 로그 주기적 확인
   - 텔레그램 알림 확인

5. **전략 최적화**
   - 트레이딩뷰 백테스팅 활용
   - 승률 60% 이상 전략 사용

---

## 🎯 권장 트레이딩뷰 전략

### 1. 골든크로스 (추세 추종)
```
조건: EMA(50) crosses over EMA(200)
승률: 50~60%
장점: 대세 상승 포착
```

### 2. RSI 과매도 반등
```
조건: RSI(14) < 30 AND 
      RSI(14) crosses over 30
승률: 55~65%
장점: 단기 반등 포착
```

### 3. 볼린저밴드 하단 터치
```
조건: Close < BB Lower AND
      Volume > Volume MA(20) × 1.5
승률: 50~60%
장점: 변동성 돌파 포착
```

---

## 📌 요약

1. ✅ **설치**: Python 패키지 설치
2. ✅ **텔레그램**: 봇 생성 및 토큰 확보
3. ✅ **설정**: config.json 수정
4. ✅ **실행**: `python3 tradingview_bot.py`
5. ✅ **활성화**: `/on` 명령어
6. ✅ **알림**: 트레이딩뷰 알림 → 텔레그램
7. ✅ **매매**: 자동 매수 → 익절/손절

---

**작성자**: AI Code Assistant  
**업데이트**: 2026-01-19
