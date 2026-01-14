# 설정 파일 사용 가이드

## 🤔 자주 묻는 질문

### Q1: trading_config.yaml이 있는데 .env가 왜 필요한가요?

**답변: 선택사항이지만, 보안을 위해 분리하는 것이 좋습니다.**

#### 현재 시스템 구조

```
설정 우선순위:
1. ~/KIS/config/kis_devlp.yaml (한투 기본 설정) ← 현재 사용 중
2. trading_config.yaml (매매 전략 설정)
3. .env (선택사항, 보안 강화)
```

#### 각 파일의 역할

| 파일 | 용도 | Git 포함 | 필수 여부 |
|------|------|---------|----------|
| `~/KIS/config/kis_devlp.yaml` | 한투 API 인증 정보 | ❌ 절대 금지 | ✅ 필수 |
| `trading_config.yaml` | 매매 전략 설정 | ✅ 가능 (민감정보 제외) | ✅ 필수 |
| `.env` | 민감 정보 통합 관리 | ❌ 절대 금지 | ⚪ 선택 |

#### 사용 방법 1: 최소 설정 (기본)

```yaml
# ~/KIS/config/kis_devlp.yaml만 사용
my_app: YOUR_APP_KEY
my_sec: YOUR_APP_SECRET
my_acct_stock: "12345678"

# trading_config.yaml
max_stocks: 5
buy_amount: 100000
```

**장점:**
- ✅ 간단함
- ✅ 한투 표준 구조

**단점:**
- ❌ API 키가 YAML에 노출
- ❌ 환경별 분리 어려움

#### 사용 방법 2: 보안 강화 (권장)

```bash
# .env (민감 정보만)
KIS_REAL_APP_KEY=PSxxxxxx
KIS_REAL_APP_SECRET=yyyyyy
KIS_REAL_ACCOUNT=12345678
TELEGRAM_BOT_TOKEN=1234567890:ABC...
```

```yaml
# trading_config.yaml (전략만)
max_stocks: 5
buy_amount: 100000
target_profit_rate: 2.0
```

**장점:**
- ✅ API 키 완전 분리
- ✅ .gitignore로 자동 보호
- ✅ 환경별 .env 파일 분리 가능

**단점:**
- ❌ 파일이 하나 더 늘어남

### Q2: 코스피/코스닥 모두 검색하는데 MARKET_DIV가 필요한가요?

**답변: 조건검색에는 불필요하지만, 현재가 조회 시 필요합니다.**

#### 문제 상황

```python
# ❌ 잘못된 접근
MARKET_DIV = "J"  # 모든 종목을 코스피로 간주

# 조건검색 결과
# - 005930 (삼성전자, 코스피) ← OK
# - 035720 (카카오, 코스닥) ← 문제! 코스닥인데 J로 조회
```

#### 해결 방법 1: 종목코드로 자동 판단

```python
def get_market_div_from_code(stock_code: str) -> str:
    """
    종목코드로 시장 구분 판단

    일반 규칙:
    - 코스피: 6자리 숫자 (005930, 000660)
    - 코스닥: A로 시작 또는 특정 패턴

    하지만 100% 정확하지 않음!
    """
    # 간단한 판단 (부정확)
    if stock_code.startswith('A'):
        return 'Q'
    return 'J'
```

**문제:** 정확하지 않음! (코스닥도 숫자 코드 있음)

#### 해결 방법 2: 종목 마스터 파일 사용 (권장)

```python
def load_stock_master():
    """
    한투 제공 종목 마스터 다운로드
    https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info
    """
    # kospi_code.xlsx
    # kosdaq_code.xlsx
    pass

def get_market_div_from_master(stock_code: str) -> str:
    """마스터 파일에서 정확한 시장 구분 조회"""
    # 마스터 파일 검색
    if stock_code in kospi_codes:
        return 'J'
    elif stock_code in kosdaq_codes:
        return 'Q'
    else:
        return 'J'  # 기본값
```

#### 해결 방법 3: API 응답에서 추출

조건검색 API 응답을 확인하면 시장 구분 정보가 포함되어 있을 수 있습니다:

```python
# psearch_result API 응답 예시
{
    "output2": [
        {
            "pdno": "005930",
            "prdt_name": "삼성전자",
            "std_pdno": "...",  # 여기에 시장 정보 있을 수 있음
        }
    ]
}
```

### 결론

#### 1. 설정 파일 사용 방법

**Option A: 현재 방식 유지 (가장 간단)**
```yaml
# ~/KIS/config/kis_devlp.yaml
# + trading_config.yaml
# = .env 없이 사용 가능
```

**Option B: 보안 강화 (권장)**
```bash
# .env 파일 생성
# + trading_config.yaml
# = 민감 정보 완전 분리
```

#### 2. MARKET_DIV 설정

**현재 문제:**
- ❌ 모든 종목을 하나의 시장으로 간주
- ❌ 코스닥 종목 조회 실패 가능

**해결 필요:**
- ✅ 종목 마스터 파일 사용
- ✅ 또는 종목별 시장 구분 자동 판단
- ✅ 또는 API 응답에서 추출

## 권장 사항

### 즉시 적용 가능한 방법

1. **설정 파일**: 현재 방식 유지 (kis_devlp.yaml + trading_config.yaml)
   - .env는 선택사항

2. **MARKET_DIV**: 코드 개선 필요
   - 종목별로 자동 판단하도록 수정

### 코드 개선 예시

```python
# test_condition_monitor.py 개선
def get_stock_price(self, stock_code: str) -> Dict:
    """종목 현재가 조회 (시장 자동 판단)"""

    # 여러 시장에서 시도
    for market_div in ['J', 'Q']:  # 코스피, 코스닥 순서로 시도
        params = {
            "FID_COND_MRKT_DIV_CODE": market_div,
            "FID_INPUT_ISCD": stock_code
        }

        res = ka._url_fetch(...)

        if res.isOK():
            return {...}  # 성공하면 반환

    # 둘 다 실패하면 None
    return None
```

이렇게 하면 코스피/코스닥 구분 없이 자동으로 처리됩니다!
