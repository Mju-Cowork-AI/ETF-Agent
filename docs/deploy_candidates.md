# 배포처 후보 조건표 (D9)

D9(배포처 결정)를 내리기 위한 비교표입니다([decision_board.md](decision_board.md)). 후보 4곳을 같은 기준으로 놓고, API·웹·DB를 각각 어디에 둘지 정하는 데 씁니다.

- **조사 기준:** 2026-11-18, 각 회사의 공식 문서와 가격표만 사용했습니다.
- **확인 필요:** 공식 근거를 찾지 못했거나 문서끼리 다른 칸입니다. 추측으로 채우지 않았습니다.
- **직접 해 보지 않은 것:** 실제 배포와 가입은 하지 않았습니다. 표의 내용은 문서 문구 기준입니다.

## 1. 크레딧 상황: 새로 받을 수 있는 곳은 Azure뿐

세 클라우드 모두 신규 고객에게만 무료 크레딧을 줍니다.

| 클라우드 | 신규 가입 크레딧 | 기간 | 우리 팀 상황 |
|---|---|---|---|
| AWS | 100달러(활동을 하면 최대 100달러 추가) | 6개월 또는 크레딧 소진 시 종료. 약관에는 12개월로 적혀 있어 문서끼리 다름(확인 필요) | Cloud Engineer가 이미 받아 씀. 새로 받을 수 없음 |
| GCP | 300달러 | 90일 | Cloud Engineer가 이미 받아 씀. 새로 받을 수 없음 |
| Azure | 200달러 | 30일 | **지금 쓰는 중**(D2) |

- **무료 크레딧을 쓸 수 있는 클라우드는 Azure 하나입니다.** AWS와 GCP는 크레딧 없이 무료 제공량만 쓰거나, 다른 팀원이 새 계정을 만들어야 합니다.
- 프로젝트 기간이 약 1개월이라, 기간이 30일인 Azure 크레딧으로도 마감(11-30)까지는 맞습니다. 모델 호출과 배포를 한 구독에서 처리할 수 있습니다.
- 한계는 크레딧이 끝난 뒤입니다. 무료 체험 구독이 비활성화되면 배포한 URL도 닫힙니다(2장). 마감 뒤에도 URL을 열어 두려면 종량제로 올리거나 다른 곳으로 옮겨야 합니다.

근거: [AWS 무료 플랜](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html), [AWS 무료 플랜 FAQ](https://aws.amazon.com/free/free-tier-faqs/), [GCP 무료 제공 범위](https://docs.cloud.google.com/free/docs/free-cloud-features), [Azure 무료 계정](https://azure.microsoft.com/en-us/pricing/purchase-options/azure-account)

## 2. 먼저 알아야 할 것

| 발견 | 영향 |
|---|---|
| **HF Spaces의 Docker Space는 유료 플랜(PRO, 월 9달러)이 있어야 만들 수 있음** | "무료 API와 Azure 크레딧 범위 안" 제약 밖입니다. 무료 후보에서 빠집니다 |
| **AWS App Runner는 2026-04-30부터 신규 고객을 받지 않음** | 팀에 기존 App Runner 고객 계정이 없으면 쓸 수 없습니다. AWS는 ECS Express Mode를 권합니다 |
| **Azure 무료 체험 구독은 30일이 지나거나 크레딧이 끝나면 비활성화됨** | Container Apps의 월 무료 제공량과 별개로, 종량제로 올리지 않으면 12월에 URL이 닫힙니다(D13) |
| **요청 시간 상한이 플랫폼마다 다름** | 답변을 SSE로 보내므로, 한 요청이 상한을 넘으면 끊깁니다. App Runner 120초, Container Apps 240초, Cloud Run 기본 5분(최대 60분) |
| **HF Spaces는 나가는 요청을 80, 443, 8080 포트만 허용** | 문서대로라면 Space에서 외부 Postgres(5432)에 붙을 수 없습니다(직접 시험하지 않음) |

## 3. 조건표

| 항목 | HF Spaces (Docker) | AWS App Runner | GCP Cloud Run | Azure Container Apps |
|---|---|---|---|---|
| **무료 상시 운영 조건** | 무료 아님. Docker Space 생성에 PRO(월 9달러) 필요, 카드 결제만 가능. CPU Basic 하드웨어 자체는 시간당 요금 없음. 48시간 안 쓰면 잠들고, 방문하면 자동으로 다시 켜짐 | 신규 고객 불가. 무료 제공량 없음. 0으로 줄지 않고 인스턴스 1개를 유지해 메모리 요금이 계속 나옴(콜드 스타트 없음) | 매월 무료: vCPU 180,000초, 메모리 360,000GiB초, 요청 200만 건. 종료일 없음. 기본값은 0으로 줄어듦(유휴 인스턴스는 최대 15분 유지). 다음 요청에 새 인스턴스가 뜨는 콜드 스타트. 최소 인스턴스 1개는 요청이 없어도 과금. 가입에 카드 등 결제 수단 필요. 체험 크레딧 300달러(90일)가 끝나면 올리지 않을 경우 자원이 멈추고 30일 뒤 삭제 | 매월 무료(구독당): vCPU 180,000초, 메모리 360,000GiB초, 요청 200만 건. 기본 최소 복제본 0, 300초 뒤 0으로 줄어듦. 0일 때는 과금 없음. 최소 복제본 1개는 유휴 요금이 나오고 무료 제공량에서 차감. 가입에 카드 필요. **무료 체험 구독은 30일 또는 크레딧 소진 시 비활성화, 계속 쓰려면 종량제로 올려야 함** |
| **메모리** | CPU Basic: 2 vCPU, 16GB, 디스크 50GB(재시작하면 지워짐) | 최소 0.25 vCPU / 0.5GB, 최대 4 vCPU / 12GB | 기본 512MiB, 최소 128MiB(1세대) 또는 512MiB(2세대), 최대 32GiB. 1 vCPU에서 4GiB까지 | 최소 0.25 vCPU / 0.5Gi, 0.25 vCPU / 0.5Gi 단위로 최대 4 vCPU / 8Gi |
| **시크릿 설정 방식** | Space 설정의 Secrets에 입력. 실행 중에는 환경변수로 들어옴 | Secrets Manager 또는 SSM Parameter Store를 ARN으로 참조. 배포할 때만 읽어 오므로 키를 바꾸면 다시 배포 | Secret Manager의 시크릿을 환경변수나 볼륨으로 연결. 서비스 계정에 접근 권한 필요 | 앱 시크릿에 직접 저장하거나 Key Vault 참조(관리 ID). 환경변수에서 `secretref:이름`으로 사용. 바꾸면 재시작 또는 새 리비전 필요 |
| **DB 일시 중지 조건** | 같은 Space 안에 Postgres를 띄우면 재시작·재배포 때 데이터가 지워짐. 외부 DB는 포트 제한(80, 443, 8080)에 걸림 | RDS: 자동 일시 중지 없음(수동으로 멈추면 7일 뒤 자동 시작). 새 계정은 크레딧 방식이라 6개월 또는 크레딧 소진 시 종료 | Cloud SQL은 상시 무료 대상이 아님. 자동 일시 중지 없음. 체험이 끝나면 멈춤 | PostgreSQL flexible server: 자동 일시 중지 없음(수동으로 멈추면 7일 뒤 자동 시작). 무료 계정 12개월 제공량(B1ms 750시간, 32GB)이 있으나 구독이 비활성화되면 같이 멈춤 |
| **요청 시간 상한(SSE)** | 확인 필요 | 요청 전체 120초 | 기본 5분, 최대 60분 | 240초 |
| **Docker·공개 URL** | Dockerfile 지원, 기본 포트 7860, 공개 Space는 로그인 없이 접속 | ECR 이미지 지원, 공개 접속 설정 가능 | Dockerfile 지원, `$PORT`(기본 8080)에서 수신, linux/amd64. 공개 접속은 Invoker 확인을 끄거나 `allUsers`에 권한 부여 | linux/amd64 이미지, 외부 ingress로 공개 주소 제공, 로그인 기능은 선택 |
| **근거 링크** | [Spaces 개요](https://huggingface.co/docs/hub/spaces-overview), [하드웨어·잠들기](https://huggingface.co/docs/hub/spaces-gpus), [Docker Space](https://huggingface.co/docs/hub/spaces-sdks-docker), [가격](https://huggingface.co/pricing) | [신규 고객 중단 안내](https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html), [가격](https://aws.amazon.com/apprunner/pricing/), [환경변수·시크릿](https://docs.aws.amazon.com/apprunner/latest/dg/env-variable.html), [요청 제한](https://docs.aws.amazon.com/apprunner/latest/dg/develop.html) | [가격](https://cloud.google.com/run/pricing), [무료 제공 범위](https://docs.cloud.google.com/free/docs/free-cloud-features), [메모리](https://docs.cloud.google.com/run/docs/configuring/services/memory-limits), [시크릿](https://docs.cloud.google.com/run/docs/configuring/services/secrets), [요청 시간](https://docs.cloud.google.com/run/docs/configuring/request-timeout), [컨테이너 계약](https://docs.cloud.google.com/run/docs/container-contract), [공개 접속](https://docs.cloud.google.com/run/docs/authenticating/public) | [과금·무료 제공량](https://learn.microsoft.com/en-us/azure/container-apps/billing), [확장](https://learn.microsoft.com/en-us/azure/container-apps/scale-app), [컨테이너 크기](https://learn.microsoft.com/en-us/azure/container-apps/containers), [시크릿](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets), [ingress](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview), [무료 계정 종료](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/avoid-charges-free-account) |

### 표를 읽을 때

- **상시 운영과 무료는 함께 가기 어렵습니다.** Cloud Run과 Container Apps의 무료 제공량은 0.25 vCPU / 0.5GiB 인스턴스 1개를 한 달 내내 켜 두면 넘습니다(30일 기준 vCPU 약 648,000초, 계산값). 무료로 쓰려면 0으로 줄어드는 설정을 쓰고 첫 요청이 느린 것을 받아들여야 합니다.
- **우리 API 컨테이너의 메모리 필요량은 아직 재지 못했습니다(확인 필요).** 코드를 들여온 뒤 로컬에서 `docker stats`로 api 컨테이너 사용량을 재서 위 표와 비교합니다.
- **웹(React)** 은 정적 파일이라 API와 같은 컨테이너에 넣거나 정적 호스팅에 따로 둘 수 있습니다. HF의 Static Space는 무료입니다.

## 4. DB 후보 (Postgres, pgvector 필수)

하루 질문 상한 카운트를 DB에 저장하므로, DB가 멈추면 URL이 열려 있어도 답이 나오지 않습니다.

| 항목 | Supabase (무료) | Neon (무료) | Azure PostgreSQL flexible server | Cloud SQL | Amazon RDS · Aurora |
|---|---|---|---|---|---|
| **무료 범위** | 프로젝트당 DB 500MB, 활성 프로젝트 2개. 기간 제한 없음 | 프로젝트당 저장 1GB, 월 100 CU시간. 기간 제한 없음, 카드 불필요 | 무료 계정 12개월: B1ms 750시간, 32GB. 가입에 카드 필요 | 상시 무료 없음. 체험 크레딧 300달러(90일) | 2025-07-15 이후 계정은 크레딧(가입 100달러 + 최대 100달러). 6개월 또는 크레딧 소진 시 종료 |
| **일시 중지** | **1주일 동안 활동이 적으면 일시 중지.** 하루 몇 건의 요청이 있으면 보통 피할 수 있음. 사전에 메일로 알림 | 5분 동안 요청이 없으면 컴퓨트가 멈춤(끌 수 없음). 프로젝트 자체는 멈추지 않음 | 자동 일시 중지 없음 | 자동 일시 중지 없음 | RDS는 없음. Aurora Serverless v2는 최소 0 ACU로 두면 자동 일시 중지 |
| **다시 켜기** | **대시보드에서 수동으로 재개** | 다음 쿼리에 자동, 수백 밀리초 | 해당 없음 | 해당 없음 | Aurora는 연결 시 자동, 약 15초 |
| **데이터 삭제** | 일시 중지 뒤 1년까지 복원 가능 | 한도에 닿아도 데이터는 지우지 않음 | 구독이 비활성화되면 서비스 중단 | 체험 종료 뒤 유예 기간이 지나면 삭제 | 종료 뒤 90일 보관 후 삭제 |
| **pgvector** | 지원. 대시보드 또는 `create extension vector` | 지원. `CREATE EXTENSION vector` | 지원. `azure.extensions` 허용 목록에 `vector` 추가 후 생성 | 지원 | 지원 |
| **연결** | 직접 연결은 IPv6. IPv4 환경은 풀러 사용(세션 5432, 트랜잭션 6543). 직접 연결 60개 | SSL 필수. 풀러 주소는 호스트에 `-pooler` 추가. 풀러에서는 세션 단위 `SET` 불가 | TLS 필수. 방화벽에 접속 IP 등록. B1ms는 사용자 연결 35개, 내장 풀러 없음 | 허용 네트워크 등록 또는 Cloud SQL 커넥터 사용 | PostgreSQL 15 이상은 SSL 기본 필수 |
| **근거 링크** | [가격](https://supabase.com/pricing), [무료 플랜 일시 중지](https://supabase.com/docs/guides/platform/free-plan-pausing), [pgvector](https://supabase.com/docs/guides/database/extensions/pgvector), [연결](https://supabase.com/docs/guides/database/connecting-to-postgres) | [플랜](https://neon.com/docs/introduction/plans), [0으로 줄이기](https://neon.com/docs/introduction/scale-to-zero), [pgvector](https://neon.com/docs/extensions/pgvector), [연결 풀](https://neon.com/docs/connect/connection-pooling) | [제품 안내](https://azure.microsoft.com/en-us/products/postgresql), [pgvector](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-use-pgvector), [제한](https://learn.microsoft.com/en-us/azure/postgresql/configure-maintain/concepts-limits) | [무료 제공 범위](https://docs.cloud.google.com/free/docs/free-cloud-features), [시작·중지](https://docs.cloud.google.com/sql/docs/postgres/start-stop-restart-instance), [확장](https://docs.cloud.google.com/sql/docs/postgres/extensions) | [RDS 무료](https://aws.amazon.com/rds/free/), [무료 플랜 FAQ](https://aws.amazon.com/free/free-tier-faqs/), [Aurora 자동 일시 중지](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html) |

- Supabase는 가입에 카드가 필요한지 확인하지 못했습니다(확인 필요).
- AWS 무료 크레딧의 만료 기간은 문서마다 6개월과 12개월로 다르게 적혀 있습니다(확인 필요).

## 5. 결정할 때 볼 것

결정은 Cloud Engineer와 AI Solutions Architect가 합니다. 아래는 표에서 바로 읽히는 내용입니다.

| 후보 | 표에서 읽히는 것 |
|---|---|
| HF Spaces (Docker) | 월 9달러가 들고, 외부 DB 연결과 데이터 보존이 모두 걸립니다 |
| AWS App Runner | 신규 고객을 받지 않습니다. 요청 상한도 120초로 가장 짧습니다 |
| GCP Cloud Run | 무료 제공량에 종료일이 없고 요청 상한이 가장 깁니다. 크레딧은 새로 받을 수 없어 무료 제공량 안에서만 써야 합니다. 결제 수단 등록이 필요하고, 0으로 줄이면 첫 요청이 느립니다 |
| Azure Container Apps | 무료 크레딧을 쓸 수 있는 유일한 클라우드입니다(1장). 키·모델과 같은 클라우드라 Key Vault 참조가 쉽습니다. 무료 체험 구독이 끝나면 멈추므로 종량제로 올릴지 정해야 합니다 |
| DB: Neon | 자동으로 다시 켜지고 카드가 필요 없습니다 |
| DB: Supabase | 1주일 방치하면 멈추고 수동으로 켜야 합니다. 주기적으로 요청을 보내는 장치가 필요합니다 |

### 남은 확인

| 항목 | 방법 |
|---|---|
| API 컨테이너 메모리 사용량 | 코드 들여온 뒤 `docker stats` |
| 한 답변에 걸리는 최대 시간 | 11-21 손 테스트에서 측정해 요청 상한과 비교 |
| 0으로 줄었을 때 첫 요청 지연 | 배포 리허설에서 측정 |
| Azure 구독을 종량제로 올릴지 | 올리면 지출 한도가 사라지므로 예산 알림이 먼저 필요 |
| 누가 카드를 등록할지 | Cloud Run과 Azure 모두 결제 수단이 필요 |
