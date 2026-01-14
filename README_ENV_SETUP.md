# 환경 변수 설정 가이드

한국투자증권 자동트레이딩 시스템의 환경 변수 설정 방법을 안내합니다.

## 📋 목차

1. [환경 변수란?](#환경-변수란)
2. [.env 파일 설정 방법](#env-파일-설정-방법)
3. [필수 환경 변수](#필수-환경-변수)
4. [선택 환경 변수](#선택-환경-변수)
5. [보안 주의사항](#보안-주의사항)
6. [문제 해결](#문제-해결)

## 환경 변수란?

**환경 변수(Environment Variables)**는 시스템 설정 정보를 저장하는 방법입니다.

### 왜 사용하나요?

1. **보안**: API 키, 계좌번호 등 민감 정보를 코드에서 분리
2. **편의성**: 설정 변경 시 코드 수정 불필요
3. **안전성**: Git에 민감 정보가 올라가는 것을 방지

### 현재 시스템의 설정 우선순위

```
1순위: .env 파일 (권장)
2순위: ~/KIS/config/kis_devlp.yaml
3순위: 코드 내 기본값
```

## .env 파일 설정 방법

### 1단계: .env.example 파일 복사

```bash
cp .env.example .env
```

### 2단계: .env 파일 편집

```bash
nano .env
# 또는
vim .env
# 또는 좋아하는 에디터로 열기
```

### 3단계: 실제 정보 입력

아래 필수 정보들을 입력합니다.

## 필수 환경 변수

### 1. 한국투자증권 API 설정

#### 앱키/앱시크리트 발급 방법

1. https://apiportal.koreainvestment.com/ 접속
2. 로그인 → API 신청
3. 실전투자/모의투자 각각 신청
4. 발급받은 앱키와 앱시크리트 복사

#### .env 파일에 입력

```bash
# 실전투자
KIS_REAL_APP_KEY=PSxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
KIS_REAL_APP_SECRET=yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy

# 모의투자
KIS_PAPER_APP_KEY=PSxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
KIS_PAPER_APP_SECRET=yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
```

### 2. 계좌 정보

```bash
# 실전투자 계좌번호 (8자리)
KIS_REAL_ACCOUNT=12345678

# 모의투자 계좌번호 (8자리)
KIS_PAPER_ACCOUNT=50000000

# 계좌상품코드 (보통 01)
KIS_ACCOUNT_PRODUCT=01
```

**계좌번호 확인 방법:**
- efriend Plus 로그인
- 상단 계좌 정보에서 확인
- 형식: `12345678-01` → 앞 8자리가 계좌번호, 뒤 2자리가 상품코드

### 3. HTS ID

```bash
# efriend Plus 로그인 ID
KIS_HTS_ID=your_id
```

### 4. 환경 모드 설정

```bash
# demo: 모의투자, real: 실전투자
ENV_MODE=demo
```

**⚠️ 주의**: 처음에는 반드시 `demo`로 테스트하세요!

## 선택 환경 변수

### 1. 텔레그램 봇 설정

#### 봇 토큰 발급

1. 텔레그램에서 `@BotFather` 검색
2. `/newbot` 명령 입력
3. 봇 이름 설정
4. 발급받은 토큰 복사

#### 채팅 ID 확인

1. 텔레그램에서 `@userinfobot` 검색
2. 봇과 대화 시작
3. 표시되는 ID 복사

#### .env 파일에 입력

```bash
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
TELEGRAM_ENABLED=true
```

### 2. 매매 전략 설정

```bash
# 최대 보유 종목 수
MAX_STOCKS=5

# 종목당 매수 금액 (원)
BUY_AMOUNT=100000

# 목표 수익률 (%)
TARGET_PROFIT_RATE=2.0

# 손절률 (%)
STOP_LOSS_RATE=-1.5
```

### 3. 시스템 운영 주기

```bash
# 잔고 조회 주기 (초)
BALANCE_CHECK_INTERVAL=30

# 조건검색 재실행 주기 (초)
CONDITION_CHECK_INTERVAL=60
```

## 환경 변수 적용 방법

### 방법 1: python-dotenv 사용 (권장)

**설치:**

```bash
pip install python-dotenv
```

**코드 예시:**

```python
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 환경 변수 읽기
app_key = os.getenv('KIS_REAL_APP_KEY')
app_secret = os.getenv('KIS_REAL_APP_SECRET')
```

### 방법 2: 시스템 환경 변수로 설정

**Linux/Mac:**

```bash
export KIS_REAL_APP_KEY="your_key"
export KIS_REAL_APP_SECRET="your_secret"
```

**Windows:**

```cmd
set KIS_REAL_APP_KEY=your_key
set KIS_REAL_APP_SECRET=your_secret
```

## 설정 파일 통합 가이드

### 현재 시스템의 설정 파일들

```
1. .env                      ← 환경 변수 (민감 정보)
2. trading_config.yaml       ← 매매 전략 설정
3. ~/KIS/config/kis_devlp.yaml ← 한투 API 설정 (기존)
```

### 권장 설정 방법

**Step 1: .env 파일 생성 (필수 정보)**

```bash
# API 키, 계좌번호 등 민감 정보
KIS_REAL_APP_KEY=...
KIS_REAL_APP_SECRET=...
TELEGRAM_BOT_TOKEN=...
```

**Step 2: trading_config.yaml (전략 설정)**

```yaml
# 매매 전략
max_stocks: 5
buy_amount: 100000
target_profit_rate: 2.0
```

**Step 3: 코드에서 통합 사용**

```python
# 환경 변수 우선, 없으면 config 파일 사용
app_key = os.getenv('KIS_REAL_APP_KEY') or config.get('my_app')
```

## 보안 주의사항

### ⚠️ 반드시 지켜야 할 사항

1. **.env 파일을 Git에 커밋하지 말 것**
   ```bash
   # .gitignore에 추가
   .env
   *.env
   .env.*
   !.env.example
   ```

2. **API 키와 시크릿은 절대 외부 노출 금지**
   - GitHub, GitLab 등 공개 저장소에 업로드 금지
   - 스크린샷 공유 시 주의
   - 로그 파일에 기록되지 않도록 주의

3. **텔레그램 봇 토큰 보안**
   - 봇 토큰도 민감 정보
   - 노출 시 봇이 악용될 수 있음

4. **계좌번호 보호**
   - 개인정보이므로 외부 노출 금지

### .gitignore 설정

```gitignore
# 환경 변수 파일
.env
.env.local
.env.*.local
*.env

# 설정 파일 (민감 정보 포함)
~/KIS/config/kis_devlp.yaml

# 로그 파일
*.log
auto_trading_*.log
condition_monitor_*.log

# 파이썬 캐시
__pycache__/
*.pyc
*.pyo
```

## 문제 해결

### 1. .env 파일이 인식되지 않음

**증상:**
```
환경 변수를 읽을 수 없습니다.
```

**해결:**
```bash
# python-dotenv 설치 확인
pip install python-dotenv

# .env 파일 위치 확인 (프로젝트 루트에 있어야 함)
ls -la .env

# 권한 확인
chmod 600 .env
```

### 2. API 키가 유효하지 않음

**증상:**
```
인증 실패 - 토큰 발급 실패
```

**해결:**
1. API 포털에서 앱키/시크릿 재확인
2. 실전/모의 구분 확인
3. 앞뒤 공백 제거 확인
4. 특수문자 이스케이프 확인

### 3. 계좌번호 오류

**증상:**
```
계좌번호가 올바르지 않습니다.
```

**해결:**
1. 8자리 숫자만 입력 (하이픈 제거)
2. 실전/모의 계좌 구분 확인
3. 계좌상품코드 확인 (보통 01)

### 4. 텔레그램 봇 작동 안 함

**증상:**
```
텔레그램 메시지 전송 실패
```

**해결:**
1. 봇 토큰 재확인
2. 채팅 ID 재확인
3. `TELEGRAM_ENABLED=true` 확인
4. 봇과 대화 먼저 시작했는지 확인

## 완성된 .env 파일 예시

```bash
# ============================================================================
# 한국투자증권 자동트레이딩 시스템 환경 변수
# ============================================================================

# 1. API 설정
KIS_REAL_APP_KEY=PSxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
KIS_REAL_APP_SECRET=yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
KIS_PAPER_APP_KEY=PSaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
KIS_PAPER_APP_SECRET=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb

# 2. 계좌 정보
KIS_REAL_ACCOUNT=12345678
KIS_PAPER_ACCOUNT=50000000
KIS_ACCOUNT_PRODUCT=01
KIS_HTS_ID=myid123

# 3. 텔레그램
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
TELEGRAM_ENABLED=true

# 4. 시스템 설정
ENV_MODE=demo
MAX_STOCKS=5
BUY_AMOUNT=100000
TARGET_PROFIT_RATE=2.0
STOP_LOSS_RATE=-1.5

# 5. 운영 주기
BALANCE_CHECK_INTERVAL=30
CONDITION_CHECK_INTERVAL=60
```

## 다음 단계

1. ✅ .env 파일 생성 및 설정 완료
2. ✅ .gitignore에 .env 추가 확인
3. ✅ 테스트 실행
   ```bash
   python test_condition_monitor.py
   ```
4. ✅ 모의투자로 충분히 테스트
5. ✅ 실전투자 전환 (신중히!)

## 추가 리소스

- [한국투자증권 OpenAPI 가이드](https://apiportal.koreainvestment.com/)
- [python-dotenv 문서](https://pypi.org/project/python-dotenv/)
- [환경 변수 보안 가이드](https://12factor.net/config)

---

**제작일**: 2026-01-14
**버전**: 1.0.0
**관련 파일**: `.env.example`
