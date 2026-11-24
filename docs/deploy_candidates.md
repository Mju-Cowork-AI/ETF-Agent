# 배포처 정리 (D9)

배포처를 Azure로 두고, API·웹·DB를 어디에 올릴지 정리한 문서입니다([decision_board.md](decision_board.md)).

- 2026-11-18에 각 회사의 공식 문서와 가격표를 보고 썼습니다. 실제 배포는 아직 해 보지 않았습니다.
- 공식 근거를 찾지 못한 칸은 "확인 필요"로 적었습니다.

## 1. 왜 Azure인가

| 클라우드 | 신규 가입 크레딧 | 기간 | 우리 팀 |
|---|---|---|---|
| Azure | 200달러 | 30일 | **지금 쓰는 중**(D2) |
| GCP | 300달러 | 90일 | Cloud Engineer가 이미 받아 씀 |
| AWS | 100달러(활동하면 최대 100달러 추가) | 6개월 또는 크레딧 소진 시 종료 | Cloud Engineer가 이미 받아 씀 |

- 세 곳 모두 신규 고객에게만 크레딧을 줍니다. **무료 크레딧을 쓸 수 있는 곳은 Azure 하나입니다.**
- 프로젝트가 약 1개월이라 30일짜리 크레딧으로 마감(11-30)까지 맞습니다.
- 모델 호출, 키 보관(Key Vault), 배포를 한 구독에서 처리합니다.

근거: [Azure 무료 계정](https://azure.microsoft.com/en-us/pricing/purchase-options/azure-account), [GCP 무료 제공 범위](https://docs.cloud.google.com/free/docs/free-cloud-features), [AWS 무료 플랜](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html)

### 제외한 후보

| 후보 | 제외 이유 | 근거 |
|---|---|---|
| HF Spaces (Docker) | Docker Space를 만들려면 유료 플랜(PRO, 월 9달러)이 필요. 나가는 요청이 80·443·8080 포트로 제한되어 외부 Postgres 연결이 막힘 | [Spaces 개요](https://huggingface.co/docs/hub/spaces-overview) |
| AWS App Runner | 2026-04-30부터 신규 고객을 받지 않음. 크레딧도 없음 | [중단 안내](https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html) |
| GCP Cloud Run | 크레딧을 새로 받을 수 없음. 모델·키와 다른 클라우드라 설정이 늘어남 | [무료 제공 범위](https://docs.cloud.google.com/free/docs/free-cloud-features) |

## 2. API: Azure Container Apps

| 항목 | 내용 | 근거 |
|---|---|---|
| 무료 제공량 | 매월 구독당 vCPU 180,000초, 메모리 360,000GiB초, 요청 200만 건 | [과금](https://learn.microsoft.com/en-us/azure/container-apps/billing) |
| 잠들기 | 기본 최소 복제본 0. 요청이 없으면 300초 뒤 0으로 줄고, 그동안 과금 없음. 다음 요청은 느림(지연 시간은 확인 필요) | [확장](https://learn.microsoft.com/en-us/azure/container-apps/scale-app) |
| 상시 켜 두기 | 최소 복제본을 1로 설정. 유휴 요금이 나오고 무료 제공량에서 차감 | [과금](https://learn.microsoft.com/en-us/azure/container-apps/billing) |
| 메모리 | 최소 0.25 vCPU / 0.5Gi, 0.25 vCPU / 0.5Gi 단위로 최대 4 vCPU / 8Gi | [컨테이너](https://learn.microsoft.com/en-us/azure/container-apps/containers) |
| 시크릿 | 앱 시크릿에 저장하거나 Key Vault 참조(관리 ID). 환경변수에서 `secretref:이름`으로 사용. 값을 바꾸면 재시작 또는 새 리비전 필요 | [시크릿](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets) |
| 요청 시간 상한 | **240초.** SSE 답변이 이보다 길면 끊김 | [ingress](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview) |
| 이미지·공개 URL | linux/amd64 이미지. 외부 ingress를 켜면 공개 주소(443)가 생기고, 로그인 기능은 선택 | [ingress](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview) |

- 0.25 vCPU / 0.5Gi 복제본 1개를 30일 내내 켜 두면 vCPU 약 648,000초로 무료 제공량을 넘습니다(계산값). 넘는 만큼은 크레딧에서 차감됩니다.
- 웹(React)은 정적 파일이라 API 컨테이너에 함께 넣을 수 있습니다. 따로 올리는 방법은 확인 필요입니다.

## 3. DB: Postgres (pgvector 필수)

하루 질문 상한 카운트를 DB에 저장하므로, DB가 멈추면 URL이 열려 있어도 답이 나오지 않습니다.

| 항목 | Azure PostgreSQL flexible server | Neon (무료) | Supabase (무료) |
|---|---|---|---|
| 비용 | 무료 계정 12개월: B1ms 750시간, 32GB. 넘으면 크레딧 차감 | 무료, 카드 불필요. 프로젝트당 1GB, 월 100 CU시간 | 무료. 프로젝트당 500MB, 활성 프로젝트 2개 |
| 일시 중지 | 자동 일시 중지 없음 | 5분간 요청이 없으면 컴퓨트가 멈춤 | **1주일간 활동이 적으면 일시 중지** |
| 다시 켜기 | 해당 없음 | 다음 쿼리에 자동(수백 밀리초) | **대시보드에서 수동** |
| pgvector | `azure.extensions`에 `vector` 추가 후 `CREATE EXTENSION vector` | `CREATE EXTENSION vector` | 대시보드 또는 `create extension vector` |
| 연결 | TLS 필수, 방화벽에 접속 IP 등록, 사용자 연결 35개 | SSL 필수, 풀러는 호스트에 `-pooler` 추가 | IPv4 환경은 풀러 사용(세션 5432) |
| 크레딧이 끝나면 | **구독과 함께 멈춤** | 계속 동작 | 계속 동작 |
| 근거 | [제품 안내](https://azure.microsoft.com/en-us/products/postgresql), [pgvector](https://learn.microsoft.com/en-us/azure/postgresql/extensions/how-to-use-pgvector), [제한](https://learn.microsoft.com/en-us/azure/postgresql/configure-maintain/concepts-limits) | [플랜](https://neon.com/docs/introduction/plans), [0으로 줄이기](https://neon.com/docs/introduction/scale-to-zero), [pgvector](https://neon.com/docs/extensions/pgvector) | [가격](https://supabase.com/pricing), [일시 중지](https://supabase.com/docs/guides/platform/free-plan-pausing), [pgvector](https://supabase.com/docs/guides/database/extensions/pgvector) |

- **Azure에 두면** 한 구독에서 관리하지만, 크레딧이 끝날 때 데이터까지 같이 멈춥니다.
- **Neon에 두면** 크레딧과 무관하게 남고 자동으로 다시 켜집니다. 다만 Container Apps에서 외부 DB로 붙는 구성이 됩니다.

## 4. 크레딧이 끝나면

| 시점 | 일어나는 일 | 근거 |
|---|---|---|
| 30일이 지나거나 크레딧을 다 씀 | 구독과 서비스가 비활성화됨. 배포한 URL과 Azure 모델 호출이 함께 멈춤 | [무료 계정 요금 피하기](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/avoid-charges-free-account) |
| 종량제로 올림 | 지출 한도가 사라지고 구독이 다시 켜짐. 무료가 아닌 자원은 과금됨 | [구독 올리기](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/upgrade-azure-subscription) |

- 비활성화된 자원이 언제 삭제되는지는 확인 필요입니다.
- 마감 뒤에도 URL을 열어 둬야 하면(D13), 종량제로 올릴지 미리 정해야 합니다. 올리면 지출 한도가 없어지므로 예산 알림이 먼저 필요합니다.

## 5. 남은 결정과 확인

| 항목 | 방법 |
|---|---|
| DB를 어디에 둘지 | 3장 표로 결정. 크레딧이 끝난 뒤에도 데이터가 필요한지가 기준 |
| 최소 복제본 0 또는 1 | 배포 리허설(11-21)에서 첫 요청 지연을 재고 결정 |
| API 컨테이너 메모리 사용량 | 코드를 들여온 뒤 `docker stats`로 측정 |
| 한 답변의 최대 소요 시간 | 11-21 손 테스트에서 재서 240초 상한과 비교 |
| 종량제로 올릴지 | 마감 뒤 URL 유지가 필요한지에 따라 결정 |
