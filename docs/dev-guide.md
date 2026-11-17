# 개발 가이드

Git 작업 순서를 단계별로 따라 하려면 [git-flow.md](git-flow.md)를 먼저 보세요.

## 1. 로컬 실행 환경

### 준비물
- Git, GNU Make
- [uv](https://docs.astral.sh/uv/) (권장) 또는 Python 3.11

### 설치

```bash
make setup
```

`scripts/setup-dev.sh`가 실행되어 다음을 준비합니다.

1. `.venv/` 가상환경 (Python 3.11)
2. `requirements.txt`, `requirements-dev.txt` 설치
3. `.env`가 없으면 `.env.example`을 복사해 생성

여러 번 실행해도 안전합니다. 의존성이 바뀐 브랜치로 옮겼다면 다시 `make setup`을 실행하세요.

### 자주 쓰는 명령

| 명령 | 하는 일 |
|---|---|
| `make check` | CI와 동일한 검사 (lint + compile + test). PR 올리기 전에 실행 |
| `make lint` | `ruff check .` |
| `make format` | ruff 자동 수정 + 포맷 |
| `make test` | `pytest -q` |
| `make clean` | `.venv`와 캐시 삭제 |

가상환경을 직접 쓰려면 `source .venv/bin/activate` 후 `python`, `pytest` 등을 실행합니다.

### make를 쓸 수 없는 경우 (예: Windows PowerShell)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env
.venv\Scripts\ruff check .
.venv\Scripts\python -m compileall -q app agent data pipeline eval
.venv\Scripts\pytest -q
```

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

PR과 `dev`/`main` push마다 `ci` 작업이 실행됩니다: `ruff check .` → `python -m compileall` → `pytest -q`.
CI는 실제 LLM이나 외부 API를 호출하지 않으며 시크릿을 사용하지 않습니다. 외부 호출이 필요한 테스트는 모킹하세요.
