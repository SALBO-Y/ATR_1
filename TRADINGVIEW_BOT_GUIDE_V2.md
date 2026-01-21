# 트레이딩뷰 Webhook 자동매매 시스템 가이드

**작성일**: 2026-01-21  
**버전**: 2.0 (Webhook 완전 자동화)

---

## 🎯 시스템 개요

### 작동 방식

**완전 자동화 (Webhook)**
```
트레이딩뷰 알림 발생
    ↓
Webhook POST 요청
    ↓
Python 서버 수신
    ↓
자동 매수 실행
    ↓
텔레그램 알림
    ↓
실시간 모니터링 (5초)
    ↓
3% 익절/손절 자동 실행
```

**수동 모드 (텔레그램)**
```
트레이딩뷰 알림 확인
    ↓
텔레그램 봇에 입력
    ↓
자동 매수 실행
```

---

## 📋 사전 준비

### 1. 패키지 설치

```bash
cd /home/user/webapp
pip install -r requirements_new.txt

# 또는 개별 설치:
pip install python-telegram-bot flask pyyaml pycryptodome requests
```

### 2. 텔레그램 봇 생성

#### 2.1. @BotFather 사용
1. 텔레그램에서 `@BotFather` 검색
2. `/newbot` 명령 실행
3. 봇 이름: `My Trading Bot`
4. 봇 아이디: `my_trading_bot` (고유 값)
5. **토큰 저장**: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

#### 2.2. Chat ID 확인
1. 생성한 봇과 대화 시작 (`/start`)
2. 브라우저로 접속:
   ```
   https://api.telegram.org/bot<봇토큰>/getUpdates
   ```
3. `"chat":{"id":987654321}` 에서 ID 확인
4. **Chat ID 저장**: `987654321`

---

### 3. 설정 파일

#### config.json 설정

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
    "enabled": true,
    "port": 8080,
    "secret_token": ""
  }
}
```

#### kis_devlp.yaml (이미 설정됨)

계좌 정보는 자동으로 가져옵니다:
- **모의투자**: `my_paper_stock` + `my_prod`
- **실전투자**: `my_acct_stock` + `my_prod`

---

## 🚀 실행 방법

### 방법 1: Webhook 자동화 (추천)

#### 1단계: 서버 실행
```bash
cd /home/user/webapp
python tradingview_bot.py
```

출력:
```
================================================================================
트레이딩뷰 연동 자동매매 시스템
================================================================================
🌐 Webhook 서버 시작: http://0.0.0.0:8080/webhook
💡 헬스 체크: http://0.0.0.0:8080/health
📱 텔레그램 봇 시작...
✅ 시스템 준비 완료!
```

#### 2단계: 공개 URL 확보

**로컬 PC에서 실행하는 경우** ngrok 또는 Cloudflare Tunnel 사용:

**ngrok (무료)**
```bash
# 설치
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install ngrok

# 실행
ngrok http 8080
```

**Cloudflare Tunnel (무료, 무제한)**
```bash
# 설치
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
sudo mv cloudflared-linux-amd64 /usr/local/bin/cloudflared
sudo chmod +x /usr/local/bin/cloudflared

# 실행
cloudflared tunnel --url http://localhost:8080
```

**공개 URL 확인**:
```
https://abc123.ngrok.io
또는
https://random-id.trycloudflare.com
```

#### 3단계: 트레이딩뷰 알림 설정

1. **트레이딩뷰** 접속: https://tradingview.com
2. **차트 열기** (예: KOSPI:005930)
3. **알림 추가** (시계 아이콘)
4. **조건 설정**:
   - 예: `EMA(50) crosses over EMA(200)`
   - 예: `RSI(14) < 30`
5. **Webhook URL** 입력:
   ```
   https://abc123.ngrok.io/webhook
   ```
6. **메시지 형식**:
   ```json
   {
     "action": "BUY",
     "ticker": "{{ticker}}",
     "price": "{{close}}",
     "time": "{{time}}"
   }
   ```
7. **저장**

#### 4단계: 테스트

```bash
# curl로 테스트
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"action":"BUY","ticker":"005930"}'
```

성공하면 텔레그램으로 알림이 옵니다!

---

### 방법 2: 수동 모드 (텔레그램만)

#### config.json 수정
```json
{
  "webhook": {
    "enabled": false
  }
}
```

#### 실행
```bash
python tradingview_bot.py
```

#### 사용법
트레이딩뷰 알림 발생 시:
```
BUY 005930 삼성전자
```
형식으로 텔레그램 봇에 입력

---

## 📱 텔레그램 명령어

| 명령어 | 설명 |
|--------|------|
| `/start` | 봇 시작 |
| `/menu` | 메뉴 표시 |
| `/status` | 시스템 상태 |
| `/positions` | 보유 종목 |
| `/balance` | 잔고 조회 |
| `/on` | 자동매매 시작 |
| `/off` | 자동매매 중지 |
| `/help` | 도움말 |
| `BUY 005930 삼성전자` | 수동 매수 |

---

## 🔧 고급 설정

### 보안 강화 (Secret Token)

#### config.json
```json
{
  "webhook": {
    "secret_token": "your-secret-token-here"
  }
}
```

#### 트레이딩뷰 메시지
```json
{
  "token": "your-secret-token-here",
  "action": "BUY",
  "ticker": "{{ticker}}"
}
```

---

## 📊 매매 로직

### 진입
- **신호**: 트레이딩뷰 알림 (`BUY 005930`)
- **주문**: 설정 금액(기본 100만원) 시장가 매수

### 1차 익절 (3%)
- **조건**: 수익률 >= 3%
- **실행**: 보유 수량의 50% 매도
- **남은 포지션**: 트레일링 스톱 활성화

### 트레일링 스톱
- **시작**: 익절 후 고점 추적
- **조건**: 고점 대비 -2% 하락
- **실행**: 잔여 수량 전량 매도

### 손절 (-2.5%)
- **조건**: 손실률 <= -2.5%
- **실행**: 전량 매도

---

## 🐛 문제 해결

### 1. Webhook이 수신되지 않음

**원인**:
- ngrok/cloudflared 실행 안 됨
- Webhook URL 오타
- 방화벽 차단

**해결**:
```bash
# ngrok 확인
ps aux | grep ngrok

# 로그 확인
tail -f logs/trading_*.log

# 테스트
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"action":"BUY","ticker":"005930"}'
```

### 2. 인증 오류

**원인**:
- KIS API 키 문제
- 토큰 만료

**해결**:
```bash
# kis_devlp.yaml 확인
cat kis_devlp.yaml

# 토큰 삭제 후 재발급
rm -rf ~/KIS/config/KIS*
python tradingview_bot.py
```

### 3. 매수 실패

**원인**:
- 잔고 부족
- 시장 개장 시간 아님
- 종목 코드 오류

**해결**:
```bash
# 로그 확인
grep "매수" logs/trading_*.log

# 잔고 확인
# 텔레그램 봇에서: /balance
```

---

## 📚 참고 자료

- **트레이딩뷰 Webhook**: https://www.tradingview.com/support/solutions/43000529348
- **ngrok**: https://ngrok.com/docs
- **Cloudflare Tunnel**: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps
- **텔레그램 봇**: https://core.telegram.org/bots

---

## 🎯 요약

### Webhook 모드 (완전 자동화)

1. `python tradingview_bot.py` 실행
2. `ngrok http 8080` 실행
3. 트레이딩뷰에 Webhook URL 설정
4. ✅ 완전 자동 매매!

### 수동 모드 (텔레그램)

1. `config.json`에서 `webhook.enabled: false`
2. `python tradingview_bot.py` 실행
3. 텔레그램으로 `BUY 005930 삼성전자` 입력

---

**이제 트레이딩뷰 알림이 자동으로 매수됩니다!** 🚀
