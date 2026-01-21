# 트레이딩뷰 Webhook 자동 연동 가이드

## 📌 개요

트레이딩뷰 알림을 **완전 자동**으로 텔레그램 봇에 연동하는 방법입니다.

```
트레이딩뷰 알림 발생
    ↓
Webhook URL로 POST 요청
    ↓
Python 서버가 수신
    ↓
텔레그램으로 알림 전송
    ↓
자동매매 실행
```

---

## 🚀 설정 방법

### 1단계: Webhook 서버 실행

```bash
cd /home/user/webapp
python tradingview_bot.py
```

서버가 시작되면 다음과 같은 로그가 출력됩니다:

```
🌐 Webhook 서버 시작: http://0.0.0.0:8080/webhook
📱 텔레그램 봇 시작...
✅ 시스템 준비 완료!
```

---

### 2단계: 공개 URL 확보

**로컬 PC에서 실행하는 경우**, 트레이딩뷰가 접근할 수 있도록 **공개 URL**이 필요합니다.

#### 옵션 A: ngrok (추천)

무료로 사용 가능한 터널링 서비스입니다.

1. **ngrok 설치**
   ```bash
   # Windows
   choco install ngrok
   
   # Mac
   brew install ngrok
   
   # Linux
   wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
   tar -xvf ngrok-v3-stable-linux-amd64.tgz
   sudo mv ngrok /usr/local/bin/
   ```

2. **ngrok 실행**
   ```bash
   ngrok http 8080
   ```

3. **공개 URL 확인**
   ```
   Forwarding  https://abc123.ngrok.io -> http://localhost:8080
   ```
   
   → **Webhook URL**: `https://abc123.ngrok.io/webhook`

#### 옵션 B: Cloudflare Tunnel (무료, 무제한)

1. **설치**
   ```bash
   # Windows
   winget install --id Cloudflare.cloudflared
   
   # Mac
   brew install cloudflared
   
   # Linux
   wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
   sudo mv cloudflared-linux-amd64 /usr/local/bin/cloudflared
   sudo chmod +x /usr/local/bin/cloudflared
   ```

2. **실행**
   ```bash
   cloudflared tunnel --url http://localhost:8080
   ```

3. **공개 URL 확인**
   ```
   https://random-id.trycloudflare.com
   ```

#### 옵션 C: 클라우드 서버 (AWS, GCP, Vultr 등)

고정 IP를 가진 서버에서 실행하면 공개 URL이 필요 없습니다.

```bash
# 예: http://your-server-ip:8080/webhook
```

---

### 3단계: 트레이딩뷰 알림 설정

#### 3-1. 알림 조건 생성

1. **트레이딩뷰** 접속: https://tradingview.com
2. **차트 열기** (예: 삼성전자, KOSPI:005930)
3. **알림 추가** (우측 상단 시계 아이콘)

#### 3-2. 알림 조건 설정

**예시 1: EMA 골든크로스**
```
조건: EMA(50) crosses over EMA(200)
```

**예시 2: RSI 과매도**
```
조건: RSI(14) < 30
```

**예시 3: 가격 돌파**
```
조건: 종가 > 이동평균(20)
```

#### 3-3. Webhook URL 설정

**알림 작업** 섹션에서:

1. **Webhook URL** 입력:
   ```
   https://your-ngrok-url.ngrok.io/webhook
   ```

2. **메시지 형식** (중요!):
   ```json
   {
     "action": "BUY",
     "ticker": "{{ticker}}",
     "price": "{{close}}",
     "time": "{{time}}"
   }
   ```

   또는 간단히:
   ```
   BUY {{ticker}}
   ```

3. **알림 이름**: "삼성전자 골든크로스"

4. **저장**

---

## 📊 메시지 형식

트레이딩뷰에서 보낼 수 있는 변수:

| 변수 | 설명 | 예시 |
|------|------|------|
| `{{ticker}}` | 종목 코드 | 005930 |
| `{{exchange}}` | 거래소 | KOSPI |
| `{{close}}` | 종가 | 75000 |
| `{{open}}` | 시가 | 74500 |
| `{{high}}` | 고가 | 75300 |
| `{{low}}` | 저가 | 74200 |
| `{{volume}}` | 거래량 | 1234567 |
| `{{time}}` | 시간 | 2024-01-15 09:30:00 |

---

## 🧪 테스트 방법

### 로컬 테스트 (서버 없이)

```bash
# curl로 직접 테스트
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"action":"BUY","ticker":"005930","price":"75000"}'
```

### ngrok 테스트

```bash
# ngrok URL로 테스트
curl -X POST https://your-ngrok-url.ngrok.io/webhook \
  -H "Content-Type: application/json" \
  -d '{"action":"BUY","ticker":"005930"}'
```

성공하면:
```json
{"status":"success","message":"Buy signal received for 005930"}
```

텔레그램으로 알림이 와야 합니다:
```
🚀 매수 신호 수신!
종목: 005930
가격: 75,000원
시간: 2024-01-15 09:30:00
```

---

## 🔒 보안 설정 (선택)

Webhook에 인증 토큰을 추가하여 보안을 강화할 수 있습니다.

### config.json에 추가:
```json
{
  "webhook": {
    "port": 8080,
    "secret_token": "your-secret-token-here"
  }
}
```

### 트레이딩뷰 메시지에 포함:
```json
{
  "token": "your-secret-token-here",
  "action": "BUY",
  "ticker": "{{ticker}}"
}
```

---

## 📋 전체 워크플로우

1. **트레이딩뷰**: EMA 골든크로스 발생
2. **Webhook 전송**: POST https://your-url.ngrok.io/webhook
3. **Python 서버**: Webhook 수신 → 텔레그램 알림
4. **텔레그램 봇**: "매수 신호 수신! 005930 삼성전자"
5. **자동매매**: KIS API로 매수 주문 실행
6. **모니터링**: 5초마다 가격 체크
7. **익절/손절**: 자동 매도

---

## ⚙️ 설정 파일 예시

**config.json**:
```json
{
  "telegram": {
    "bot_token": "123456789:ABCdefGHIjklMNOpqrsTUVwxyz",
    "chat_id": "987654321"
  },
  "kis": {
    "server": "vps"
  },
  "trading": {
    "enabled": true,
    "buy_amount": 1000000,
    "profit_target": 0.03,
    "trailing_stop": 0.02,
    "stop_loss": 0.025,
    "check_interval": 5
  },
  "webhook": {
    "port": 8080,
    "secret_token": ""
  }
}
```

---

## 🐛 문제 해결

### 1. Webhook이 수신되지 않음

**증상**: 트레이딩뷰 알림은 발생하지만 텔레그램으로 오지 않음

**해결**:
1. ngrok/cloudflared가 실행 중인지 확인
2. Webhook URL이 정확한지 확인 (https://로 시작)
3. 방화벽 설정 확인
4. 로그 확인:
   ```bash
   tail -f logs/trading_*.log
   ```

### 2. 인증 오류

**증상**: `401 Unauthorized`

**해결**:
1. `config.json`에 `secret_token` 확인
2. 트레이딩뷰 메시지에 토큰 포함 여부 확인

### 3. 매수 실패

**증상**: 알림은 오지만 매수되지 않음

**해결**:
1. `kis_devlp.yaml` 설정 확인
2. 계좌 잔고 확인
3. 시장 개장 시간 확인
4. 로그 확인:
   ```bash
   grep "매수" logs/trading_*.log
   ```

---

## 📚 참고 자료

- **ngrok 공식 문서**: https://ngrok.com/docs
- **Cloudflare Tunnel**: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps
- **트레이딩뷰 Webhook**: https://www.tradingview.com/support/solutions/43000529348
- **텔레그램 봇 API**: https://core.telegram.org/bots/api

---

## 🎯 요약

| 단계 | 명령/설정 |
|------|-----------|
| 1. 서버 실행 | `python tradingview_bot.py` |
| 2. 터널링 | `ngrok http 8080` |
| 3. Webhook URL | https://abc123.ngrok.io/webhook |
| 4. 트레이딩뷰 | 알림 설정 → Webhook URL 입력 |
| 5. 테스트 | curl로 POST 요청 |
| 6. 자동매매 | ✅ 완전 자동화! |

---

**이제 트레이딩뷰 알림이 발생하면 자동으로 매수됩니다!** 🚀
