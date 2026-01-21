# 트레이딩뷰 → 텔레그램 직접 연결 가이드

**목적**: 트레이딩뷰 알림을 텔레그램으로 **즉시** 받기 (자동매매 없음)

---

## 🚀 설정 방법

### 1단계: 텔레그램 봇 생성

#### 1.1. @BotFather와 대화
1. 텔레그램 앱 열기
2. 검색: `@BotFather`
3. `/newbot` 입력
4. 봇 이름: `TradingView Alert Bot`
5. 봇 아이디: `tradingview_alert_bot` (고유해야 함)

**결과**:
```
Done! Congratulations on your new bot. You will find it at t.me/tradingview_alert_bot.
You can now add a description, about section and profile picture for your bot.

Use this token to access the HTTP API:
123456789:ABCdefGHIjklMNOpqrsTUVwxyz

For a description of the Bot API, see this page: https://core.telegram.org/bots/api
```

**토큰 저장**: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

#### 1.2. Chat ID 확인

**방법 A: 봇과 대화 후 확인**
1. 생성한 봇과 대화 시작
2. `/start` 입력
3. 브라우저에서 접속:
   ```
   https://api.telegram.org/bot123456789:ABCdefGHIjklMNOpqrsTUVwxyz/getUpdates
   ```
   (위 URL에서 `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`를 본인 토큰으로 교체)

4. 결과에서 Chat ID 확인:
   ```json
   {
     "ok": true,
     "result": [
       {
         "update_id": 123456789,
         "message": {
           "message_id": 1,
           "from": {
             "id": 987654321,
             "is_bot": false,
             "first_name": "Your Name"
           },
           "chat": {
             "id": 987654321,  ← 이것이 Chat ID
             "first_name": "Your Name",
             "type": "private"
           },
           "date": 1234567890,
           "text": "/start"
         }
       }
     ]
   }
   ```

**Chat ID 저장**: `987654321`

**방법 B: @userinfobot 사용**
1. 텔레그램에서 `@userinfobot` 검색
2. 봇과 대화 시작
3. Chat ID가 즉시 표시됨

---

### 2단계: Webhook URL 생성

#### 기본 형식
```
https://api.telegram.org/bot<BOT_TOKEN>/sendMessage?chat_id=<CHAT_ID>&text=<MESSAGE>
```

#### 실제 예시
```
https://api.telegram.org/bot123456789:ABCdefGHIjklMNOpqrsTUVwxyz/sendMessage?chat_id=987654321&text=BUY%20005930%20삼성전자
```

#### 트레이딩뷰 변수 활용
트레이딩뷰에서는 다음 변수를 사용할 수 있습니다:
- `{{ticker}}` - 종목 코드
- `{{exchange}}` - 거래소
- `{{close}}` - 종가
- `{{time}}` - 시간

**최종 URL** (URL 인코딩 필요):
```
https://api.telegram.org/bot123456789:ABCdefGHIjklMNOpqrsTUVwxyz/sendMessage?chat_id=987654321&text=🚀%20매수%20신호%0A종목:%20{{ticker}}%0A가격:%20{{close}}%0A시간:%20{{time}}
```

---

### 3단계: 트레이딩뷰 알림 설정

#### 3.1. 차트 열기
1. **트레이딩뷰** 접속: https://tradingview.com
2. **종목 선택** (예: KOSPI:005930 삼성전자)
3. **차트 분석** (원하는 지표 추가)

#### 3.2. 알림 생성
1. **알림 아이콘** 클릭 (우측 상단 시계 아이콘)
2. **조건 설정**:
   - 예1: `EMA(50) crosses over EMA(200)` (골든크로스)
   - 예2: `RSI(14) < 30` (과매도)
   - 예3: `Close > MA(20)` (이동평균 돌파)
3. **알림 작업** 섹션에서:
   - ✅ **Webhook URL** 체크
   - **URL 입력**:
     ```
     https://api.telegram.org/bot<본인토큰>/sendMessage?chat_id=<본인Chat_ID>&text=BUY%20{{ticker}}
     ```

#### 3.3. 고급 메시지 형식 (이모지 포함)

**간단한 버전**:
```
https://api.telegram.org/bot123456789:ABC.../sendMessage?chat_id=987654321&text=BUY%20{{ticker}}%20at%20{{close}}
```

**상세한 버전** (URL 인코딩된 메시지):
```
https://api.telegram.org/bot123456789:ABC.../sendMessage?chat_id=987654321&text=🚀%20매수%20신호%0A%0A종목:%20{{ticker}}%0A거래소:%20{{exchange}}%0A가격:%20{{close}}원%0A시간:%20{{time}}%0A%0A전략:%20골든크로스
```

**실제 텔레그램 메시지 결과**:
```
🚀 매수 신호

종목: 005930
거래소: KOSPI
가격: 75000원
시간: 2024-01-21 09:30:00

전략: 골든크로스
```

---

### 4단계: URL 인코딩 도구

복잡한 메시지를 보낼 때는 URL 인코딩이 필요합니다.

**온라인 도구**: https://www.urlencoder.org

**예시**:
```
원본: 🚀 매수 신호\n종목: {{ticker}}
인코딩: %F0%9F%9A%80%20%EB%A7%A4%EC%88%98%20%EC%8B%A0%ED%98%B8%0A%EC%A2%85%EB%AA%A9:%20{{ticker}}
```

---

## 🧪 테스트 방법

### 브라우저에서 직접 테스트

1. 아래 URL을 브라우저 주소창에 붙여넣기:
   ```
   https://api.telegram.org/bot<본인토큰>/sendMessage?chat_id=<본인Chat_ID>&text=테스트%20메시지
   ```

2. 텔레그램에 "테스트 메시지"가 도착하면 성공!

### curl로 테스트

```bash
curl -X POST "https://api.telegram.org/bot123456789:ABC.../sendMessage?chat_id=987654321&text=테스트"
```

---

## 📊 실전 예시

### 예시 1: 단순 알림
```
https://api.telegram.org/bot123456789:ABC.../sendMessage?chat_id=987654321&text=BUY%20{{ticker}}
```

**결과**:
```
BUY 005930
```

### 예시 2: 상세 알림
```
https://api.telegram.org/bot123456789:ABC.../sendMessage?chat_id=987654321&text=매수신호%0A종목:%20{{ticker}}%0A가격:%20{{close}}
```

**결과**:
```
매수신호
종목: 005930
가격: 75000
```

### 예시 3: 이모지 + 상세 정보
```
https://api.telegram.org/bot123456789:ABC.../sendMessage?chat_id=987654321&text=🚀%20{{ticker}}%20매수%0A💰%20가격:%20{{close}}%0A⏰%20시간:%20{{time}}
```

**결과**:
```
🚀 005930 매수
💰 가격: 75000
⏰ 시간: 2024-01-21 09:30:00
```

---

## 🔧 문제 해결

### 1. 메시지가 오지 않음

**원인**:
- 토큰 또는 Chat ID 오류
- URL 인코딩 문제
- 봇과 대화 시작 안 함

**해결**:
1. 봇과 `/start` 대화
2. Chat ID 재확인
3. 브라우저로 직접 테스트

### 2. 한글이 깨짐

**원인**: URL 인코딩 필요

**해결**: https://www.urlencoder.org 사용

### 3. 특수문자 표시 안 됨

**해결**: 이모지 대신 일반 텍스트 사용
```
원본: 🚀 매수
대체: [매수] {{ticker}}
```

---

## 📋 체크리스트

- [ ] 텔레그램 봇 생성 (`@BotFather`)
- [ ] Bot Token 확보
- [ ] Chat ID 확보
- [ ] Webhook URL 생성
- [ ] 브라우저로 테스트
- [ ] 트레이딩뷰 알림 설정
- [ ] 실제 알림 수신 확인

---

## 🎯 요약

### 필요한 정보
1. **Bot Token**: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`
2. **Chat ID**: `987654321`

### Webhook URL 템플릿
```
https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>&text=BUY%20{{ticker}}
```

### 실제 URL 예시
```
https://api.telegram.org/bot123456789:ABCdefGHIjklMNOpqrsTUVwxyz/sendMessage?chat_id=987654321&text=BUY%20{{ticker}}%20at%20{{close}}
```

---

**이제 트레이딩뷰 알림이 실시간으로 텔레그램에 도착합니다!** 📱

**다음 단계**: Python 자동매매 서버 설정 →
