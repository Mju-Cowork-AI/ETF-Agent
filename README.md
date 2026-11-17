# ETF-Agent: ETF 질의응답 챗봇

> **배포된 서비스:** (11-21 배포 리허설 후 URL 기입. 예: `https://<앱 이름>.<배포처 주소>`)
>
> AI가 생성한 답변이며 투자 조언이 아닙니다. 수치는 기준일 데이터입니다.

<!-- 스크린샷: 배포 후 docs/images/에 넣고 아래 주석을 풉니다 -->
<!-- ![서비스 화면](docs/images/screenshot_main.png) -->
<!-- ![검증 과정 보기](docs/images/screenshot_guard.png) -->

## 서비스 개요

국내 ETF에 대해 물으면 **조회한 근거(ETF DB와 문서)로만** 답하고, **준법 검증을 통과한 답만** 보여 주는 챗봇입니다.

- **할 수 있는 일:** ETF 상품 정보 조회(총보수·실부담비용·순자산·구성종목 등), ETF 비교, ETF 개념·용어 설명, 투자 권유·전망 요청에 대한 안전한 안내
- **에이전트 구조:** LLM이 질문을 보고 어떤 도구(ETF DB 조회, 문서 검색)를 쓸지 계획합니다. 결과가 부족하면 한 번 더 계획하고, 답을 쓴 뒤 다른 LLM이 검증합니다. 반복 횟수와 안전 경계는 코드가 제한합니다.
- **설계 원칙:** LLM은 숫자를 만들지 않습니다. 수치는 DB에서만 가져오고, 기준일과 투자 고지는 코드가 붙입니다.
- **기술 스택:** Python, FastAPI, LangGraph, Postgres(pgvector), React, Docker, Azure OpenAI
- **배경:** LLM 기반 ETF 질의응답 챗봇 구축 RFP를 바탕으로 한 팀 프로젝트입니다. 자세한 기획은 [docs/plan.md](docs/plan.md)에 있습니다.

## 팀원별 역할

| 역할 | 이름 | 맡은 일 |
|---|---|---|
| AI Solutions Architect | | 아키텍처·재계획 루프 설계, 외부 호출 전 개인정보 차단, 가드레일 기준, 레드팀·정상 질문 평가셋, 일정·범위 관리, README |
| AI Engineer | | 에이전트 그래프(계획·재계획·합성·검증), 숫자 대조, 프롬프트, Azure 모델 연결 |
| Cloud Engineer | | 배포·시크릿, 하루 질문 상한, 예산 알림·사용량 모니터링, 평가 실행 운영, 사용자 테스트 진행 |
| Data Scientist | | ETF 데이터 수집·검증·적재, 문서 검색(RAG) 색인·튜닝, 일반 평가셋 정답값 |

역할별 상세는 [docs/roles.md](docs/roles.md)에 있습니다.

## 로컬 실행 방법 (FastAPI 기반)

> **아직 확정되지 않은 값이 있습니다.** FastAPI 기반 코드는 채팅방에서 정한 방식(11-18 18:00까지)으로 이 저장소에 들여옵니다. 그 전까지 아래의 경로·명령은 **들여올 코드 기준이며 "확인 필요"** 표시가 있는 것은 들여온 뒤 고칩니다.

1. **필요한 도구**
   - Git, GNU Make
   - Docker, Docker Compose v2.24 이상
   - Python: FastAPI 기반 코드는 3.14, 이 저장소 CI는 3.11 → **확인 필요**(코드 들여오기 뒤 하나로 맞춤)
   - [uv](https://docs.astral.sh/uv/), Node.js 24(웹 화면 테스트·린트용)
2. **받기**
   ```bash
   git clone git@github.com:Mju-Cowork-AI/ETF-Agent.git
   cd ETF-Agent
   git switch dev
   ```
3. **환경변수**
   ```bash
   cp .env.example .env
   ```
   - Azure 엔드포인트·키·배포 이름은 Azure 키 관리자에게 받습니다(키 원본은 Azure Key Vault). **키는 절대 커밋하지 않습니다.**
   - 변수 이름은 들여온 코드의 설정 이름에 맞춰 바뀔 수 있습니다(**확인 필요**).
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
7. **테스트**
   ```bash
   make check      # CI와 같음: ruff, compileall, pytest. 외부 API는 mock
   ```
8. **종료:** `./scripts/run-local.sh down`(데이터 볼륨 유지, 경로는 확인 필요)

## 문서

| 문서 | 내용 |
|---|---|
| [docs/plan.md](docs/plan.md) | 통합 기획서(목표·범위, 아키텍처, 데이터, 안전장치, 평가, 일정, 위험) |
| [docs/decisions.md](docs/decisions.md) | 결정 기록(결정됨 / 결정 필요) |
| [docs/roles.md](docs/roles.md) | 역할별 할 일과 날짜별 완료 기준 |
| [docs/team_rules.md](docs/team_rules.md) | 팀이 더한 협업 규칙(승인 필수 PR, 키, 데이터, 개인정보) |
| [docs/decision_board.md](docs/decision_board.md) | 채팅방 결정 안건(결정 방식·주도 역할·기한) |
| [CLAUDE.md](CLAUDE.md) | Claude Code 공통 규칙 |

---

## 작업 공간 안내

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

- **브랜치 이름:** `타입/짧은-설명` — 타입은 `feat`, `fix`, `refactor`, `docs`, `chore`, `data`, `infra`, `prompt`, `eval`, `test`
- **커밋 메시지:** `타입: 내용` (한글 가능)
- **작업 흐름:** 모든 작업은 브랜치 → `dev` PR. CI가 통과하면 작성자가 직접 머지해도 됩니다. 리뷰가 필요하면 보류하고 담당자에게 전달해 주세요.
- **승인 필수 PR:** 개인정보 차단, 가드(검증), 숫자 대조, 데이터 파이프라인을 고치는 PR은 팀원 1명 승인 후 머지합니다.
- **충돌 관리:** 작업 브랜치는 매일 `dev`를 받아 충돌을 정리합니다.
- **릴리스:** `dev` → `main`은 Cloud Engineer만 가능하게 설정했습니다. (권한 필요하면 말씀해주세요)
- **API 키:** 커밋 금지. 키는 Azure Key Vault에서 관리하고 CI·배포용은 GitHub Secrets에 복사합니다. 로컬은 `.env.example` 형식의 `.env`를 사용합니다.

- 처음이라면: [docs/git-flow.md](docs/git-flow.md) — 브랜치 만들기부터 머지까지 따라 하는 Git 작업 흐름
- 전체 규칙: [docs/dev-guide.md](docs/dev-guide.md) — 로컬 환경, 릴리스, API 키, CI
