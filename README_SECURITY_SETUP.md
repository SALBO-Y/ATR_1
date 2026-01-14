# 보안 설정 가이드

## ⚠️ 중요: Git 보안 설정 완료

이 문서는 설정 파일의 보안 문제를 해결하고, 민감 정보가 Git에 노출되지 않도록 하는 방법을 안내합니다.

## 변경 사항 요약

### 1. 파일 구조 변경

**변경 전 (위험):**
```
kis_devlp.yaml          ← Git 추적됨 (민감 정보 입력 시 위험!)
trading_config.yaml     ← Git 추적됨 (민감 정보 입력 시 위험!)
```

**변경 후 (안전):**
```
kis_devlp.yaml.example      ← Git 추적 (템플릿, 안전)
trading_config.yaml.example ← Git 추적 (템플릿, 안전)
kis_devlp.yaml              ← Git 무시 (실제 설정, 안전)
trading_config.yaml         ← Git 무시 (실제 설정, 안전)
.env                        ← Git 무시 (권장 사용 방식)
```

### 2. .gitignore 업데이트

다음 파일들이 Git에서 자동으로 무시됩니다:
```gitignore
kis_devlp.yaml          # 실제 설정 파일
trading_config.yaml     # 실제 설정 파일
.env                    # 환경 변수 파일
```

하지만 템플릿 파일은 추적됩니다:
```gitignore
!kis_devlp.yaml.example      # 템플릿은 공유 가능
!trading_config.yaml.example # 템플릿은 공유 가능
```

## 사용 방법

### 첫 설정 시

#### 방법 1: .env 사용 (권장)

**장점:**
- ✅ 가장 안전 (민감 정보 완전 분리)
- ✅ 표준 방식 (python-dotenv)
- ✅ 환경별 설정 용이 (.env.real, .env.demo 등)

**설정:**
```bash
# 1. .env.example을 복사
cp .env.example .env

# 2. .env 파일 편집
nano .env

# 3. 실제 정보 입력
KIS_REAL_APP_KEY=PS실제앱키여기입력...
KIS_REAL_APP_SECRET=실제시크릿여기입력...
KIS_REAL_ACCOUNT=12345678
TELEGRAM_BOT_TOKEN=1234567890:ABC...
TELEGRAM_CHAT_ID=123456789
```

**코드에서 사용:**
```python
import os
from dotenv import load_dotenv

load_dotenv()

app_key = os.getenv('KIS_REAL_APP_KEY')
app_secret = os.getenv('KIS_REAL_APP_SECRET')
```

#### 방법 2: kis_devlp.yaml + trading_config.yaml 사용

**장점:**
- ✅ 한투 공식 예제와 동일한 구조
- ✅ 별도 라이브러리 불필요

**설정:**
```bash
# 1. 템플릿 복사
cp kis_devlp.yaml.example kis_devlp.yaml
cp trading_config.yaml.example trading_config.yaml

# 2. kis_devlp.yaml 편집
nano kis_devlp.yaml

# 실제 정보 입력 (플레이스홀더 대체)
my_app: "PS실제앱키여기입력..."
my_sec: "실제시크릿여기입력..."
my_acct_stock: "12345678"

# 3. trading_config.yaml 편집
nano trading_config.yaml

# 텔레그램 설정 (필요시)
telegram_bot_token: "1234567890:ABC..."
telegram_chat_id: "123456789"
telegram_enabled: true
```

**⚠️ 주의사항:**
- kis_devlp.yaml과 trading_config.yaml은 .gitignore에 의해 보호됩니다
- 이 파일들은 절대 Git에 커밋되지 않습니다
- 실수로 `git add .`을 해도 무시됩니다

## Git 작업 시 확인 사항

### 커밋 전 항상 확인

```bash
# 1. 상태 확인
git status

# 2. 민감 파일이 포함되지 않았는지 확인
# 다음 파일들이 "Changes to be committed"에 없어야 함:
#   - kis_devlp.yaml
#   - trading_config.yaml
#   - .env

# 3. 안전하게 커밋
git add .
git commit -m "커밋 메시지"
```

### 실수로 민감 정보를 커밋했다면?

**아직 푸시 안 했을 때:**
```bash
# 마지막 커밋 취소
git reset --soft HEAD~1

# 또는 특정 파일만 제거
git reset HEAD kis_devlp.yaml
git restore --staged kis_devlp.yaml
```

**이미 푸시했을 때 (긴급):**
```bash
# 1. 즉시 API 키 재발급
#    https://apiportal.koreainvestment.com/

# 2. 텔레그램 봇 토큰 재발급
#    @BotFather에서 /revoke 명령

# 3. Git 히스토리에서 완전 제거 (고급)
#    주의: 협업 시 팀원과 조율 필요
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch kis_devlp.yaml" \
  --prune-empty --tag-name-filter cat -- --all

# 4. 강제 푸시
git push origin --force --all
```

## 보안 체크리스트

### ✅ 필수 확인 사항

- [ ] `.env` 파일이 .gitignore에 포함됨
- [ ] `kis_devlp.yaml` (실제)이 .gitignore에 포함됨
- [ ] `trading_config.yaml` (실제)이 .gitignore에 포함됨
- [ ] `git status`에서 민감 파일이 추적되지 않음
- [ ] `.example` 파일들은 플레이스홀더만 포함
- [ ] 실제 설정 파일에만 진짜 정보 입력

### ✅ 커밋 전 확인

```bash
# 이 명령어의 결과에 민감 파일이 없어야 함
git diff --cached --name-only | grep -E "(kis_devlp\.yaml|trading_config\.yaml|\.env)$"

# 출력이 없으면 안전, 있으면 위험!
```

### ✅ GitHub 공개 저장소 사용 시

- [ ] `.gitignore` 재확인
- [ ] GitHub Secrets 사용 고려 (CI/CD용)
- [ ] Private Repository로 변경 고려
- [ ] API 키에 IP 제한 설정 (한투 API 포털)

## 권장 설정 구조

### 개발 환경 (로컬)

```
프로젝트 루트/
├── .env                          # 실제 환경 변수 (Git 무시)
├── .env.example                  # 템플릿 (Git 추적)
├── kis_devlp.yaml               # 실제 한투 설정 (Git 무시)
├── kis_devlp.yaml.example       # 템플릿 (Git 추적)
├── trading_config.yaml          # 실제 매매 설정 (Git 무시)
├── trading_config.yaml.example  # 템플릿 (Git 추적)
└── .gitignore                   # 보안 설정
```

### 서버 배포 시

**방법 1: .env 파일 직접 생성**
```bash
# 서버에서
cd /path/to/project
cp .env.example .env
nano .env  # 실제 정보 입력
```

**방법 2: 환경 변수로 설정**
```bash
# /etc/environment 또는 ~/.bashrc에 추가
export KIS_REAL_APP_KEY="PS..."
export KIS_REAL_APP_SECRET="..."
```

**방법 3: Docker Secrets**
```yaml
# docker-compose.yml
services:
  trading:
    env_file:
      - .env.production
    secrets:
      - kis_app_key
      - kis_app_secret
```

## 문제 해결

### Q1: git status에서 kis_devlp.yaml이 보입니다

**원인:** .gitignore가 적용되지 않았거나, 이미 추적 중인 파일

**해결:**
```bash
# Git 캐시에서 제거
git rm --cached kis_devlp.yaml

# .gitignore 재확인
grep kis_devlp.yaml .gitignore
```

### Q2: 템플릿 파일을 실수로 수정했습니다

**해결:**
```bash
# 템플릿 복원
git checkout kis_devlp.yaml.example
git checkout trading_config.yaml.example

# 또는 원본에서 다시 복사
git show HEAD:kis_devlp.yaml.example > kis_devlp.yaml.example
```

### Q3: .env와 kis_devlp.yaml 중 어느 것을 사용해야 하나요?

**권장:** .env 사용 (표준 방식)

**kis_devlp.yaml 사용해도 되는 경우:**
- 한투 공식 예제를 그대로 따르고 싶을 때
- python-dotenv 설치를 원하지 않을 때
- 이미 kis_devlp.yaml 기반 코드가 많을 때

**하지만 둘 다 사용 가능:**
```python
# 우선순위: .env > kis_devlp.yaml
app_key = os.getenv('KIS_REAL_APP_KEY') or config.get('my_app')
```

## 추가 보안 팁

### 1. API 키 보안 강화

**한투 API 포털에서:**
- IP 주소 제한 설정
- 사용하지 않는 API는 권한 해제
- 정기적으로 키 재발급 (3-6개월마다)

### 2. 텔레그램 봇 보안

**BotFather 설정:**
```
/setprivacy - enable (그룹 메시지 읽기 방지)
/setjoingroups - disable (그룹 초대 차단)
```

**봇 토큰 관리:**
- 봇 토큰도 API 키만큼 중요
- 노출 시 즉시 /revoke로 재발급

### 3. 로그 파일 보안

```gitignore
# .gitignore에 추가됨
*.log
auto_trading_*.log
condition_monitor_*.log
```

**로그 파일 확인:**
```bash
# 민감 정보가 로그에 기록되지 않았는지 확인
grep -r "APP_KEY\|APP_SECRET\|bot_token" *.log
```

## 현재 상태 확인

```bash
# 보안 상태 확인 스크립트
echo "=== Git 추적 파일 확인 ==="
git ls-files | grep -E "(kis_devlp|trading_config|\.env)$"

echo -e "\n=== .gitignore 설정 확인 ==="
grep -E "(kis_devlp|trading_config|\.env)" .gitignore

echo -e "\n=== 로컬 설정 파일 존재 확인 ==="
ls -la kis_devlp.yaml trading_config.yaml .env 2>&1 | grep -v "No such file"

echo -e "\n=== Git 상태 확인 ==="
git status --short
```

**안전한 상태:**
```
=== Git 추적 파일 확인 ===
kis_devlp.yaml.example
trading_config.yaml.example

=== .gitignore 설정 확인 ===
kis_devlp.yaml
!kis_devlp.yaml.example
trading_config.yaml
!trading_config.yaml.example
.env

=== 로컬 설정 파일 존재 확인 ===
(파일 목록 표시)

=== Git 상태 확인 ===
(민감 파일이 없어야 함)
```

## 요약

### ✅ 이제 안전합니다

1. **kis_devlp.yaml과 trading_config.yaml은 .gitignore에 의해 보호됩니다**
2. **.example 템플릿만 Git에 추적됩니다**
3. **실제 설정 파일에 민감 정보를 입력해도 안전합니다**
4. **커밋 시 자동으로 무시됩니다**

### 🔒 안전한 작업 흐름

```bash
# 1. 템플릿에서 복사
cp .env.example .env

# 2. 실제 정보 입력
nano .env

# 3. 안전하게 커밋 (민감 파일은 자동 무시됨)
git add .
git commit -m "기능 추가"
git push
```

---

**제작일:** 2026-01-14
**관련 파일:** `.gitignore`, `.env.example`, `kis_devlp.yaml.example`, `trading_config.yaml.example`
