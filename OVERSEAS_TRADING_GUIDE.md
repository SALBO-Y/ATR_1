# 🌍 국내주식 + 해외주식 통합 자동매매 시스템

**작성일**: 2026-01-21  
**버전**: 3.0 (국내+해외 통합)

---

## 🎯 주요 업그레이드

### 1. 국내주식 + 해외주식 지원
- ✅ 국내주식 (KOSPI, KOSDAQ)
- ✅ 해외주식 (NASDAQ, NYSE, AMEX, 홍콩, 상해, 심천, 동경)

### 2. 텔레그램 메뉴 구분
- 🇰🇷 국내주식 메뉴
  - 자동매매 시작/중지
  - 보유 종목 조회
  - 잔고 조회
- 🌎 해외주식 메뉴
  - 자동매매 시작/중지
  - 보유 종목 조회
  - 잔고 조회 (USD)

### 3. 독립적인 설정
- 국내/해외 각각 독립적으로 활성화
- 매수 금액 개별 설정 (국내: 원화, 해외: USD)
- 익절/손절 목표 개별 설정 가능

---

## 📂 파일 구조

### 핵심 코드
```
tradingview_bot.py
├── KISAuth                    # 인증 (공통)
├── KISMarket                  # 국내주식 시세
├── KISOrder                   # 국내주식 주문
├── KISOverseasMarket          # 해외주식 시세 (신규)
├── KISOverseasOrder           # 해외주식 주문 (신규)
├── PositionManager            # 포지션 관리 (업그레이드)
├── TelegramBot                # 텔레그램 봇 (업그레이드)
├── WebhookServer              # Webhook 서버
└── TradingSystem              # 메인 시스템 (업그레이드)
```

---

## ⚙️ 설정 파일

### config.json (업그레이드)

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
      "enabled": false,
      "buy_amount": 1000000,
      "profit_target": 0.03,
      "trailing_stop": 0.02,
      "stop_loss": 0.025,
      "check_interval": 5
    },
    "overseas": {
      "enabled": false,
      "buy_amount": 1000,
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

---

## 🚀 사용 방법

### 1. 트레이딩뷰 Webhook 메시지

#### 국내주식 (KOSPI, KOSDAQ)
```json
{
  "action": "BUY",
  "market": "domestic",
  "ticker": "005930",
  "exchange": "KOSPI"
}
```

#### 해외주식 (미국)
```json
{
  "action": "BUY",
  "market": "overseas",
  "ticker": "AAPL",
  "exchange": "NASDAQ"
}
```

#### 해외주식 (홍콩)
```json
{
  "action": "BUY",
  "market": "overseas",
  "ticker": "0700",
  "exchange": "홍콩"
}
```

---

### 2. 텔레그램 봇 메뉴

#### 메인 메뉴
```
🤖 트레이딩뷰 자동매매 봇

국내주식 + 해외주식 자동매매

📱 아래 버튼을 선택하세요:

[📊 시스템 상태]
[🇰🇷 국내주식] [🌎 해외주식]
[💰 전체 잔고]
[❓ 도움말]
```

#### 국내주식 메뉴
```
🇰🇷 국내주식 메뉴

[✅ 자동매매 시작] [⏸️ 자동매매 중지]
[📊 보유 종목]
[💰 잔고 조회]
[◀️ 메인 메뉴]
```

#### 해외주식 메뉴
```
🌎 해외주식 메뉴

[✅ 자동매매 시작] [⏸️ 자동매매 중지]
[📊 보유 종목 (USD)]
[💰 잔고 조회 (USD)]
[◀️ 메인 메뉴]
```

---

## 📊 지원 거래소

### 해외 거래소 코드

| 거래소 | 코드 (트레이딩뷰) | API 코드 | 예시 |
|--------|-------------------|----------|------|
| 나스닥 | NASDAQ | NASD | AAPL |
| 뉴욕 | NYSE | NYSE | TSLA |
| 아멕스 | AMEX | AMEX | - |
| 홍콩 | 홍콩 | SEHK | 0700 |
| 상해 | 상해 | SHAA | - |
| 심천 | 심천 | SZAA | - |
| 동경 | 동경 | TKSE | - |
| 호치민 | 호치민 | HOSE | - |
| 하노이 | 하노이 | HNSE | - |

---

## 🎮 API 매핑

### 국내주식 API
- **현재가**: `FHKST01010100`
- **매수**: `TTTC0802U` (실전), `VTTC0802U` (모의)
- **매도**: `TTTC0801U` (실전), `VTTC0801U` (모의)
- **잔고**: `TTTC8434R` (실전), `VTTC8434R` (모의)

### 해외주식 API
- **현재가**: `HHDFS00000300`
- **매수**: `TTTT1002U` (실전), `VTTT1002U` (모의)
- **매도**: `TTTT1006U` (실전), `VTTT1006U` (모의)
- **잔고**: `TTTS3012R` (실전), `VTTS3012R` (모의)

---

## 🧪 테스트 방법

### 1. 국내주식 테스트

```bash
# Webhook 테스트
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "action": "BUY",
    "market": "domestic",
    "ticker": "005930",
    "exchange": "KOSPI"
  }'
```

### 2. 해외주식 테스트

```bash
# Webhook 테스트 (AAPL)
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "action": "BUY",
    "market": "overseas",
    "ticker": "AAPL",
    "exchange": "NASDAQ"
  }'
```

---

## 📈 실전 사용 예시

### 시나리오 1: 국내 + 해외 동시 운용

**설정**:
```json
{
  "trading": {
    "domestic": {
      "enabled": true,
      "buy_amount": 1000000
    },
    "overseas": {
      "enabled": true,
      "buy_amount": 500
    }
  }
}
```

**트레이딩뷰 알림**:
1. 삼성전자 골든크로스 → 국내 매수 (100만원)
2. 애플 RSI 과매도 → 해외 매수 ($500)

**포지션**:
```
국내주식:
- [005930] 삼성전자: 13주 @ 75,000원

해외주식:
- [AAPL] Apple: 3주 @ $185
```

---

### 시나리오 2: 국내만 운용

**설정**:
```json
{
  "trading": {
    "domestic": {
      "enabled": true
    },
    "overseas": {
      "enabled": false
    }
  }
}
```

**결과**: 해외주식 알림은 무시됨

---

## 🔄 업그레이드 체크리스트

### Phase 1: 코드 업데이트
- [x] `KISOverseasMarket` 클래스 추가
- [x] `KISOverseasOrder` 클래스 추가
- [x] `PositionManager.market_type` 추가
- [x] `config.json` 구조 변경
- [ ] 텔레그램 콜백 핸들러 완성
- [ ] `TradingSystem` 통합
- [ ] `WebhookServer` 시장 타입 처리

### Phase 2: 테스트
- [ ] 국내주식 매수/매도
- [ ] 해외주식 매수/매도
- [ ] 잔고 조회 (국내/해외)
- [ ] 포지션 관리 (국내/해외)
- [ ] 텔레그램 메뉴

### Phase 3: 문서화
- [ ] API 가이드
- [ ] 트레이딩뷰 설정 가이드
- [ ] 거래소 코드 매핑표

---

## ⚠️ 주의사항

### 1. 해외주식 거래 시간
- **미국**: 한국 시간 23:30 ~ 06:00 (서머타임: 22:30 ~ 05:00)
- **홍콩**: 한국 시간 10:30 ~ 17:00
- **동경**: 한국 시간 09:00 ~ 15:00

### 2. 환율 고려
- 해외주식은 USD 기준
- 원화 → USD 환전 수수료 확인
- 환율 변동 리스크

### 3. 세금
- 국내주식: 매도 차익 없음 (양도소득세 없음, 단 대주주 제외)
- 해외주식: 양도소득세 22% (연 250만원 공제)

---

## 🎯 다음 단계

### 즉시 진행
1. **config.json 업데이트**
   ```bash
   # 기존 config.json 백업
   cp config.json config.json.backup
   
   # 새 구조로 업데이트
   # trading.enabled → trading.domestic.enabled, trading.overseas.enabled
   ```

2. **서버 재시작**
   ```bash
   python tradingview_bot.py
   ```

3. **텔레그램 테스트**
   - /start 실행
   - 국내/해외 메뉴 확인

### 추가 구현 필요
- [ ] 텔레그램 콜백 핸들러 완성
- [ ] WebhookServer market_type 처리
- [ ] TradingSystem 국내/해외 분리
- [ ] 모니터링 스레드 분리

---

## 📚 관련 문서

- **`tradingview_bot.py`** - 메인 코드 (부분 업데이트 완료)
- **`config.json.example`** - 설정 예시 (업데이트 필요)
- **`OVERSEAS_TRADING_GUIDE.md`** - 이 문서
- **`API_REFERENCE.md`** - API 참조 (작성 예정)

---

## 🚧 현재 상태

### 완료
- ✅ 해외주식 클래스 추가 (`KISOverseasMarket`, `KISOverseasOrder`)
- ✅ PositionManager market_type 지원
- ✅ config.json 구조 설계
- ✅ 거래소 코드 매핑

### 진행 중
- 🔄 텔레그램 봇 메뉴 업데이트
- 🔄 WebhookServer market_type 처리
- 🔄 TradingSystem 통합

### 예정
- 📋 완전한 테스트
- 📋 문서화 완성

---

**현재 코드는 부분 업데이트 상태입니다. 완전한 기능을 위해서는 추가 구현이 필요합니다.**

**귀하의 선택**:
1. **현재 코드로 테스트** - 국내주식만 작동 (해외는 API만 추가됨)
2. **완전 구현 요청** - 텔레그램 메뉴 + Webhook + 시스템 통합

**어떻게 진행하시겠어요?** 🤔
