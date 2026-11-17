# ETF-Agent
코멘토 명지대 AI 2조 작업 공간입니다.

ETF 관련 질문에 답하는 QA 에이전트를 만듭니다.

## 빠른 시작 (로컬 실행 환경)

```bash
git clone git@github.com:Mju-Cowork-AI/ETF-Agent.git
cd ETF-Agent
make setup      # .venv(Python 3.11) 생성 + 의존성 설치 + .env 준비
make check      # CI와 같은 검사 (ruff, compileall, pytest)
```

- `make setup`은 [uv](https://docs.astral.sh/uv/)가 있으면 Python 3.11을 자동으로 받아 쓰고, 없으면 설치된 Python 3.11을 사용합니다.
- 어느 브랜치에서든 `make check`가 통과하면 CI도 통과합니다.
- `make help`로 전체 명령을 볼 수 있습니다. 자세한 내용은 [docs/dev-guide.md](docs/dev-guide.md)를 보세요.

## 폴더 구조

| 폴더 | 용도 |
|---|---|
| `app/` | 서비스 진입점 (API/UI) |
| `agent/` | 에이전트 로직 |
| `agent/prompts/` | 프롬프트 |
| `data/` | 데이터 로더·스키마 (`data/raw/` 원본은 커밋 안 함) |
| `pipeline/` | 수집·전처리·인덱싱 파이프라인 |
| `eval/` | 평가 셋과 평가 스크립트 |
| `infra/` | 배포·인프라 설정 |
| `docs/` | 문서 |
| `tests/` | 테스트 |
| `scripts/` | 보조 스크립트 |

## 팀 규칙 요약

- **브랜치 이름:** `타입/짧은-설명` — 타입은 `feat`, `fix`, `refactor`, `docs`, `chore`, `data`, `infra`, `prompt`
- **커밋 메시지:** `타입: 내용` (한글 가능)
- **작업 흐름:** 모든 작업은 브랜치 → `dev` PR. CI가 통과하면 작성자가 직접 머지해도 됩니다. 리뷰가 필요하면 보류하고 담당자에게 전달해 주세요.
- **충돌 관리:** 작업 브랜치는 매일 `dev`를 받아 충돌을 정리합니다.
- **릴리스:** `dev` → `main`은 Cloud Engineer만 가능하게 설정했습니다. (권한 필요하면 말씀해주세요)
- **API 키:** 커밋 금지. 키는 Azure Key Vault에서 관리하고, 로컬은 `.env.example` 형식의 `.env`를 사용합니다.

- 처음이라면: [docs/git-flow.md](docs/git-flow.md) — 브랜치 만들기부터 머지까지 따라 하는 Git 작업 흐름
- 전체 규칙: [docs/dev-guide.md](docs/dev-guide.md) — 로컬 환경, 릴리스, API 키, CI
