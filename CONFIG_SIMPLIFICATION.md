# ✅ config.json 단순화 완료

**변경일**: 2026-01-19  
**커밋**: c37e29c

---

## 🎯 변경 사항

### Before (중복 설정)
```json
{
  "telegram": {...},
  "kis": {
    "server": "vps",
    "account": "12345678",  ← 중복!
    "product": "01"         ← 중복!
  },
  "trading": {...}
}
```

### After (단순화)
```json
{
  "telegram": {...},
  "kis": {
    "server": "vps"  ← server만 지정
  },
  "trading": {...}
}
```

---

## 💡 작동 방식

### kis_devlp.yaml에서 자동 읽기
```python
class KISOrder:
    def __init__(self, auth, yaml_cfg, config):
        # server 설정에 따라 자동 선택
        if auth.server == "prod":
            self.account = yaml_cfg["my_acct_stock"]    # 실전 계좌
        else:
            self.account = yaml_cfg["my_paper_stock"]   # 모의 계좌
        
        self.product = yaml_cfg["my_prod"]              # 상품 코드
```

---

## ✅ 장점

| 항목 | Before | After |
|------|--------|-------|
| **설정 파일** | 2개 모두 수정 필요 | kis_devlp.yaml만 수정 |
| **중복** | 계좌번호 2곳에 존재 | 1곳에만 존재 |
| **오류 가능성** | 높음 (불일치 가능) | 낮음 |
| **관리 편의성** | 불편 | 편리 |

---

## 📋 사용자 입장 변화

### 기존 방식 (복잡)
1. kis_devlp.yaml 수정
2. config.json도 수정 (같은 정보)
3. 두 파일이 일치하는지 확인

### 새 방식 (간단)
1. kis_devlp.yaml만 수정
2. config.json에서 server만 선택 (vps/prod)
3. 끝!

---

## 🔧 설정 예시

### kis_devlp.yaml (기존)
```yaml
# 실전투자
my_app: "앱키"
my_sec: "앱시크릿"
my_acct_stock: "12345678"  ← 실전 계좌

# 모의투자
paper_app: "모의앱키"
paper_sec: "모의시크릿"
my_paper_stock: "87654321"  ← 모의 계좌

# 상품코드
my_prod: "01"
```

### config.json (단순화)
```json
{
  "telegram": {
    "bot_token": "YOUR_TOKEN",
    "chat_id": "YOUR_CHAT_ID"
  },
  "kis": {
    "server": "vps"  ← 이것만 설정!
  },
  "trading": {
    "enabled": false,
    "buy_amount": 1000000
  }
}
```

---

## 🚀 실행 예시

### 모의투자로 테스트
```json
// config.json
"kis": {
  "server": "vps"
}
```
→ 자동으로 `my_paper_stock` (87654321) 사용

### 실전투자로 전환
```json
// config.json
"kis": {
  "server": "prod"
}
```
→ 자동으로 `my_acct_stock` (12345678) 사용

**kis_devlp.yaml은 수정 불필요!**

---

## 📌 요약

✅ **config.json 더 간단해짐**  
✅ **kis_devlp.yaml이 유일한 진실의 원천**  
✅ **중복 제거로 오류 가능성 감소**  
✅ **사용자 편의성 증가**

---

**GitHub**: https://github.com/SALBO-Y/ATR_1/tree/genspark  
**커밋**: c37e29c - Simplify config.json
