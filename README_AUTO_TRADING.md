# 한국투자증권 자동트레이딩 시스템

한국투자증권 OpenAPI를 활용한 자동매매 시스템입니다.

## 주요 기능

1. **조건검색식 기반 종목 필터링**
   - HTS에 저장된 조건검색식을 실행하여 매수 대상 종목 자동 선정
   - 주기적으로 조건검색 재실행하여 신규 종목 발굴

2. **실시간 체결통보 (WebSocket)**
   - 주문 접수 및 체결 실시간 모니터링
   - 체결 즉시 텔레그램 알림 발송

3. **자동 매수/매도**
   - 조건검색 결과 종목 자동 매수
   - 목표수익률/손절률 도달 시 자동 매도
   - 최대 보유 종목 수 제한 관리

4. **텔레그램 봇 연동**
   - 매수/매도 체결 알림
   - 실시간 잔고 및 손익 현황 알림
   - 시스템 시작/종료 알림

5. **잔고/손익 실시간 모니터링**
   - 주기적 잔고 조회
   - 보유 종목별 수익률 계산
   - 매도 조건 자동 체크

6. **에러 처리 및 로깅**
   - API 에러 자동 처리 (토큰 만료, 거래건수 초과 등)
   - 모든 거래 내역 로그 파일 저장
   - 거래 가능 시간 체크

## 시스템 구조

```
auto_trading_system.py
├── AuthManager              # 인증 관리
├── ConditionSearchManager   # 조건검색 관리
├── OrderManager            # 주문 관리
├── BalanceManager          # 잔고 관리
├── ExecutionNoticeManager  # 체결통보 관리 (WebSocket)
├── TelegramNotifier        # 텔레그램 알림
├── ErrorHandler            # 에러 처리
└── AutoTradingSystem       # 메인 시스템
```

## 설치 방법

### 1. 필수 패키지 설치

```bash
pip install pandas requests websockets pyyaml pycryptodome
```

### 2. 텔레그램 봇 설치 (선택사항)

```bash
pip install python-telegram-bot
```

### 3. 한국투자증권 OpenAPI 설정

`~/KIS/config/kis_devlp.yaml` 파일을 다음과 같이 설정:

```yaml
# 실전투자 앱키/앱시크리트
my_app: "YOUR_APP_KEY"
my_sec: "YOUR_APP_SECRET"

# 모의투자 앱키/앱시크리트
paper_app: "YOUR_PAPER_APP_KEY"
paper_sec: "YOUR_PAPER_APP_SECRET"

# 계좌번호
my_acct_stock: "12345678"  # 실전 주식계좌 (8자리)
my_paper_stock: "12345678"  # 모의 주식계좌 (8자리)

# 계좌상품코드
my_prod: "01"  # 01: 주식투자

# HTS ID
my_htsid: "YOUR_HTS_ID"

# User Agent
my_agent: "MyTradingBot/1.0"

# 도메인
prod: "https://openapi.koreainvestment.com:9443"  # 실전투자
vps: "https://openapivts.koreainvestment.com:29443"  # 모의투자

# WebSocket 도메인
ops: "ws://ops.koreainvestment.com:21000"  # 실전투자
vops: "ws://ops.koreainvestment.com:31000"  # 모의투자
```

## 사용 방법

### 1. HTS에서 조건검색식 등록

1. 한국투자증권 HTS (efriend Plus) 실행
2. [0110] 조건검색 화면 이동
3. 원하는 조건식 등록 (예: 거래량 급증, 상한가 근접 등)
4. **"사용자조건 서버저장"** 버튼 클릭 (중요!)

### 2. 설정 파일 수정

`trading_config.yaml` 파일을 수정:

```yaml
# 환경 설정
env_mode: "demo"  # "real": 실전투자, "demo": 모의투자

# 매매 전략
max_stocks: 5  # 최대 보유 종목 수
buy_amount: 100000  # 종목당 매수 금액 (원)
target_profit_rate: 2.0  # 목표 수익률 (2%)
stop_loss_rate: -1.5  # 손절률 (-1.5%)

# 텔레그램 설정 (선택사항)
telegram_enabled: true
telegram_bot_token: "YOUR_BOT_TOKEN"
telegram_chat_id: "YOUR_CHAT_ID"
```

### 3. 실행

```bash
python auto_trading_system.py
```

## 텔레그램 봇 설정 방법

### 1. 봇 생성

1. 텔레그램에서 `@BotFather` 검색
2. `/newbot` 명령 입력
3. 봇 이름 및 사용자명 설정
4. 발급받은 **봇 토큰** 복사

### 2. 채팅 ID 확인

1. 텔레그램에서 `@userinfobot` 검색
2. 봇과 대화 시작
3. **채팅 ID** 확인

### 3. 설정 파일에 입력

```yaml
telegram_enabled: true
telegram_bot_token: "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
telegram_chat_id: "123456789"
```

## 주문구분 코드

### 매수/매도 주문구분

- `00`: 지정가
- `01`: 시장가
- `02`: 조건부지정가
- `03`: 최유리지정가
- `04`: 최우선지정가
- `05`: 장전시간외
- `06`: 장후시간외
- `07`: 시간외단일가
- `08`: 자기주식
- `09`: 자기주식S-Option
- `10`: 자기주식금전신탁
- `11`: IOC지정가 (즉시체결,잔량취소)
- `12`: FOK지정가 (즉시체결,전량취소)
- `13`: IOC시장가 (즉시체결,잔량취소)
- `14`: FOK시장가 (즉시체결,전량취소)
- `15`: IOC최유리 (즉시체결,잔량취소)
- `16`: FOK최유리 (즉시체결,전량취소)

## 시스템 운영 프로세스

```
[시스템 시작]
    ↓
[인증] → Access Token 발급 + WebSocket 접속키 발급
    ↓
[조건검색식 목록 조회]
    ↓
┌─────────────────────────────────┐
│     메인 루프 (거래시간 체크)      │
├─────────────────────────────────┤
│ 1. 조건검색 실행 (60초마다)        │
│    - 매수 대상 종목 조회          │
│    - 최대 보유 종목 수 체크       │
│    - 자동 매수 실행              │
│                                 │
│ 2. 잔고 조회 (30초마다)           │
│    - 보유 종목 수익률 계산        │
│    - 목표수익률/손절률 체크       │
│    - 조건 도달 시 자동 매도       │
│                                 │
│ 3. 체결통보 수신 (WebSocket)      │
│    - 실시간 체결 알림            │
│    - 텔레그램 알림 발송          │
└─────────────────────────────────┘
    ↓
[시스템 종료] → 텔레그램 종료 알림
```

## 로그 파일

모든 거래 내역은 다음 파일에 저장됩니다:

```
auto_trading_YYYYMMDD.log
```

로그 내용:
- 시스템 시작/종료 시간
- 인증 성공/실패
- 조건검색 결과
- 매수/매도 주문 내역
- 체결 통보
- 잔고 현황
- 에러 메시지

## 주의사항

### 1. 토큰 발급 제한

- Access Token 유효기간: **1일**
- 6시간 경과 후 갱신 권장
- **5분당 1회 이상 토큰 발급 시 제한** (EGW00201 오류)

### 2. API 호출 제한

- 초당 거래건수 제한 존재
- 연속 호출 시 0.1~0.5초 대기 권장
- 에러 발생 시 자동 재시도 로직 포함

### 3. 조건검색 제한

- 조건당 **최대 100건**까지만 조회 가능
- WebSocket 실시간 구독 불가 (REST만 지원)

### 4. 실시간 체결통보

- **계좌 단위**로만 구독 가능
- 전체 종목 실시간 시세 구독 제한

### 5. 거래 시간

- 장 시작: 09:00
- 장 마감: 15:30
- 장 외 시간에는 자동으로 대기 모드

### 6. 모의투자 vs 실전투자

- 모의투자로 충분히 테스트 후 실전투자 전환 권장
- TR ID가 다름: `TTTC*` (실전) vs `VTTC*` (모의)

## 에러 코드 및 해결방법

### EGW00201: 초당 거래건수 초과

```
해결: 0.5초 대기 후 재시도
```

### EGW00123: Access Token 만료

```
해결: 토큰 자동 재발급
```

### MCA05918: 종목코드 오류

```
원인: 조건검색 결과 0건
해결: 조건검색식 확인 및 수정
```

## 개발 참고 문서

- [한국투자증권 OpenAPI GitHub](https://github.com/koreainvestment/open-trading-api)
- [API 개발가이드](https://apiportal.koreainvestment.com/intro)
- [종목코드 마스터 다운로드](https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info)

## 라이선스

이 프로젝트는 개인 사용 목적으로 제작되었습니다.

## 면책 조항

본 프로그램은 교육 및 참고 목적으로 제공됩니다.
실제 매매에 사용 시 발생하는 손실에 대해서는 사용자 본인이 책임을 집니다.
충분한 테스트 후 신중하게 사용하시기 바랍니다.

## 문의 및 지원

문제 발생 시 로그 파일을 확인하거나, 한국투자증권 OpenAPI 고객센터에 문의하시기 바랍니다.

---

**제작일**: 2026-01-12
**버전**: 1.0.0
**기반**: 한국투자증권 OpenAPI v1
