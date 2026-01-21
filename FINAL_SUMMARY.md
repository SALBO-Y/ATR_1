# 🎯 트레이딩뷰 자동매매 시스템 - 최종 요약

**작성일**: 2026-01-21  
**버전**: 2.0 (완전 자동화)  
**GitHub**: https://github.com/SALBO-Y/ATR_1/tree/genspark

---

## ✅ 완료된 작업

### Phase 1: 알림 연동 (완료)
✅ 트레이딩뷰 → 텔레그램 직접 연결  
✅ Webhook URL 생성 방법  
✅ URL 인코딩 가이드  
✅ 테스트 방법  

**문서**: `TRADINGVIEW_TELEGRAM_DIRECT.md`

### Phase 2: 자동매매 시스템 (완료)
✅ Flask Webhook 서버 구현  
✅ 한국투자증권 API 연동  
✅ 자동 매수/익절/손절 로직  
✅ 트레일링 스톱 구현  
✅ 포지션 관리 시스템  
✅ 텔레그램 봇 통합  
✅ ngrok 고정 도메인 지원  
✅ 자동 재시작 설정 (Windows/Linux)  

**문서**: `COMPLETE_SETUP_GUIDE.md`

---

## 📂 파일 구조

```
webapp/
├── tradingview_bot.py           # 메인 자동매매 봇
├── realtime_modules.py          # 실시간 모듈 (참고용)
├── advanced_scalping_realtime.py # 고급 스캘핑 (참고용)
├── config.json.example          # 설정 예시
├── kis_devlp.yaml               # KIS API 설정
├── requirements_new.txt         # 패키지 목록
├── positions.json               # 포지션 저장 (자동 생성)
│
├── logs/                        # 로그 디렉토리 (자동 생성)
│   └── trading_YYYYMMDD.log
│
└── docs/
    ├── TRADINGVIEW_TELEGRAM_DIRECT.md   # Phase 1 가이드
    ├── COMPLETE_SETUP_GUIDE.md          # Phase 2 가이드
    ├── TRADINGVIEW_WEBHOOK_GUIDE.md     # 기술 가이드
    ├── TRADINGVIEW_BOT_GUIDE_V2.md      # 사용자 가이드
    ├── API_VERIFICATION_REPORT.md       # API 검증 보고서
    └── CONFIG_SIMPLIFICATION.md         # 설정 단순화
```

---

## 🚀 빠른 시작 (3단계)

### 1️⃣ Phase 1: 알림만 받기 (5분)

```
1. 텔레그램 봇 생성 (@BotFather)
2. Bot Token, Chat ID 확보
3. 트레이딩뷰 Webhook URL 설정:
   https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<CHAT_ID>&text=BUY%20{{ticker}}
4. ✅ 완료! 알림 수신
```

**문서**: `TRADINGVIEW_TELEGRAM_DIRECT.md`

---

### 2️⃣ Phase 2: 자동매매 (30분)

**준비물**:
- PC 24시간 실행 환경
- ngrok 유료 플랜 (고정 도메인)
- 한국투자증권 API 키

**실행 순서**:

```bash
# 1. 패키지 설치
pip install -r requirements_new.txt

# 2. 설정 파일 수정
# config.json - 텔레그램 토큰, Chat ID
# kis_devlp.yaml - KIS API 키

# 3. 서버 시작
python tradingview_bot.py

# 4. ngrok 시작 (별도 터미널)
ngrok http 8080 --domain=your-trading-bot.ngrok.app

# 5. 트레이딩뷰 Webhook 설정
# URL: https://your-trading-bot.ngrok.app/webhook
# 메시지: {"action":"BUY","ticker":"{{ticker}}"}

# 6. ✅ 완료! 자동매매 시작
```

**문서**: `COMPLETE_SETUP_GUIDE.md`

---

## 📊 시스템 기능

### 1. 진입 전략
- **신호**: 트레이딩뷰 알림 (Webhook)
- **실행**: 설정 금액 시장가 매수 (기본 100만원)
- **확인**: 중복 진입 방지, 최대 보유 종목 관리

### 2. 익절 전략
- **1차 익절**: 수익률 >= 3% → 보유 수량의 50% 매도
- **트레일링**: 고점 대비 -2% 하락 시 잔여 매도

### 3. 손절 전략
- **하드 스톱**: 손실률 <= -2.5% → 전량 매도

### 4. 포지션 관리
- **실시간 모니터링**: 5초 간격 가격 체크
- **자동 매도**: 익절/손절 조건 충족 시 자동 실행
- **상태 추적**: `positions.json` 파일에 저장

### 5. 알림 시스템
- **텔레그램 알림**: 매수/익절/손절 실시간 알림
- **로그 기록**: `logs/trading_YYYYMMDD.log`

---

## 🎮 텔레그램 명령어

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `/start` | 봇 시작 | - |
| `/menu` | 메뉴 표시 | - |
| `/status` | 시스템 상태 | 자동매매: ON, 보유 종목: 2개 |
| `/positions` | 보유 종목 조회 | [005930] 삼성전자, +3.2% |
| `/balance` | 잔고 조회 | 예수금: 5,000,000원 |
| `/on` | 자동매매 시작 | - |
| `/off` | 자동매매 중지 | - |
| `/help` | 도움말 | - |
| `BUY 005930` | 수동 매수 (수동 모드) | - |

---

## ⚙️ 설정 파일

### config.json

```json
{
  "telegram": {
    "bot_token": "123456789:ABC...",
    "chat_id": "987654321"
  },
  "kis": {
    "server": "vps"  // vps: 모의, prod: 실전
  },
  "trading": {
    "enabled": true,
    "buy_amount": 1000000,      // 매수 금액
    "profit_target": 0.03,       // 익절 목표 (3%)
    "trailing_stop": 0.02,       // 트레일링 (-2%)
    "stop_loss": 0.025,          // 손절 (-2.5%)
    "check_interval": 5          // 모니터링 간격 (초)
  },
  "webhook": {
    "enabled": true,
    "port": 8080,
    "secret_token": ""           // 보안 토큰 (선택)
  }
}
```

### kis_devlp.yaml

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

---

## 🔄 자동 재시작 설정

### Windows: Task Scheduler

**start_bot.bat**:
```batch
@echo off
cd C:\Users\YourName\webapp
python tradingview_bot.py
```

**start_ngrok.bat**:
```batch
@echo off
ngrok http 8080 --domain=your-trading-bot.ngrok.app
```

**작업 스케줄러**에 등록:
- 트리거: `컴퓨터를 시작할 때`
- 동작: `.bat` 파일 실행

---

### Linux/Mac: systemd

**trading-bot.service**:
```ini
[Unit]
Description=TradingView Bot
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/home/user/webapp
ExecStart=/usr/bin/python3 tradingview_bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable trading-bot
sudo systemctl start trading-bot
```

---

## 📈 실전 사용 예시

### 시나리오: 삼성전자 골든크로스

**1. 트레이딩뷰 설정**:
```
조건: EMA(50) crosses over EMA(200)
Webhook URL: https://your-trading-bot.ngrok.app/webhook
메시지: {"action":"BUY","ticker":"{{ticker}}"}
```

**2. 알림 발생**:
```
[2024-01-21 09:30:00] EMA 골든크로스 발생
```

**3. 자동 매수**:
```
🚀 매수 체결 (Webhook)

종목: [005930] 삼성전자
가격: 75,000원
수량: 13주
금액: 975,000원
```

**4. 실시간 모니터링**:
```
[09:30:05] 현재가: 75,100원 (+0.13%)
[09:30:10] 현재가: 75,300원 (+0.40%)
[09:30:15] 현재가: 76,500원 (+2.00%)
[09:30:20] 현재가: 77,300원 (+3.07%) ← 1차 익절 조건 충족
```

**5. 1차 익절 (50%)**:
```
💰 익절 (1차)

종목: 삼성전자
매도 수량: 6주
수익: +2,310원 (+3.07%)
남은 수량: 7주 (트레일링 활성화)
```

**6. 트레일링 스톱**:
```
[09:30:25] 현재가: 78,000원 (+4.00%) ← 고점 갱신
[09:30:30] 현재가: 78,500원 (+4.67%) ← 고점 갱신
[09:30:35] 현재가: 76,950원 (+2.60%) ← 고점 대비 -2% 도달
```

**7. 최종 매도**:
```
🎯 익절 (트레일링)

종목: 삼성전자
매도 수량: 7주
최종 수익: +3,465원 (+3.55%)
총 수익: +5,775원 (+3.94%)
```

---

## 🐛 문제 해결

### 1. Webhook 수신 안 됨

**증상**: 트레이딩뷰 알림 발생했지만 매수 안 됨

**원인 & 해결**:
```bash
# Python 서버 실행 중?
ps aux | grep python
→ 없으면: python tradingview_bot.py

# ngrok 실행 중?
ps aux | grep ngrok
→ 없으면: ngrok http 8080

# 로그 확인
tail -f logs/trading_*.log
```

### 2. 인증 오류

**증상**: `401 Unauthorized`

**해결**:
```bash
# 토큰 삭제
rm -rf ~/KIS/config/KIS*

# kis_devlp.yaml 확인
cat kis_devlp.yaml

# 재시작
python tradingview_bot.py
```

### 3. 매수 실패

**증상**: 알림은 오지만 매수 안 됨

**원인**:
- 잔고 부족
- 시장 폐장
- 종목 코드 오류

**해결**:
```bash
# 잔고 확인 (텔레그램)
/balance

# 로그 확인
grep "매수" logs/trading_*.log

# API 테스트
python test_kis_api.py
```

---

## 📚 문서 가이드

### 초보자 추천 순서

1. **`TRADINGVIEW_TELEGRAM_DIRECT.md`**  
   → Phase 1: 알림만 받기 (5분)

2. **`COMPLETE_SETUP_GUIDE.md`**  
   → Phase 2: 자동매매 설정 (30분)

3. **`TRADINGVIEW_BOT_GUIDE_V2.md`**  
   → 사용자 가이드 (명령어, 설정)

### 고급 사용자

4. **`TRADINGVIEW_WEBHOOK_GUIDE.md`**  
   → Webhook 기술 문서

5. **`API_VERIFICATION_REPORT.md`**  
   → API 연동 검증 보고서

---

## 🎯 체크리스트

### Phase 1: 알림 (5분)
- [ ] 텔레그램 봇 생성
- [ ] Bot Token 확보
- [ ] Chat ID 확보
- [ ] 트레이딩뷰 Webhook URL 설정
- [ ] 알림 수신 테스트

### Phase 2: 자동매매 (30분)
- [ ] Python 3.9+ 설치
- [ ] 패키지 설치 (`requirements_new.txt`)
- [ ] `config.json` 설정
- [ ] `kis_devlp.yaml` 확인
- [ ] 로컬 서버 테스트
- [ ] ngrok 설치 및 인증
- [ ] ngrok 실행 (고정 도메인)
- [ ] 트레이딩뷰 Webhook 설정
- [ ] 실전 테스트 (매수/익절)
- [ ] 자동 재시작 설정
- [ ] 모니터링 설정

---

## 🚀 최종 실행 명령

### 서버 시작
```bash
cd /home/user/webapp
python tradingview_bot.py
```

### ngrok 시작 (별도 터미널)
```bash
ngrok http 8080 --domain=your-trading-bot.ngrok.app
```

### 트레이딩뷰 설정
```
Webhook URL: https://your-trading-bot.ngrok.app/webhook
메시지: {"action":"BUY","ticker":"{{ticker}}"}
```

---

## 💰 예상 성과

**설정**:
- 매수 금액: 100만원
- 익절 목표: 3%
- 승률: 60%

**월 예상 수익** (월 20회 거래):
```
성공: 12회 × +3% × 100만원 = +36만원
실패: 8회 × -2.5% × 100만원 = -20만원
순수익: +16만원 (월 1.6%)
연 수익: 약 20%
```

**주의**: 실제 성과는 전략과 시장 상황에 따라 다름

---

## ⚠️ 주의사항

1. **모의투자로 테스트**: 실전 전 반드시 모의투자로 1주일 이상 테스트
2. **리스크 관리**: 종목당 자본의 2% 이하 배분
3. **시장 상황**: 변동성 큰 시기에는 자동매매 중지
4. **모니터링**: 매일 텔레그램 알림 확인
5. **손실 한도**: 일일 -5% 도달 시 자동 중단

---

## 📞 지원

- **GitHub**: https://github.com/SALBO-Y/ATR_1/tree/genspark
- **문서**: `/home/user/webapp/*.md`
- **로그**: `/home/user/webapp/logs/`

---

**이제 완전 자동 매매 시스템이 준비되었습니다!** 🚀💰

**Phase 1로 알림을 받고, Phase 2로 자동매매를 시작하세요!**

**행운을 빕니다!** 🍀
