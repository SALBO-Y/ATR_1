# 🔗 트레이딩뷰 알림 연동 완벽 가이드

**작성일**: 2026-01-19  
**대상**: tradingview_bot.py 사용자

---

## 🎯 3가지 연동 방법 비교

| 방법 | 난이도 | 비용 | 자동화 | 안정성 | 추천 대상 |
|------|--------|------|--------|--------|-----------|
| **수동 전송** | ⭐ | 무료 | ❌ | ⭐⭐⭐ | 초보자, 신중한 매매 |
| **IFTTT** | ⭐⭐ | 무료 | ✅ | ⭐⭐⭐ | 일반 사용자 |
| **Webhook 서버** | ⭐⭐⭐ | VPS 필요 | ✅ | ⭐⭐⭐⭐ | 고급 사용자 |

---

## 방법 1: 수동 전송 ⭐ (추천!)

### 왜 추천하나요?
- ✅ 5분만에 시작 가능
- ✅ 추가 설정 불필요
- ✅ 잘못된 매매 방지 (눈으로 확인)
- ✅ 안정적

### 설정 순서

#### 1️⃣ 트레이딩뷰 알림 만들기 (3분)

```
1. 차트 열기 (예: KOSPI:005930 삼성전자)

2. 지표 추가
   - Pine Script 버튼 클릭
   - "EMA" 검색 → "Moving Average Exponential" 추가
   - 두 번 추가 (50, 200)

3. 알림 생성
   - 알림 아이콘(⏰) 클릭
   - 조건 선택:
     • EMA(50) crosses over EMA(200)
   
4. 알림 설정
   ✅ Alert name: "삼성전자 골든크로스"
   ✅ 알림창 표시
   ✅ 알림음
   ✅ 이메일 (선택)
   만료: 만료 안 함
   
5. 저장
```

#### 2️⃣ 알림 발생 시 동작 (1분)

```
1. 트레이딩뷰 알림 확인
   [🔔 삼성전자 골든크로스]
   EMA(50) crosses over EMA(200)
   KOSPI:005930

2. 텔레그램 앱 열기

3. 봇에게 메시지 전송:
   BUY 005930 삼성전자

4. 봇 응답 확인:
   ✅ 매수 완료
   종목: 삼성전자 (005930)
   가격: 60,000원
   수량: 16주
```

### 💡 팁
- 알림음을 다르게 설정 (중요도별)
- 여러 전략을 동시 운영 가능
- 시간이 있을 때만 매매

---

## 방법 2: IFTTT 자동화 ⭐⭐ (추천!)

### 왜 좋은가요?
- ✅ 완전 자동화
- ✅ 무료 (월 5개 앱플릿)
- ✅ 코딩 불필요
- ✅ 안정적

### 설정 순서 (20분)

#### 1️⃣ IFTTT 계정 생성 (5분)

```
1. https://ifttt.com 접속
2. "Sign up" 클릭
3. 이메일/비밀번호 입력
4. 이메일 인증
```

#### 2️⃣ Webhooks 설정 (5분)

```
1. 상단 검색창: "Webhooks"
2. "Webhooks" 서비스 클릭
3. "Settings" 버튼
4. "Documentation" 클릭
5. URL 복사 (나중에 사용):
   
   https://maker.ifttt.com/trigger/{event}/with/key/YOUR_KEY
   
   예시:
   https://maker.ifttt.com/trigger/tradingview_alert/with/key/dX1Y2Z3A4B5C
```

#### 3️⃣ Applet 만들기 (5분)

```
1. IFTTT 홈 → "Create" 버튼

2. "If This" 클릭
   - 검색: Webhooks
   - "Receive a web request" 선택
   - Event Name: tradingview_alert
   - "Create trigger"

3. "Then That" 클릭
   - 검색: Telegram
   - "Send message" 선택
   - 텔레그램 계정 연결 (최초 1회)
   - 메시지 형식:
     
     BUY {{Value1}} {{Value2}}
   
   - Target chat: @YOUR_BOT_USERNAME
   - "Create action"

4. "Continue" → "Finish"
```

#### 4️⃣ 트레이딩뷰 알림 설정 (5분)

```
1. 차트에서 알림 생성

2. 조건 설정 (골든크로스 등)

3. Notifications 탭:
   ✅ Webhook URL 체크

4. URL 입력:
   https://maker.ifttt.com/trigger/tradingview_alert/with/key/YOUR_KEY

5. Message (JSON 형식):
   {"value1":"{{ticker}}", "value2":"삼성전자"}
   
   또는 Pine Script에서:
   {"value1":"005930", "value2":"삼성전자"}

6. 저장
```

#### 5️⃣ 테스트 (2분)

```
1. IFTTT Webhooks Documentation 페이지

2. "Test It" 섹션:
   - value1: 005930
   - value2: 삼성전자
   
3. "Test It" 버튼 클릭

4. 텔레그램 봇에서 메시지 확인:
   BUY 005930 삼성전자

5. 성공! ✅
```

### 작동 흐름

```
트레이딩뷰 알림 발생
    ↓
Webhook 전송 (자동)
    ↓
IFTTT 수신
    ↓
텔레그램 메시지 전송 (자동)
    ↓
BUY 005930 삼성전자
    ↓
봇이 자동 매수!
```

### 💡 고급 팁

#### 여러 전략 운영
```
1. Applet 1: tradingview_alert_1 (골든크로스)
2. Applet 2: tradingview_alert_2 (RSI 과매도)
3. Applet 3: tradingview_alert_3 (볼린저밴드)
```

#### 조건부 실행
```
1. IFTTT Filter 사용
2. 특정 시간대만 알림
3. 특정 종목만 필터링
```

---

## 방법 3: Webhook 서버 ⭐⭐⭐

### 왜 사용하나요?
- ✅ 완전한 제어
- ✅ 무제한 알림
- ✅ 로깅/통계
- ✅ 커스터마이징

### 필요한 것
1. VPS 서버 (예: AWS, DigitalOcean)
2. Python 환경
3. 공개 IP 주소

### 설정 순서 (30분)

#### 1️⃣ 서버 준비

```bash
# 패키지 설치
pip install flask requests

# webhook_server.py 다운로드
# (이미 생성됨: /home/user/webapp/webhook_server.py)
```

#### 2️⃣ 설정 수정

```python
# webhook_server.py 열기
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"
WEBHOOK_SECRET = "your-secret-key-12345"
```

#### 3️⃣ 서버 실행

```bash
python3 webhook_server.py

# 출력:
# ================================================================================
# 트레이딩뷰 Webhook → 텔레그램 중계 서버
# ================================================================================
# 
# 🔑 Webhook Secret: your-secret-key-12345
# 📡 Webhook URL: http://YOUR_SERVER_IP:5000/webhook
# 💬 Telegram Chat ID: 987654321
# 
# 서버 시작 중...
```

#### 4️⃣ 방화벽 설정

```bash
# 포트 5000 열기
sudo ufw allow 5000

# 또는 AWS Security Group에서 5000 포트 허용
```

#### 5️⃣ 트레이딩뷰 알림 설정

```
1. 알림 생성

2. Webhook URL:
   http://YOUR_SERVER_IP:5000/webhook

3. Message (JSON):
   {
     "secret": "your-secret-key-12345",
     "action": "buy",
     "ticker": "{{ticker}}",
     "name": "삼성전자",
     "price": {{close}},
     "strategy": "골든크로스"
   }

4. 저장
```

#### 6️⃣ 테스트

```bash
# 로컬 테스트
curl -X POST http://localhost:5000/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "your-secret-key-12345",
    "action": "buy",
    "ticker": "005930",
    "name": "삼성전자",
    "price": 60000,
    "strategy": "테스트"
  }'

# 텔레그램 봇에서 메시지 확인
```

### 작동 흐름

```
트레이딩뷰 알림
    ↓
HTTP POST → http://YOUR_SERVER:5000/webhook
    ↓
Flask 서버 수신
    ↓
JSON 파싱 및 검증
    ↓
텔레그램 메시지 전송
    ↓
BUY 005930 삼성전자
    ↓
봇이 자동 매수!
```

### 서버 로그 예시

```
2026-01-19 15:30:00 [INFO] 📨 Webhook 수신: {"secret":"***","action":"buy","ticker":"005930","name":"삼성전자","price":60000,"strategy":"골든크로스"}
2026-01-19 15:30:01 [INFO] ✅ 텔레그램 전송 성공: 🔔 트레이딩뷰 알림...
```

---

## 🎯 어떤 방법을 선택할까?

### 초보자 → **수동 전송** ⭐
- 안전하게 시작
- 매매 확인 후 실행
- 무료

### 일반 사용자 → **IFTTT** ⭐⭐
- 완전 자동화
- 설정 간단
- 무료

### 고급 사용자 → **Webhook 서버** ⭐⭐⭐
- 완전한 제어
- 확장 가능
- VPS 비용 ($5/월)

---

## 📊 추천 순서

### 1주차: 수동 전송
- 시스템 이해
- 전략 테스트
- 매매 익숙해지기

### 2주차: IFTTT 자동화
- 자동화 테스트
- 알림 정확도 확인
- 24시간 운영

### 1개월 후: Webhook 서버 (선택)
- 대량 알림 처리
- 로깅/통계
- 커스터마이징

---

## ⚠️ 주의사항

### 보안
- ✅ WEBHOOK_SECRET 사용
- ✅ HTTPS 사용 (가능하면)
- ✅ IP 화이트리스트

### 테스트
- ✅ 모의투자로 충분히 테스트
- ✅ 소액으로 실전 테스트
- ✅ 알림 정확도 검증

### 모니터링
- ✅ 텔레그램 알림 확인
- ✅ 로그 파일 확인
- ✅ 서버 상태 체크

---

## 🎉 요약

| 방법 | 설정 시간 | 자동화 | 추천 |
|------|----------|--------|------|
| 수동 전송 | 5분 | ❌ | ✅ 초보자 |
| IFTTT | 20분 | ✅ | ✅ 일반 사용자 |
| Webhook | 30분+ | ✅ | 고급 사용자 |

**대부분의 경우 IFTTT를 추천합니다!** 🎯

---

**작성**: AI Code Assistant  
**업데이트**: 2026-01-19
