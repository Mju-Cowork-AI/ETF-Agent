# 고도화 버전: Azure 구성

로컬은 Docker(Postgres·OpenAI API 또는 fake)로 개발하고, 고도화·배포 버전은 **Azure**에 둔다.
**팀 배포는 바로 아래 "리허설 배포 구성"을 따른다.** 그 뒤의 절(대응표, 모델, DB, 인증, 파일 저장)은 들여온 코드의 배경 설명과 대안이다.
코드 변경 없이 **환경변수만** 바꿔 옮기는 것이 원칙이다. 아직 스텁인 어댑터는 아래 표에 표시했다.

## 리허설 배포 구성 (2026-11-20 기준)

API·DB는 Azure, 웹은 Cloudflare Pages에 있다. 아래 명령은 11-20에 실제로 실행한 것이다.
비밀 값은 Key Vault(`kv-etf-agent-b084`)에만 있고, 앱은 관리 ID로 읽는다.

> 리허설 이미지는 `dev`에 #14(로그인 없는 접근)와 #17(하루 질문 상한)을 로컬에서 합쳐 빌드했다(태그 `rehearsal-0fcb11e`).
> 두 PR이 머지되면 `dev`에서 다시 빌드해 올린다.

### 리소스

| 리소스 | 이름 | 지역 | 비고 |
| --- | --- | --- | --- |
| 리소스 그룹 | `rg-etf-agent` | koreacentral | 모델 리소스만 `etf-agent-local-rg`에 있다 |
| Key Vault | `kv-etf-agent-b084` | koreacentral | `LLM-API-KEY`, `DATABASE-URL`, `LOCAL-JWT-SECRET`, `ADMIN-TOKEN` 등 |
| 모델(Azure OpenAI) | `etf-agent-local-22eaff` | koreacentral | 배포: `gpt-6-sol`(생성), `gpt-6-luna`(검증), `text-embedding-3-small`. gpt-6 두 배포는 각 50K TPM |
| DB | `pg-etf-agent-japaneast` | **Japan East** | PostgreSQL 17, B1ms, 32GB. koreacentral은 이 구독에서 B1ms 생성이 `SkuNotAvailable`로 거부되어 일본 동부에 만들었다 |
| 컨테이너 레지스트리 | `acretfagentb084` | koreacentral | Basic |
| 로그 | `log-etf-agent` | koreacentral | Log Analytics |
| Container Apps 환경 | `cae-etf-agent` | koreacentral | |
| 관리 ID | `id-etf-agent-api` | koreacentral | 레지스트리 `AcrPull`, Key Vault `Key Vault Secrets User` |
| API 앱 | `ca-etf-agent-api` | koreacentral | 0.5 vCPU / 1Gi, 복제본 1개 고정(최소 1, 최대 1) |
| 설정 작업 | `caj-etf-agent-setup` | koreacentral | 수동 실행: 마이그레이션 → 샘플 시드 → 샘플 문서 적재 |
| 웹 | Cloudflare Pages `etf-agent` | — | <https://etf-agent.pages.dev>. Cloud Engineer의 Cloudflare 계정 |

- 복제본을 1개로 고정한 이유: 캐시가 프로세스 메모리에 있어 인스턴스가 여러 개면 캐시 삭제가 전파되지 않는다.
- DB 방화벽은 "Azure 서비스 허용"(0.0.0.0)만 열려 있다. 로컬 PC에서는 접속되지 않는다(접속하려면 자기 IP 규칙을 추가).
- 운영 화면에서 올린 원본 파일은 컨테이너 디스크(`/data/storage`)에 있어 재시작하면 사라진다(DB의 문서·청크는 남는다).

### API 환경변수

정의 예시는 [`containerapp-api.example.yaml`](containerapp-api.example.yaml), 작업은 [`containerapp-job.example.yaml`](containerapp-job.example.yaml)에 있다.

| 변수 | 값 |
| --- | --- |
| `APP_ENV` | `prod` |
| `DATABASE_URL`, `LLM_API_KEY`, `LOCAL_JWT_SECRET`, `ADMIN_TOKEN` | Key Vault 참조(`secretref:`) |
| `AUTH_PROVIDER` / `ANON_ACCESS_ENABLED` | `local` / `true` |
| `ADMIN_AUTH` | `token` |
| `DAILY_QUESTION_LIMIT` | `200`(임시) |
| `CORS_ORIGINS` | `https://etf-agent.pages.dev` |
| `LLM_PROVIDER` / `LLM_BASE_URL` | `openai_compat` / `https://etf-agent-local-22eaff.openai.azure.com/openai/v1/` |
| `LLM_MODEL` / `JUDGE_MODEL` | `gpt-6-sol` / `gpt-6-luna` |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` / `EMBEDDING_REQUEST_DIMENSIONS` | `text-embedding-3-small` / `1024` / `true` |
| `FALLBACK_PROVIDER` / `STORAGE_PROVIDER` / `STORAGE_LOCAL_DIR` / `TRACER` | `none` / `local` / `/data/storage` / `pg` |

`LOCAL_JWT_SECRET`은 바꾸지 않는다. 바꾸면 발급된 익명 토큰이 모두 무효가 되어 사용자가 이전 대화를 잃는다.

### 다시 배포하는 절차

사전 조건: `az login`, Docker(Apple Silicon은 `linux/amd64`로 빌드), 웹은 `npx wrangler login`.

웹(Cloudflare Pages `etf-agent`)은 Cloud Engineer의 개인 Cloudflare 계정에 있어, 지금은 Cloud Engineer만 배포할 수 있다. 다른 팀원이 배포하려면 Cloud Engineer가 그 계정에 구성원으로 초대해야 한다.

```bash
# 1) API 이미지 빌드·푸시 (레포 루트에서). 무료 구독은 `az acr build`가 막혀 있어 로컬에서 빌드한다
TAG=$(git rev-parse --short HEAD)
IMG=acretfagentb084.azurecr.io/etf-agent-api:$TAG
az acr login -n acretfagentb084
docker buildx build --platform linux/amd64 -f apps/api/Dockerfile -t $IMG --push .

# 2) 마이그레이션·시드·적재 (스키마나 샘플 데이터가 바뀌었을 때)
az containerapp job update -g rg-etf-agent -n caj-etf-agent-setup --image $IMG
az containerapp job start  -g rg-etf-agent -n caj-etf-agent-setup
az containerapp job execution list -g rg-etf-agent -n caj-etf-agent-setup \
  --query "[].{name:name,status:properties.status}" -o table   # Succeeded 확인(11-20: 47초)

# 3) API 앱을 새 이미지로
az containerapp update -g rg-etf-agent -n ca-etf-agent-api --image $IMG
curl https://ca-etf-agent-api.wittyrock-5cacb91d.koreacentral.azurecontainerapps.io/health   # {"status":"ok","db":"ok"}

# 4) 웹 빌드·배포 (VITE_* 값은 빌드할 때 고정된다)
cd apps/web && npm ci
VITE_API_BASE_URL=https://ca-etf-agent-api.wittyrock-5cacb91d.koreacentral.azurecontainerapps.io \
  VITE_AUTH_MODE=anonymous npm run build
ls dist    # _redirects, assets, favicon.svg, index.html만 있어야 한다
npx wrangler pages deploy dist --project-name etf-agent --branch main
```

- 환경변수만 바꿀 때: `az containerapp update -g rg-etf-agent -n ca-etf-agent-api --set-env-vars 이름=값`
- Key Vault 값을 바꾼 뒤에는 새 리비전이 떠야 반영된다(위 명령으로 아무 환경변수나 갱신하거나 이미지를 다시 지정).
- 로그: Log Analytics `log-etf-agent`의 `ContainerAppConsoleLogs_CL`, `ContainerAppSystemLogs_CL`
- 3)에서 `az containerapp update --image`는 11-20에 직접 실행해 보지 않았다(앱은 YAML로 한 번에 만들었다). 2)의 작업 갱신·실행과 4)는 실행해 확인했다.

### 리허설에서 걸린 것

- **DB 지역**: koreacentral의 B1ms는 SKU 목록에는 나오지만 영역 1·2·3 모두 생성이 거부됐다. 일본 동부는 한 번에 됐다.
- **`--database-name`**: `az postgres flexible-server create`에서 쓸 수 없다. 서버를 만든 뒤 `az postgres flexible-server db create --name etf_agent`로 만든다.
- **확장**: 서버 매개변수 `azure.extensions`에 `VECTOR,PG_TRGM`을 넣어야 마이그레이션 0001·0002가 통과한다.
- **`az acr build`**: 무료 구독에서 `TasksOperationsNotAllowed`로 거부된다.
- **셸 명령 인자**: `az containerapp job create --command "/bin/sh" "-c" …`는 `-c`를 옵션으로 읽어 실패한다. 작업은 YAML(`--yaml`)로 만든다.
- **wrangler 4의 Pages 프로젝트 생성**: `wrangler pages project create`가 Workers로 넘기려다 실패하면서 `apps/web`의 `package.json`·`vite.config.ts`를 고치고 `wrangler.jsonc`와 `dist/wrangler.json`(로컬 경로 포함)을 만든다. 이 상태로 배포하면 그 파일이 공개된다. 프로젝트는 이미 만들어져 있으니 다시 만들지 말고, 배포 전에 `git status`와 `ls dist`를 확인한다.

### 11-20 확인 결과

- `/health` 200(`db: ok`), 익명 발급 200, `dev-login` 404, 운영 토큰 없는 `/admin/traces` 401
- 웹 주소에서 온 CORS 사전 요청은 허용, 다른 출처는 거부
- 손 질문 2건: 답변까지 약 5~8초, 가드 통과. 12문항 토큰 실측과 상한 값 계산은 11-21에 한다

## AWS → Azure 대응표

| 역할 | 이전 계획(AWS) | Azure | 이 레포에서 바꿀 것 | 상태 |
| --- | --- | --- | --- | --- |
| 생성 모델(관리형) | Bedrock | **Azure OpenAI**(Microsoft Foundry) | `LLM_PROVIDER=openai_compat`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`=배포 이름 | 동작(로컬에서 실측) |
| 임베딩 | Bedrock Titan v2 | Azure OpenAI `text-embedding-3-small`(`dimensions=1024`) | `EMBEDDING_MODEL`=배포 이름, `EMBEDDING_REQUEST_DIMENSIONS=true` | 동작 |
| 자체 호스팅 sLLM | EC2/ECS GPU + vLLM | Azure GPU VM(NC 계열) 또는 AKS GPU 노드 + vLLM | `LLM_BASE_URL`=VNet 내부 주소 | 동작(어댑터 공통) |
| LLM 폴백 | Bedrock | Azure OpenAI | `FALLBACK_PROVIDER=openai_compat`, `FALLBACK_BASE_URL`, `FALLBACK_API_KEY`, `FALLBACK_MODEL` | 동작(vLLM을 1순위로 쓸 때만 의미 있음) |
| DB | RDS/Aurora PostgreSQL | **Azure Database for PostgreSQL Flexible Server**(D9). 대안: Supabase 서울 리전 | `DATABASE_URL` | 코드 변경 없음 |
| 인증 | Cognito | **자체 발급 JWT 유지**(기본) 또는 Microsoft Entra External ID | `AUTH_PROVIDER=local` 또는 `entra` | local은 로그인 수단 보강 필요, entra는 스텁 |
| 파일 저장 | S3 | **Azure Blob Storage** | `STORAGE_PROVIDER=azure_blob` | 스텁(`app/storage/azure_blob.py`) |
| API 실행 | ECS Fargate | Azure Container Apps | 컨테이너 환경변수 | — |
| 배치(`jobs/`) | EventBridge + ECS 태스크 | Container Apps Jobs(예약 실행) | — | — |
| 웹(정적) | S3 + CloudFront | Cloudflare Pages(리허설에서 사용). 대안: Azure Static Web Apps | `VITE_API_BASE_URL`, `VITE_AUTH_MODE` | 동작 |
| 이미지 저장소 | ECR | Azure Container Registry | — | — |
| 비밀값 | Secrets Manager | Key Vault(Container Apps 비밀 참조) | — | — |
| 서비스 간 권한 | IAM 역할 | 관리 ID(Managed Identity) + RBAC | — | — |
| 네트워크 | VPC·보안 그룹 | VNet·NSG·Private Endpoint | — | — |
| 로그·지표 | CloudWatch | Azure Monitor(Log Analytics·Application Insights) | — | — |

어떤 방식이든 질의는 저장 전 `privacy.mask_pii()`를 거치고, 답변은 컴플라이언스 가드를 통과해야 나간다.

## 모델

### A. Azure OpenAI (기본 권장)

설정 예시: [`azure-openai.env.example`](azure-openai.env.example)

Azure OpenAI의 v1 엔드포인트는 OpenAI API와 형식이 같아 로컬과 **같은 어댑터(openai_compat)** 를 쓴다.
`LLM_MODEL`·`EMBEDDING_MODEL`에는 모델 이름이 아니라 **배포 이름**을 넣는다.

```dotenv
LLM_PROVIDER=openai_compat
LLM_BASE_URL=https://<리소스 이름>.openai.azure.com/openai/v1/
LLM_MODEL=<생성 모델 배포 이름>
EMBEDDING_MODEL=<임베딩 배포 이름>
EMBEDDING_DIM=1024
EMBEDDING_REQUEST_DIMENSIONS=true
```

- 로컬과 같은 임베딩 모델(`text-embedding-3-small`, 1024차원)을 쓰면 다시 임베딩할 필요가 없다.
- `LLM_API_KEY`는 Key Vault에 두고 Container Apps 비밀 참조로 주입한다. `.env`에 넣지 않는다.
  키 없이 관리 ID 토큰으로 호출하는 방식은 아직 어댑터에 없다(필요하면 `app/llm/openai_compat.py`에 추가).
- 모델·배포 유형(GlobalStandard 등)별 할당량은 구독마다 다르다. 무료 체험 구독은 koreacentral에서
  `gpt-5-mini`·`text-embedding-3-small`만 할당량이 있었다(2026-11 기준).
- 타임아웃·재시도는 로컬과 같다(`LLM_TIMEOUT_SECONDS`). 실패하면 `LLMError` → 안전 답변(`llm_unavailable`).

### B. 자체 호스팅 sLLM (vLLM)

설정 예시: [`vllm.env.example`](vllm.env.example)

외부 API 사용이 보안 정책상 불가할 때 쓴다. vLLM도 OpenAI 호환 API라 같은 어댑터를 쓴다
(`OPENAI_MAX_TOKENS_PARAM=max_tokens`, `OPENAI_OMIT_TEMPERATURE=false`, `OPENAI_REASONING_EFFORT=off`).

```bash
# GPU VM(예: NC 계열 T4 16GB)에서
vllm serve K-intelligence/Midm-2.0-Mini-Instruct \
  --served-model-name midm-2.0-mini --max-model-len 8192 --port 8000
```

- vLLM 서버는 VNet의 프라이빗 서브넷에 두고 NSG로 API 서버에서만 접근하게 한다.
- GPU VM은 구독 할당량 신청이 필요하다(무료 체험 구독은 GPU 할당량이 없다).
- 생성과 임베딩은 엔드포인트를 따로 둘 수 있지만(`EMBEDDING_BASE_URL`) **API 키는 하나(`LLM_API_KEY`)를 같이 쓴다.**
  vLLM 생성 + Azure OpenAI 임베딩을 섞으려면 vLLM을 `--api-key`로 같은 값에 맞추거나, 임베딩도 vLLM에서 띄운다.
- 모델 라이선스를 확인한다(Mi:dm 2.0 MIT, EXAONE은 비상업 라이선스라 상용 불가).

### C. 자체 호스팅 + Azure OpenAI 폴백

B 설정에 다음을 더한다. vLLM 호출이 실패하면 `FALLBACK_ALLOWED_INTENTS`에 든 의도만 Azure OpenAI로 다시 호출한다.
제한하는 것은 프롬프트에 넣는 **자료**(문서 근거·ETF 데이터·공시)다. 허용된 의도의 자료만 있으면 폴백하며, 이때 질문 문장과 이전 대화는 그대로 함께 전송된다.

```dotenv
FALLBACK_PROVIDER=openai_compat
FALLBACK_BASE_URL=https://<리소스 이름>.openai.azure.com/openai/v1/
FALLBACK_MODEL=<폴백 모델 배포 이름>
FALLBACK_ALLOWED_INTENTS=faq
```

- `FALLBACK_API_KEY`는 Key Vault 비밀 참조로 주입한다. URL이나 모델이 비어 있으면 기동하지 않는다.
- 폴백은 gpt-5 계열 형식(`max_completion_tokens`, 온도 생략)으로 부른다. 생각 분량은 `FALLBACK_REASONING_EFFORT`(기본 `minimal`).

## DB — Supabase 서울 리전 (비용 우선)

- 프로젝트를 만들 때 리전을 **Northeast Asia (Seoul)**, `ap-northeast-2`로 고른다. Azure koreacentral도 서울이라 API ↔ DB 지연이 작다.
- `DATABASE_URL`은 **Session pooler(5432)** 주소를 `postgresql+asyncpg://` 스킴으로 넣는다
  (Transaction pooler는 asyncpg prepared statement와 충돌한다). pgvector·pg_trgm은 마이그레이션이 `extensions` 스키마에 만든다(이 스키마가 없는 로컬·Azure에서는 기본 스키마).
- 무료 플랜은 DB 500MB이고 **1주일 동안 사용이 없으면 일시 중지**된다(데이터는 남고 수동 복구). 데모·개발은 무료로,
  상시 운영은 Pro로 올린다. 요금·한도는 바뀔 수 있으니 supabase.com/pricing에서 확인한다.
- Supabase는 Azure 밖(AWS 서울)에 있어 연결이 공용 인터넷(TLS)을 지난다. VNet 안에만 DB를 둬야 하는 보안 요건이 생기면 아래 대안으로 옮긴다.

### 대안: Azure Database for PostgreSQL Flexible Server

`DATABASE_URL`만 바꾸면 된다. 인스턴스가 상시 과금되므로 사설망(Private Endpoint)·규모가 필요해질 때 쓴다.

- 서버 매개변수 `azure.extensions`에 `VECTOR`, `PG_TRGM`을 허용 목록으로 넣어야 마이그레이션의 `CREATE EXTENSION`이 통과한다.
- `DATABASE_URL=postgresql+asyncpg://<사용자>:<비밀번호>@<서버>.postgres.database.azure.com:5432/<DB>?ssl=require`
- 로컬 이미지와 같은 메이저 버전(PostgreSQL 17)을 고른다.

## 인증 — JWT는 그대로

API는 어느 방식이든 **Bearer JWT를 검증**한다(`app/auth/base.py`의 `AuthBackend`). 달라지는 것은 "누가 로그인시키고 토큰을 발급하는가"뿐이다.

| 방식 | 발급 | 설정 | 더 만들 것 |
| --- | --- | --- | --- |
| 자체 발급 JWT(기본) | API 서버 | `AUTH_PROVIDER=local`, `LOCAL_JWT_SECRET`(Key Vault) | 실제 로그인 수단. 지금 `dev-login`은 이메일만 받아 토큰을 주며 `APP_ENV=local`에서만 열린다 |
| Supabase Auth | Supabase | `AUTH_PROVIDER=supabase`, `SUPABASE_URL` | `app/auth/supabase_jwt.py`(JWKS 검증), web `src/lib/auth.ts`. DB를 Supabase에 두면 추가 비용 없이 쓸 수 있다 |
| Entra External ID | Azure | `AUTH_PROVIDER=entra`, `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID` | `app/auth/entra_jwt.py`(JWKS 검증), web 로그인 연동 |

자체 발급으로 갈 때 배포 전에 필요한 것: 비밀번호(해시 저장) 또는 소셜 로그인, 토큰 만료·재발급(지금은 12시간 단일 토큰),
로그인 시도 제한. 가입·비밀번호 재설정·소셜 로그인을 직접 만들고 싶지 않을 때 Supabase Auth나 Entra External ID로 넘어간다.

## 파일 저장 — Blob에 원본, DB에는 주소만

- 원본 파일(PDF 등)은 Blob 컨테이너에 두고, Postgres `documents.source_uri`에 주소(`azure_blob://uploads/…`)만 남긴다.
  운영 화면 업로드의 지금 로컬 구조(`local://uploads/…`)와 같아서 어댑터만 구현하면 된다(`make ingest`로 넣은 문서는 `file://…`이고 저장소를 거치지 않는다).
- 질문에 답할 때 읽는 것은 원본이 아니라 DB의 `chunks`(본문 조각·임베딩)다. 자주 조회되는 내용은 이미 DB에 있으므로
  원본을 DB에 중복 저장할 필요가 없다. 원본은 다시 ingest하거나 내려받을 때만 Blob에서 읽으면 되는데, 이 두 기능은 아직 없다(지금 저장소를 읽는 곳은 업로드 실패 시 되돌리기뿐이다).
- Blob에만 두고 DB 기록을 없애는 방식은 쓰지 않는다. 목록·검색은 DB의 문서·청크를 읽고, 재-ingest는 `source_uri`로 같은 문서를 찾아 갱신한다.
- 컨테이너는 비공개로 두고, API는 관리 ID(Storage Blob Data Contributor)로 접근한다. 사용자에게 원본을 내려줄 때는 만료 시간이 짧은 SAS URL을 쓴다.

## 배포 시 함께 바꿀 값

- `APP_ENV=prod` — `AUTH_PROVIDER=local`이면 `LOCAL_JWT_SECRET`이 없을 때 기동하지 않는다.
- `CORS_ORIGINS` — 웹 공개 주소(리허설은 `https://etf-agent.pages.dev`). 웹과 API의 주소가 달라서 반드시 넣는다.
- `TRACER` — `pg`만 동작한다. `langfuse`는 스텁이라 고르면 API가 기동하지 않는다.
- `ADMIN_AUTH` — 공개 URL에서는 `token`을 쓴다. 운영 API가 `X-Admin-Token` 헤더를 `ADMIN_TOKEN`(Key Vault, 공백을 뺀 32자 이상. 예: `openssl rand -hex 32`)과 비교하고, 팀원은 웹 주소 끝 `#admin`에서 이 값을 넣는다. `local`(JWT의 `role=admin`)은 로컬 개발용이다. `cf_access`(Cloudflare Access)는 스텁이라 운영 API가 501로 응답한다.
- `ANON_ACCESS_ENABLED=true` — 로그인 없는 접근(브라우저마다 익명 사용자, 토큰 30일). 웹은 `VITE_AUTH_MODE=anonymous`로 빌드한다. `LOCAL_JWT_SECRET`을 바꾸면 기존 익명 토큰이 모두 무효가 되어 사용자가 대화를 잃으므로, 한 번 등록한 뒤에는 바꾸지 않는다.
- `DAILY_QUESTION_LIMIT` — 하루 질문 상한(D13). 리허설 임시값 200, 11-21 토큰 실측 뒤 다시 계산한다.
