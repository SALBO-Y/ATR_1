# 트레이딩뷰 자동매매 시스템 - 완전 가이드

**작성일**: 2026-01-21  
**대상**: PC 24시간 실행 + ngrok 유료 플랜 사용자

---

## 🎯 시스템 구조

```
┌─────────────────┐
│  트레이딩뷰      │
│  알림 발생      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────┐
│  방법 1:        │      │  방법 2:     │
│  직접 연결      │──────│  자동매매    │
│  (알림만)       │      │  (완전자동)  │
└────────┬────────┘      └──────┬───────┘
         │                      │
         ▼                      ▼
┌─────────────────┐      ┌──────────────┐
│  텔레그램       │      │  Python      │
│  알림 수신      │      │  Flask 서버  │
└─────────────────┘      └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │  KIS API     │
                         │  자동 매수   │
                         └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │  실시간      │
                         │  모니터링    │
                         │  (익절/손절) │
                         └──────────────┘
```

---

## 📋 전체 설정 순서

### Phase 1: 알림 연동 (방법 1)
✅ **완료** - `TRADINGVIEW_TELEGRAM_DIRECT.md` 참고

### Phase 2: 자동매매 서버 (방법 2)
👇 **지금 진행**

---

## 🚀 Phase 2: 자동매매 서버 설정

### 1단계: 환경 준비

#### 1.1. 필수 소프트웨어 설치

**Python 3.9+ 확인**:
```bash
python --version
# Python 3.9.x 이상
```

**패키지 설치**:
```bash
cd /home/user/webapp
pip install -r requirements_new.txt

# 또는 개별 설치:
pip install python-telegram-bot flask pyyaml pycryptodome requests websockets
```

**설치 확인**:
```bash
python -c "import flask; import telegram; print('✅ 패키지 설치 완료')"
```

---

### 2단계: 설정 파일

#### 2.1. config.json 설정

**파일 위치**: `/home/user/webapp/config.json`

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

**주요 설정 설명**:
- `telegram.bot_token`: 텔레그램 봇 토큰 (Phase 1에서 생성)
- `telegram.chat_id`: 본인의 Chat ID (Phase 1에서 확인)
- `kis.server`: `vps` (모의투자) 또는 `prod` (실전투자)
- `trading.buy_amount`: 매수 금액 (원)
- `webhook.port`: 서버 포트 (기본 8080)
- `webhook.secret_token`: 보안 토큰 (선택사항)

#### 2.2. kis_devlp.yaml 확인

**파일 위치**: `/home/user/webapp/kis_devlp.yaml`

```yaml
# 실전투자
my_app: 실전_앱키
my_sec: 실전_앱시크릿
my_acct_stock: 12345678
my_prod: "01"

# 모의투자
paper_app: 모의_앱키
paper_sec: 모의_앱시크릿
my_paper_stock: 87654321

# 도메인
prod: https://openapi.koreainvestment.com:9443
vps: https://openapivts.koreainvestment.com:29443
```

**중요**: `config.json`에서 `kis.server`를 설정하면 자동으로 계좌 선택:
- `server: "vps"` → `my_paper_stock` 사용
- `server: "prod"` → `my_acct_stock` 사용

---

### 3단계: 서버 실행

#### 3.1. 로컬 테스트

```bash
cd /home/user/webapp
python tradingview_bot.py
```

**예상 출력**:
```
================================================================================
트레이딩뷰 연동 자동매매 시스템
================================================================================
✅ TradingSystem 초기화 완료
🌐 Webhook 서버 초기화 완료
🌐 Webhook 서버 시작: http://0.0.0.0:8080/webhook
💡 헬스 체크: http://0.0.0.0:8080/health
📱 텔레그램 봇 시작...
🚀 포지션 모니터링 시작
✅ 시스템 준비 완료!
 * Running on http://0.0.0.0:8080
```

#### 3.2. 헬스 체크

**새 터미널에서**:
```bash
curl http://localhost:8080/health
```

**예상 결과**:
```json
{
  "status": "ok",
  "service": "TradingView Bot Webhook",
  "enabled": true,
  "positions": 0
}
```

#### 3.3. Webhook 테스트

```bash
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"action":"BUY","ticker":"005930","price":"75000"}'
```

**예상 결과**:
```json
{
  "status": "success",
  "message": "Buy signal received for 005930",
  "data": {
    "code": "005930",
    "name": "삼성전자",
    "price": 75000,
    "quantity": 13
  }
}
```

---

### 4단계: ngrok 설정 (유료 플랜)

#### 4.1. ngrok 설치

**Windows**:
```powershell
choco install ngrok
```

**Mac**:
```bash
brew install ngrok
```

**Linux**:
```bash
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
tar -xvf ngrok-v3-stable-linux-amd64.tgz
sudo mv ngrok /usr/local/bin/
```

#### 4.2. ngrok 인증

**계정 생성**: https://dashboard.ngrok.com/signup

**인증 토큰 설정**:
```bash
ngrok config add-authtoken <YOUR_AUTHTOKEN>
```

#### 4.3. ngrok 실행 (유료 플랜 - 고정 도메인)

**일반 모드** (무료, 재시작 시 URL 변경):
```bash
ngrok http 8080
```

**고정 도메인** (유료):
```bash
ngrok http 8080 --domain=your-trading-bot.ngrok.app
```

**예상 출력**:
```
ngrok

Session Status                online
Account                       Your Name (Plan: Pro)
Version                       3.x.x
Region                        Korea (kr)
Latency                       10ms
Web Interface                 http://127.0.0.1:4040
Forwarding                    https://your-trading-bot.ngrok.app -> http://localhost:8080

Connections                   ttl     opn     rt1     rt5     p50     p90
                              0       0       0.00    0.00    0.00    0.00
```

**Webhook URL 확인**:
```
https://your-trading-bot.ngrok.app/webhook
```

---

### 5단계: 트레이딩뷰 설정

#### 5.1. 알림 생성

1. **트레이딩뷰** 접속: https://tradingview.com
2. **종목 차트** 열기 (예: KOSPI:005930)
3. **알림 아이콘** 클릭
4. **조건 설정**:
   - 예: `EMA(50) crosses over EMA(200)`
   - 예: `RSI(14) < 30`

#### 5.2. Webhook URL 설정

**Webhook URL** 입력:
```
https://your-trading-bot.ngrok.app/webhook
```

**메시지** 입력:
```json
{
  "action": "BUY",
  "ticker": "{{ticker}}",
  "price": "{{close}}",
  "time": "{{time}}"
}
```

**알림 이름**: "삼성전자 골든크로스"

**저장**

---

### 6단계: 실전 테스트

#### 6.1. 트레이딩뷰에서 알림 발생 대기

또는 **강제 테스트**:

```bash
# ngrok URL로 테스트
curl -X POST https://your-trading-bot.ngrok.app/webhook \
  -H "Content-Type: application/json" \
  -d '{"action":"BUY","ticker":"005930"}'
```

#### 6.2. 텔레그램 알림 확인

**예상 메시지**:
```
🚀 매수 체결 (Webhook)

종목: [005930] 삼성전자
가격: 75,000원
수량: 13주
금액: 975,000원
```

#### 6.3. 포지션 확인

**텔레그램 봇에서**:
```
/positions
```

**예상 결과**:
```
📊 보유 종목 (1)

[005930] 삼성전자
  매수가: 75,000원
  현재가: 75,500원
  수익률: +0.67%
  수량: 13주
  상태: active
```

---

## 🔄 자동 재시작 설정

### Windows: Task Scheduler

#### 1. Python 서버 자동 시작

**start_trading_bot.bat** 생성:
```batch
@echo off
cd C:\Users\YourName\webapp
python tradingview_bot.py
```

**작업 스케줄러**:
1. `작업 스케줄러` 열기
2. `기본 작업 만들기`
3. 트리거: `컴퓨터를 시작할 때`
4. 동작: `start_trading_bot.bat` 실행
5. 완료

#### 2. ngrok 자동 시작

**start_ngrok.bat** 생성:
```batch
@echo off
ngrok http 8080 --domain=your-trading-bot.ngrok.app
```

**작업 스케줄러**에 등록

---

### Linux/Mac: systemd

#### 1. 서비스 파일 생성

**`/etc/systemd/system/trading-bot.service`**:
```ini
[Unit]
Description=TradingView Automated Trading Bot
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/home/user/webapp
ExecStart=/usr/bin/python3 /home/user/webapp/tradingview_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 2. 서비스 등록
```bash
sudo systemctl daemon-reload
sudo systemctl enable trading-bot
sudo systemctl start trading-bot
sudo systemctl status trading-bot
```

#### 3. ngrok 서비스

**`/etc/systemd/system/ngrok.service`**:
```ini
[Unit]
Description=ngrok
After=network.target

[Service]
Type=simple
User=youruser
ExecStart=/usr/local/bin/ngrok http 8080 --domain=your-trading-bot.ngrok.app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable ngrok
sudo systemctl start ngrok
```

---

## 📊 모니터링

### 1. 로그 확인

```bash
# 실시간 로그
tail -f logs/trading_*.log

# 오늘 로그
cat logs/trading_$(date +%Y%m%d).log

# 매수 로그만
grep "매수" logs/trading_*.log

# 익절 로그만
grep "익절" logs/trading_*.log
```

### 2. ngrok 웹 인터페이스

브라우저에서: http://localhost:4040

**실시간 확인**:
- Webhook 요청 내역
- 응답 시간
- 에러 로그

### 3. 텔레그램 봇 명령어

| 명령어 | 설명 |
|--------|------|
| `/status` | 시스템 상태 |
| `/positions` | 보유 종목 |
| `/balance` | 잔고 조회 |
| `/on` | 자동매매 시작 |
| `/off` | 자동매매 중지 |
| `/perf` | 성과 조회 |

---

## 🐛 문제 해결

### 1. Webhook 수신 안 됨

**확인 사항**:
```bash
# Python 서버 실행 중?
ps aux | grep python

# ngrok 실행 중?
ps aux | grep ngrok

# 포트 사용 중?
lsof -i :8080

# 로그 확인
tail -f logs/trading_*.log
```

### 2. 매수 실패

**원인**:
- 잔고 부족
- 시장 폐장
- API 키 오류

**해결**:
```bash
# 잔고 확인 (텔레그램)
/balance

# API 테스트
python test_kis_api.py

# 로그 확인
grep "ERROR" logs/trading_*.log
```

### 3. ngrok 연결 끊김

**유료 플랜 장점**:
- ✅ 고정 도메인
- ✅ 무제한 연결
- ✅ 안정성

**재시작**:
```bash
pkill ngrok
ngrok http 8080 --domain=your-trading-bot.ngrok.app
```

---

## 📋 체크리스트

### Phase 1: 알림 연동
- [ ] 텔레그램 봇 생성
- [ ] Bot Token, Chat ID 확보
- [ ] 트레이딩뷰 직접 연결 테스트
- [ ] 알림 수신 확인

### Phase 2: 자동매매
- [ ] Python 패키지 설치
- [ ] config.json 설정
- [ ] kis_devlp.yaml 확인
- [ ] 로컬 서버 실행 테스트
- [ ] ngrok 설치 및 인증
- [ ] ngrok 실행 (고정 도메인)
- [ ] 트레이딩뷰 Webhook 설정
- [ ] 실전 테스트 (매수/익절/손절)
- [ ] 자동 재시작 설정
- [ ] 모니터링 설정

---

## 🎯 최종 요약

### 실행 순서

**1단계: 서버 시작**
```bash
cd /home/user/webapp
python tradingview_bot.py
```

**2단계: ngrok 시작**
```bash
ngrok http 8080 --domain=your-trading-bot.ngrok.app
```

**3단계: 트레이딩뷰 설정**
```
Webhook URL: https://your-trading-bot.ngrok.app/webhook
메시지: {"action":"BUY","ticker":"{{ticker}}"}
```

**4단계: 자동매매 시작!** 🚀

---

## 📚 관련 문서

- **Phase 1 가이드**: `TRADINGVIEW_TELEGRAM_DIRECT.md`
- **Webhook 가이드**: `TRADINGVIEW_WEBHOOK_GUIDE.md`
- **설정 가이드**: `TRADINGVIEW_BOT_GUIDE_V2.md`
- **API 검증**: `API_VERIFICATION_REPORT.md`

---

**이제 완전 자동 매매 시스템이 가동됩니다!** 💰🚀

**PC는 24시간 켜두고, ngrok 유료 플랜으로 안정적인 운영을 하세요!**
