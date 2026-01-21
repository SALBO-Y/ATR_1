# 트레이딩뷰 알림에 종목명 포함하기

**문제**: 트레이딩뷰 변수에는 **종목명이 없습니다!**

트레이딩뷰에서 제공하는 변수:
- ✅ `{{ticker}}` - 종목 코드 (예: 005930)
- ✅ `{{exchange}}` - 거래소 (예: KOSPI)
- ✅ `{{close}}` - 현재가 (예: 75000)
- ❌ 종목명 - **없음!**

---

## 🔧 해결 방법 3가지

### 방법 1: 수동으로 종목명 입력 (간단, 알림만)

**트레이딩뷰 메시지에 직접 작성**:

#### URL (귀하의 봇 토큰 사용):

```
https://api.telegram.org/bot8589662322:AAEeCIf0Poce5kmYD43zYwdYSp6MzTdwOOM/sendMessage?chat_id=5030462236&text=%F0%9F%9A%80%20%EB%A7%A4%EC%88%98%20%EC%8B%A0%ED%98%B8%0A%0A%EC%A2%85%EB%AA%A9%3A%20{{ticker}}%20%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90%0A%EA%B0%80%EA%B2%A9%3A%20{{close}}%EC%9B%90%0A%EC%8B%9C%EA%B0%84%3A%20{{time}}
```

**결과**:
```
🚀 매수 신호

종목: 005930 삼성전자
가격: 75000원
시간: 2024-01-21 09:30:00
```

**장점**:
- ✅ 간단함 (Python 서버 불필요)
- ✅ 즉시 사용 가능

**단점**:
- ❌ 종목마다 알림을 따로 만들어야 함
- ❌ 자동매매 불가

---

### 방법 2: Python 서버로 자동 종목명 조회 ⭐ **추천**

**Python 서버가 자동으로 종목명 조회!**

#### 트레이딩뷰 Webhook URL (귀하의 서버):
```
https://your-trading-bot.ngrok.app/webhook
```

#### 트레이딩뷰 메시지 (간단하게):
```json
{
  "action": "BUY",
  "ticker": "{{ticker}}"
}
```

#### Python 서버가 보내는 텔레그램 메시지:
```
🚀 매수 체결 (Webhook)

종목: [005930] 삼성전자
가격: 75,000원
수량: 13주
금액: 975,000원
```

**장점**:
- ✅ 종목명 자동 조회 (KIS API)
- ✅ 자동 매수 실행
- ✅ 익절/손절 자동화
- ✅ 포지션 관리
- ✅ 하나의 알림으로 모든 종목 처리

**구현 완료!**
- `tradingview_bot.py`에 `get_stock_name()` 함수 추가
- 2단계 조회: 마스터 API → 현재가 API

---

### 방법 3: 종목별 고정 메시지 (중간)

**종목별로 알림 따로 생성**

#### 삼성전자 (005930):
```
https://api.telegram.org/bot8589662322:AAEeCIf0Poce5kmYD43zYwdYSp6MzTdwOOM/sendMessage?chat_id=5030462236&text=%F0%9F%9A%80%20%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90%20%EB%A7%A4%EC%88%98%0A%EC%A2%85%EB%AA%A9%3A%20{{ticker}}%0A%EA%B0%80%EA%B2%A9%3A%20{{close}}%EC%9B%90
```

#### SK하이닉스 (000660):
```
https://api.telegram.org/bot8589662322:AAEeCIf0Poce5kmYD43zYwdYSp6MzTdwOOM/sendMessage?chat_id=5030462236&text=%F0%9F%9A%80%20SK%ED%95%98%EC%9D%B4%EB%8B%89%EC%8A%A4%20%EB%A7%A4%EC%88%98%0A%EC%A2%85%EB%AA%A9%3A%20{{ticker}}%0A%EA%B0%80%EA%B2%A9%3A%20{{close}}%EC%9B%90
```

**장점**:
- ✅ 종목명 표시 가능
- ✅ Python 서버 불필요

**단점**:
- ❌ 종목마다 알림 따로 설정
- ❌ 자동매매 불가

---

## 🎯 추천 방법

### 지금 당장 알림만 받고 싶다면 → **방법 1**

**즉시 사용 가능한 URL** (귀하의 봇):

**기본 버전** (종목명 없음):
```
https://api.telegram.org/bot8589662322:AAEeCIf0Poce5kmYD43zYwdYSp6MzTdwOOM/sendMessage?chat_id=5030462236&text=%F0%9F%9A%80%20{{ticker}}%20%EB%A7%A4%EC%88%98%0A%EA%B0%80%EA%B2%A9%3A%20{{close}}%EC%9B%90
```

**삼성전자 전용** (종목명 포함):
```
https://api.telegram.org/bot8589662322:AAEeCIf0Poce5kmYD43zYwdYSp6MzTdwOOM/sendMessage?chat_id=5030462236&text=%F0%9F%9A%80%20%EB%A7%A4%EC%88%98%20%EC%8B%A0%ED%98%B8%0A%0A%EC%A2%85%EB%AA%A9%3A%20{{ticker}}%20%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90%0A%EA%B0%80%EA%B2%A9%3A%20{{close}}%EC%9B%90%0A%EC%8B%9C%EA%B0%84%3A%20{{time}}
```

---

### 자동매매를 원한다면 → **방법 2** ⭐

**설정 순서**:

1. **`config.json` 생성** (귀하의 정보):
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
    "enabled": true,
    "buy_amount": 1000000
  },
  "webhook": {
    "enabled": true,
    "port": 8080
  }
}
```

2. **서버 시작**:
```bash
cd /home/user/webapp
python tradingview_bot.py
```

3. **ngrok 시작**:
```bash
ngrok http 8080 --domain=your-trading-bot.ngrok.app
```

4. **트레이딩뷰 Webhook URL**:
```
https://your-trading-bot.ngrok.app/webhook
```

5. **트레이딩뷰 메시지**:
```json
{
  "action": "BUY",
  "ticker": "{{ticker}}"
}
```

6. **결과** (자동으로 종목명 조회):
```
🚀 매수 체결 (Webhook)

종목: [005930] 삼성전자
가격: 75,000원
수량: 13주
금액: 975,000원
```

---

## 📊 비교표

| 항목 | 방법 1 (수동) | 방법 2 (자동) |
|------|---------------|---------------|
| 종목명 표시 | 수동 입력 | ✅ 자동 조회 |
| 설정 난이도 | ⭐ 쉬움 | ⭐⭐⭐ 어려움 |
| 자동매매 | ❌ | ✅ |
| 익절/손절 | ❌ | ✅ |
| Python 서버 | 불필요 | 필수 |
| 여러 종목 | 알림 따로 | 한 번 설정 |
| 추천도 | ⭐⭐ | ⭐⭐⭐⭐⭐ |

---

## 🎮 테스트

### 방법 1 테스트 (브라우저)

**삼성전자 알림 URL** (복사해서 브라우저에 붙여넣기):
```
https://api.telegram.org/bot8589662322:AAEeCIf0Poce5kmYD43zYwdYSp6MzTdwOOM/sendMessage?chat_id=5030462236&text=%F0%9F%9A%80%20005930%20%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90%20%EB%A7%A4%EC%88%98%0A%EA%B0%80%EA%B2%A9%3A%2075000%EC%9B%90
```

**텔레그램 결과**:
```
🚀 005930 삼성전자 매수
가격: 75000원
```

---

### 방법 2 테스트 (Python 서버)

```bash
# 서버가 실행 중이어야 함
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"action":"BUY","ticker":"005930"}'
```

**텔레그램 결과**:
```
🚀 매수 체결 (Webhook)

종목: [005930] 삼성전자
가격: 75,000원
수량: 13주
금액: 975,000원
```

---

## ✅ 요약

### 귀하의 상황에 맞는 선택:

**지금 당장 알림만 받고 싶다면**:
→ **방법 1** 사용
→ URL: `https://api.telegram.org/bot8589662322:AAEeCIf0Poce5kmYD43zYwdYSp6MzTdwOOM/sendMessage?chat_id=5030462236&text={{ticker}}%20매수`

**자동매매 + 종목명 자동 조회를 원한다면**:
→ **방법 2** 사용
→ `python tradingview_bot.py` 실행
→ ngrok으로 공개 URL 생성
→ 트레이딩뷰 Webhook 설정

---

**어떤 방법을 원하시나요?** 🤔

1. **방법 1**: 지금 당장 알림만 (종목명 수동 입력)
2. **방법 2**: 자동매매 + 종목명 자동 조회 (추천)
