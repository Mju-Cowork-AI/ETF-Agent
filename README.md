# ETF-Agent: ETF 질의응답 챗봇

> **배포된 서비스:** (11-21 배포 리허설 후 URL 기입. 예: `https://<앱 이름>.<배포처 주소>`)
>
> AI가 생성한 답변이며 투자 조언이 아닙니다. 수치는 기준일 데이터입니다.

<!-- 스크린샷: 배포 후 docs/images/에 넣고 아래 주석을 풉니다 -->
<!-- ![서비스 화면](docs/images/screenshot_main.png) -->
<!-- ![검증 과정 보기](docs/images/screenshot_guard.png) -->

## 서비스 개요

코멘토 명지대 AI 2조의 팀 프로젝트입니다. 국내 ETF에 대해 물으면 **조회한 근거(ETF DB와 문서)로만** 답하고, **준법 검증을 통과한 답만** 보여 주는 챗봇입니다.

- **할 수 있는 일:** ETF 상품 정보 조회(총보수·실부담비용·순자산·구성종목 등), ETF 비교, ETF 개념·용어 설명, 투자 권유·전망 요청에 대한 안전한 안내
- **에이전트 구조:** LLM이 질문을 보고 어떤 도구(ETF DB 조회, 문서 검색)를 쓸지 계획합니다. 결과가 부족하면 한 번 더 계획하고, 답을 쓴 뒤 다른 LLM이 검증합니다. 반복 횟수와 안전 경계는 코드가 제한합니다.
- **설계 원칙:** LLM은 숫자를 만들지 않습니다. 수치는 DB에서만 가져오고, 기준일과 투자 고지는 코드가 붙입니다.
- **기술 스택:** Python, FastAPI, LangGraph, Postgres(pgvector), React, Docker, Azure OpenAI
- **배경:** LLM 기반 ETF 질의응답 챗봇 구축 RFP를 바탕으로 합니다. 자세한 기획은 [docs/plan.md](docs/plan.md)에 있습니다.

## 팀원별 역할

| 역할 | 이름 | 맡은 일 |
|---|---|---|
| AI Solutions Architect | | 아키텍처·재계획 루프 설계, 외부 호출 전 개인정보 차단, 가드레일 기준, 레드팀·정상 질문 평가셋, 일정·범위 관리, README |
| AI Engineer | | 에이전트 그래프(계획·재계획·합성·검증), 숫자 대조, 프롬프트, Azure 모델 연결, 평가 실행 운영 |
| Cloud Engineer | | 저장소 관리, 배포·시크릿, 하루 질문 상한, 예산 알림·사용량 모니터링, 평가 실행 환경(배포 URL·키) 지원, 사용자 테스트 진행 |
| Data Scientist | | ETF 데이터 수집·검증·적재, 문서 검색(RAG) 색인·튜닝, 일반 평가셋 정답값 |

역할별 상세는 [docs/roles.md](docs/roles.md)에 있습니다.

## 로컬 실행 방법 (FastAPI 기반)

> **아직 확정되지 않은 값이 있습니다.** FastAPI 기반 코드는 채팅방에서 정한 방식(11-18 18:00까지)으로 이 저장소에 들여옵니다. 그 전까지 아래의 경로·명령은 **들여올 코드 기준이며 "확인 필요"** 표시가 있는 것은 들여온 뒤 고칩니다.

1. **필요한 도구**
   - Git, GNU Make
   - Docker, Docker Compose v2.24 이상
   - Python 3.14 (저장소 CI·로컬 환경과 FastAPI 기반 코드가 같은 버전)
   - [uv](https://docs.astral.sh/uv/), Node.js 24(웹 화면 테스트·린트용)
2. **받기와 개발 환경**
   ```bash
   git clone git@github.com:Mju-Cowork-AI/ETF-Agent.git
   cd ETF-Agent
   git switch dev
   make setup      # .venv 생성 + 의존성 설치 + .env가 없으면 .env.example을 복사
   ```
   - `make setup`은 [uv](https://docs.astral.sh/uv/)가 있으면 Python 3.14를 자동으로 받아 씁니다. 3.11로 만든 `.venv`가 있으면 `make clean` 후 다시 `make setup`을 실행합니다.
   - `make help`로 전체 명령을 봅니다. make를 쓸 수 없으면(Windows PowerShell 등) [docs/dev-guide.md](docs/dev-guide.md) 1장을 봅니다.
3. **환경변수:** `make setup`이 만든 `.env`에 값을 채웁니다.
   - Azure 엔드포인트·키·배포 이름은 Azure 키 관리자에게 받습니다. 보관 규칙은 [docs/dev-guide.md](docs/dev-guide.md) 6장. **키는 절대 커밋하지 않습니다.**
   - 변수 이름은 들여온 코드의 설정 이름에 맞춰 바뀝니다(**확인 필요**).
4. **실행**(DB·API·웹을 띄우고 마이그레이션·샘플 적재까지 수행)
   ```bash
   ./scripts/run-local.sh        # 실제 모델(Azure)로 실행. 경로는 확인 필요
   ./scripts/run-fake.sh         # API 키 없이 가짜 모델로 실행. 경로는 확인 필요
   ```
5. **데이터 적재**
   - 마이그레이션·시드·문서 적재·수집: `make migrate`, `make seed`, `make ingest`, `make collect`(FastAPI 기반 Makefile 기준, **확인 필요**)
   - 실데이터(ETF 5개) 파이프라인은 옮겨 오는 중이라 명령이 **미정**입니다. 데이터를 갱신한 뒤에는 API를 재시작합니다.
6. **접속**
   - 웹: <http://localhost:5173>, API 문서: <http://localhost:8000/docs>(포트는 **확인 필요**)
   - 로컬은 개발용 로그인으로 들어갑니다. 공개 URL의 로그인 없는 접근은 11-21 배포 리허설에서 추가합니다.
7. **검사**
   ```bash
   make check      # CI와 같음: ruff, compileall, pytest. 외부 API는 mock
   ```
   - `make check`가 통과하면 CI도 통과합니다. PR 올리기 전에 실행합니다.
8. **종료:** `./scripts/run-local.sh down`(데이터 볼륨 유지, 경로는 확인 필요)

### 실행할 때 주의할 점

- **Windows:** `make`와 bash 스크립트를 쓰므로 **WSL2** 안에서 실행합니다.
- **Docker Compose v2.24 이상**이 필요합니다(`docker compose version`으로 확인).
- **포트 충돌:** 로컬 Postgres가 5432 포트를 쓰고 있으면 충돌합니다. `.env`의 `POSTGRES_PORT`를 다른 값으로 바꿉니다.
- **`make test`:** DB가 떠 있어야 하고, `_test`로 끝나는 테스트 DB를 지우고 다시 만듭니다.
- **데이터 갱신 뒤:** `make seed`, `make ingest`, `make collect` 다음에는 **`make restart`**를 실행합니다. 안 하면 캐시 때문에 이전 값이 나옵니다.
- **Azure 연결:** `LLM_MODEL`에는 모델 이름이 아니라 **배포 이름**을 넣고, base URL은 **`/openai/v1/`로 끝나야** 합니다.

## 폴더 구조

지금은 저장소 뼈대 구조입니다. 코드 들여오기 뒤 Cloud Engineer가 갱신합니다([docs/roles.md](docs/roles.md) 4장).

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

## 팀 규칙과 문서

| 문서 | 내용 |
|---|---|
| [docs/git-flow.md](docs/git-flow.md) | 처음이라면: 브랜치 만들기부터 머지까지 따라 하는 Git 작업 흐름 |
| [docs/dev-guide.md](docs/dev-guide.md) | 전체 규칙: 로컬 환경, 브랜치·커밋 타입, PR(승인 필수 PR 포함), 릴리스, API 키, CI |
| [docs/team_rules.md](docs/team_rules.md) | 팀이 더한 규칙: 옮겨 온 코드 리뷰, 커밋 금지 파일, 테스트, 크레딧, 데이터, 개인정보 |
| [docs/plan.md](docs/plan.md) | 통합 기획서(목표·범위, 아키텍처, 데이터, 안전장치, 평가, 일정, 위험) |
| [docs/decisions.md](docs/decisions.md) | 결정 기록(결정됨 / 결정 필요) |
| [docs/decision_board.md](docs/decision_board.md) | 채팅방 결정 안건(결정 방식·주도 역할·기한) |
| [docs/roles.md](docs/roles.md) | 역할별 할 일과 날짜별 완료 기준 |
| [CLAUDE.md](CLAUDE.md) | Claude Code 공통 규칙 |
