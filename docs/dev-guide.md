# 개발 가이드

Git 작업 순서를 단계별로 따라 하려면 [git-flow.md](git-flow.md)를 먼저 보세요.

## 1. 로컬 실행 환경

### 준비물
- Git, GNU Make
- Docker, Docker Compose v2.24 이상
- [uv](https://docs.astral.sh/uv/) (Python 3.14는 uv가 자동으로 받습니다)
- Node.js 24

Windows에서는 `make`와 bash 스크립트를 쓰므로 **WSL2** 안에서 실행합니다.

### 설치

```bash
scripts/setup-dev.sh
```

다음을 준비합니다.

1. `apps/api/.venv/` 가상환경과 API 의존성 (`uv sync --locked`)
2. `apps/web/node_modules/` 웹 의존성 (`npm ci`)
3. `.env`가 없으면 `.env.example`을 복사해 생성

여러 번 실행해도 안전합니다. 의존성이 바뀐 브랜치로 옮겼다면 다시 실행하세요. `.env`가 이미 있으면 `make setup`만 실행해도 됩니다(1, 2번만 수행).

### 실행

```bash
./scripts/run-fake.sh       # API 키 없이 가짜 모델로 DB·API·웹 실행
./scripts/run-local.sh      # 실제 모델로 실행(.env.local 필요)
```

자세한 실행 방법과 주의할 점은 [README.md](../README.md)에 있습니다.

### 자주 쓰는 명령

| 명령 | 하는 일 |
|---|---|
| `make check` | CI와 동일한 검사 (lint + test). PR 올리기 전에 실행 |
| `make lint` | ruff 검사·포맷 검사(`apps/api`, `jobs`, `ml`, `scripts`) + 웹 eslint·prettier·tsc(`apps/web`) |
| `make fmt` | ruff 자동 수정 + 포맷, prettier 포맷 |
| `make test` | API 테스트(`apps/api/tests`). 가짜 모델로 실행하며 DB 컨테이너가 떠 있어야 함 |
| `make up PROVIDER=fake` | DB·API·웹 컨테이너 실행 |
| `make down` | 컨테이너 종료(데이터 볼륨 유지) |

`make test`는 `_test`로 끝나는 테스트 DB를 지우고 다시 만듭니다. `make help`로 전체 명령을 봅니다.

## 2. 브랜치

- 이름: `타입/짧은-설명` (예: `feat/etf-search`, `fix/price-parser`)
- 타입

| 타입 | 용도 |
|---|---|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `refactor` | 동작 변화 없는 구조 개선 |
| `docs` | 문서 |
| `chore` | 설정, 의존성 등 잡무 |
| `data` | 데이터 수집·가공 |
| `infra` | 배포·인프라 |
| `prompt` | 프롬프트 수정 |
| `eval` | 평가셋·평가 실행기 |
| `test` | 테스트만 추가·수정 |

- 기본 브랜치는 `dev`입니다. `dev`와 `main`은 직접 push, force push, 삭제가 막혀 있습니다.

## 3. 커밋

- 형식: `타입: 내용` (한글 가능)
- 예: `feat: ETF 종목 검색 추가`, `fix: 배당 수익률 계산 오류 수정`

## 4. 작업 흐름 (브랜치 → dev)

```bash
git switch dev && git pull
git switch -c feat/etf-search
# ... 작업, 커밋 ...
make check
git push -u origin feat/etf-search
gh pr create --base dev --fill
```

1. 모든 작업은 작업 브랜치에서 하고 `dev`로 PR을 올립니다.
2. CI(`ci`)가 통과하면 **작성자가 직접 squash 머지**합니다. 승인은 필수가 아니지만 리뷰를 권장합니다.
3. 머지된 작업 브랜치는 자동 삭제됩니다.
4. squash 머지 커밋의 제목은 PR 제목, 본문은 PR 본문이 됩니다. PR 제목도 `타입: 내용` 형식으로 적어 주세요.

### 승인이 필수인 PR

아래를 고치는 PR은 **팀원 1명의 승인**을 받은 뒤 머지합니다. 나머지 PR은 위 2번대로 CI 통과 후 작성자가 squash 머지합니다.

| 대상 | 이유 |
|---|---|
| 개인정보 차단(외부 API 호출 전) | 개인정보가 외부로 나가면 되돌릴 수 없음 |
| 가드(규칙 검사·검증 모델) | 검증을 통과한 답만 내보내는 안전장치 |
| 숫자 대조 | 답변 수치가 DB 근거와 맞는지 확인하는 장치 |
| 데이터 파이프라인(수집·검증·적재) | 모든 답변 수치의 원천 |

### 매일 dev 받기

작업 브랜치는 매일 `dev`를 받아 충돌을 미리 정리합니다.

```bash
git fetch origin
git merge origin/dev     # 충돌이 나면 해결 후 커밋
```

## 5. 릴리스 (dev → main)

- `dev` → `main` PR은 **selee1012만** 머지할 수 있고, **merge commit** 방식만 허용됩니다.
- `main`으로는 `dev`에서 온 PR만 허용됩니다. 다른 브랜치에서 올리면 CI가 "main으로는 dev에서만 PR 가능"으로 실패합니다.
- 릴리스마다 태그를 붙입니다: `v1.0`, `v1.1` …

```bash
gh pr create --base main --head dev --title "release: v1.0"
gh pr merge <PR번호> --merge          # selee1012만 가능
git fetch origin && git tag v1.0 origin/main && git push origin v1.0
```

## 6. API 키

- **API 키는 절대 커밋하지 않습니다.** `.env`는 `.gitignore`에 들어 있습니다.
- 키의 원본은 **Azure Key Vault**에서 관리하고, CI/배포용으로 GitHub Secrets에 복사해 둡니다.
- 로컬에서는 `.env.example`을 복사한 `.env`에 값을 채워 사용합니다 (`make setup`이 자동 생성).
- 이름 규칙: Key Vault는 하이픈(`LLM-API-KEY`), GitHub Secrets와 `.env`는 언더스코어(`LLM_API_KEY`).

| 키 | 용도 |
|---|---|
| `LLM_API_KEY` | LLM 호출 |
| `DATA_GO_KR_API_KEY` | 공공데이터포털 |
| `DART_API_KEY` | 전자공시(DART) |

### 키 등록·교체 (관리자)

```bash
KV_NAME=<Key Vault 이름> scripts/set-secret.sh DART_API_KEY
```

값은 화면에 보이지 않게 입력받아 Key Vault와 GitHub Secrets에 함께 저장합니다.

### 키를 실수로 커밋했다면

즉시 팀에 알리고 해당 키를 **폐기 후 재발급**합니다. 히스토리에서 지우는 것만으로는 안전하지 않습니다.

## 7. 의존성

- `requirements.txt`: 실행용. **버전을 반드시 고정**합니다 (`패키지==1.2.3`).
- `requirements-dev.txt`: 개발/CI용 (ruff, pytest).
- 패키지를 추가하거나 올릴 때는 PR에 이유를 적습니다.

## 8. CI

PR과 `dev`/`main` push마다 `ci` 작업이 실행됩니다. `make check`와 같은 검사입니다.

1. main 보호 가드: `main`으로는 `dev`에서 온 PR만 통과
2. API: Python 3.14 + uv로 `apps/api`에서 `uv sync --locked`
3. `ruff check`, `ruff format --check` (`apps/api`, `jobs`, `ml`, `scripts`. 설정은 `apps/api/pyproject.toml`)
4. `pytest` (`apps/api/tests`. pgvector 서비스 컨테이너를 DB로 쓰고 `LLM_PROVIDER=fake`, `EMBEDDING_PROVIDER=fake`로 실행)
5. 웹: Node 24로 `apps/web`에서 `npm ci` → `lint` → `format:check` → `typecheck`

CI는 실제 LLM이나 외부 API를 호출하지 않으며 시크릿을 사용하지 않습니다. 외부 호출이 필요한 테스트는 모킹하세요.
