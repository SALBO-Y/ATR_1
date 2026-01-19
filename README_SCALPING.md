# 스캘핑 자동매매 봇 (Scalping Trading Bot)

## 📋 개요

한국투자증권 API를 활용한 **심플하고 실용적인** 스캘핑 자동매매 시스템입니다.

### 주요 특징
- ✅ **단일 파일** 구조 - 복잡하지 않고 심플함
- ✅ **텔레그램 봇** 연동 - 모바일에서 실시간 제어
- ✅ **국내주식 + 해외주식** 지원
- ✅ **골든크로스 + 거래량 급증** 전략
- ✅ **자동 익절/손절** 관리

## 🎯 매매 전략

### 진입 조건
1. **15분봉 MA50 > MA200** (골든크로스)
2. **5분봉 거래량 급증** (평균 대비 2.5배 이상)
3. **최대 3개 종목** 동시 보유

### 청산 조건
- ✅ **익절**: +3% 달성 시
- ❌ **손절**: -2.5% 도달 시
- ⏰ **시간 청산**: 2시간 이상 보유 + 수익 1% 이상

## 🚀 시작하기

### 1. 필수 패키지 설치

```bash
pip install -r requirements_new.txt
```

### 2. 설정 파일 (kis_devlp.yaml)

```yaml
# 실전투자
my_app: "실전 앱키"
my_sec: "실전 시크릿"

# 모의투자
paper_app: "모의 앱키"
paper_sec: "모의 시크릿"

# HTS ID
my_htsid: "HTS ID"

# 계좌번호
my_acct_stock: "증권계좌 8자리"
my_paper_stock: "모의계좌 8자리"

my_prod: "01"
```

### 3. 텔레그램 봇 생성

1. 텔레그램에서 `@BotFather` 검색
2. `/newbot` 명령어로 봇 생성
3. **봇 토큰** 받기
4. 봇과 대화 시작
5. `https://api.telegram.org/bot{토큰}/getUpdates` 접속해서 **chat_id** 확인

### 4. 실행

```bash
python scalping_bot.py
```

입력 프롬프트:
- 텔레그램 봇 토큰 입력
- 텔레그램 채팅 ID 입력

## 📱 텔레그램 명령어

- `/start` - 봇 시작
- `/menu` - 메인 메뉴 (버튼 인터페이스)
- `/status` - 현재 상태 조회

### 메뉴 버튼
- 💼 **잔고** - 현재 보유 종목 확인
- 📊 **포지션** - 진행 중인 포지션 확인
- 🟢 **국내주식** / 🔵 **해외주식** - 시장 전환
- ▶️ **시작** / ⏹ **중지** - 자동매매 시작/중지

## 📊 주요 기능

### 실시간 모니터링
- 5분봉/15분봉 데이터 추적
- 이동평균선 계산
- 거래량 분석

### 자동 주문
- 시장가 매수/매도
- 포지션 사이징
- 리스크 관리

### 텔레그램 알림
- 매수/매도 체결 알림
- 실시간 손익 확인
- 시스템 상태 모니터링

## ⚙️ 전략 파라미터 수정

`scalping_bot.py` 파일에서 다음 값을 수정하세요:

```python
# ScalpingSystem 클래스 __init__ 메서드
self.max_positions = 3         # 최대 동시 보유 종목
self.profit_rate = 0.03        # 익절 비율 (3%)
self.loss_rate = 0.025         # 손절 비율 (2.5%)
```

## 📁 파일 구조

```
webapp/
├── scalping_bot.py           # 메인 시스템 (단일 파일)
├── kis_devlp.yaml            # API 설정
├── requirements_new.txt      # 패키지 목록
├── logs/                     # 로그 파일
│   └── bot_YYYYMMDD.log
└── README_SCALPING.md        # 이 문서
```

## ⚠️ 주의사항

1. **모의투자로 먼저 테스트**하세요
2. **리스크는 본인 책임**입니다
3. **시장 상황에 따라 전략 조정** 필요
4. **과도한 레버리지 금지**
5. **손실 허용 범위 내에서만** 운영

## 🔧 트러블슈팅

### 토큰 오류
```python
# ~/KIS/config/KIS날짜 파일 삭제 후 재실행
rm ~/KIS/config/KIS*
```

### 텔레그램 연결 실패
```bash
# python-telegram-bot 재설치
pip install --upgrade python-telegram-bot
```

### 주문 실패
- kis_devlp.yaml 설정 확인
- 계좌번호/상품코드 확인
- 모의투자 계좌 사용 여부 확인

## 📈 향후 개선 계획

- [ ] 웹소켓 실시간 시세 연동
- [ ] 체결강도 분석 추가
- [ ] RSI, 볼린저밴드 등 추가 지표
- [ ] 백테스팅 기능
- [ ] 성과 분석 대시보드
- [ ] 다양한 전략 템플릿

## 📞 문의

- GitHub Issues: https://github.com/SALBO-Y/ATR_1/issues
- 한국투자증권 API: https://apiportal.koreainvestment.com/

## 📜 라이선스

이 코드는 참고용입니다. 실제 투자 손실에 대해 개발자는 책임지지 않습니다.
