# 채팅방 결정 안건

회의 없이 팀 채팅방에서 정합니다. 결과는 [decisions.md](decisions.md)에 기록합니다.

## 결정 방식

1. **주도 역할**이 기한 전에 채팅방에 **추천안과 이유(1~2줄)**를 올립니다.
2. **함께 정할 역할**이 확인합니다. 의견이 다르면 같은 스레드에 답합니다.
3. **기한까지 반대가 없으면 확정**합니다.
4. **AI Solutions Architect**가 decisions.md에 기록합니다.

- 주도 역할은 결정으로 일이 생기는 역할, 함께 정할 역할은 영향을 받는 역할입니다.
- 이름은 쓰지 않고 역할로만 적습니다.

## 기한 한눈에 보기

| 기한 | 안건 |
|---|---|
| ~~11-18(수) 18:00~~ | **결정됨:** 코드 들여오기, D9, D17, D16, D12, Azure 키 관리자, 범위 조정, D4(5개), D5(제외)<br>각자 빠지는 날은 11-22에 받음 |
| **11-19(목) 12:00** | **결정됨:** D7(사실 비교표만), D8(같은 분기 이내). 반대 없음 / D6(용어집 + 투자설명서), 모듈 간 입출력 형식(AI Engineer 초안 확정), 모델 배치(생성 `gpt-6-sol`, 계획·검증 `gpt-6-luna`) |
| 11-20(금) PR 리뷰 | **결정됨:** 공개 URL 설정(익명 접근 + 운영 토큰), 익명 토큰 30일, D13 세는 방식(서비스 전체 하루 KST, 리허설 임시값 200건), 가드 사유 id 범주 단위. PR #14·#15·#17 리뷰에서 정함([decisions.md](decisions.md)). D9 웹 배포처는 Cloudflare Pages로 정함(리허설 배포, Cloud Engineer)<br>**채팅방(Cloud Engineer 제안·반대 없음):** D9 수정 — 웹 Cloudflare Pages(Cloud Engineer 개인 계정), DB 지역 일본 동부(koreacentral B1ms 생성 거부, SKU 그대로) |
| ~~11-21(토) 12:00~~ | **결정됨:** 범위 조정 2차(약 −24h, AI Engineer·Data Scientist·Cloud Engineer 동의), 계획 JSON `refuse` 범위 확대(AI Engineer 제안), 순자산 상품별 기준일 표시, 11-21 리허설 순서(Cloud Engineer) |
| ~~11-22(일)~~ | **결정됨(팀원 동의):** 공수 실측(78h 사용, 남은 일 약 65h), 범위 조정 3차(약 −11.5h → 약 53.5h), 빠지는 날과 일정 조정, D6 변경(투자설명서 색인 뺌, 개념 문서 13개), DART 키·수집 코드 삭제(#39), 하루 상한 200건 유지, 시세 질문 처리(#35·#41), 문서만 바꾸는 PR은 리뷰 없이 머지, 채점 기준 8장 정리 |
| ~~11-24(월) 18:00~~ | **결정됨(반대 없음):** D3 로컬 LLM 실측(포함, 계획 단계만, 배포는 Azure 유지), 배포·릴리스 계정 이중화, 멘토 피드백 반영(발표일 상한 조정, 실행 메모, 데이터 기준일 한 줄, RFP 범위 표)<br>**운영진 공지(11-24):** 제출물(GitHub 링크·PPT·최종 URL, 팀장 취합), SA PO 업무 겸임, 역할별 마지막 점검, 발표 형식(PPT 제출 시점은 확인 중) |
| ~~11-29(일)~~ | **결정됨(11-28, Cloud Engineer 제안, AI Solutions Architect 동의):** D10 시연 질문 캐시 — 실시간 + 발표 직전 워밍업(전날 캐시 안 함) |

## 1. 공유: D1 FastAPI 기반 (결정됨)

- FastAPI 기반(Python + FastAPI + Postgres(pgvector) + React + Docker + LangGraph)으로 정했습니다. 근거는 남은 기간과 기능 완성도입니다. Streamlit 기반은 옮겨 올 강점의 출처로만 씁니다.
- 위험: 공수 대비 용량 여유가 작음(범위 조정 2차 후 약 194.5h 추정. 11-22 실측으로 남은 일 약 53.5h, 남은 7일 용량으로 충분), 배포 복잡도(API·웹·DB 따로 배포, 로그인 없는 접근)
- 대응: 11-21 배포 리허설, 11-22 공수 실측(완료). 옮겨 온 코드는 원 코드 작성자가 리뷰합니다.
- **올리는 역할:** AI Solutions Architect / **확인:** 전원(이견이 있으면 11-18 18:00까지 채팅방에)

## 2. 안건

이유 칸은 "주도: 일이 생김 / 함께: 영향받음"입니다.

### 11-18(수) 18:00까지

**결과(11-18 기록).** 자세한 내용은 [decisions.md](decisions.md) 결정됨 표에 있습니다. 아래 안건 표는 결정할 때 쓴 자료라 그대로 둡니다.

| 안건 | 상태 | 결과 |
|---|---|---|
| 코드 들여오기 | 결정됨 | FastAPI 구조 그대로, git 이력 살림. Cloud Engineer Draft PR, AI Engineer 리뷰(CI 통과 + 로컬 질문 1개) |
| D9 배포처 | 결정됨 | API Azure Container Apps(koreacentral, 최소 복제본 1), DB Azure PostgreSQL B1ms. 웹은 11-20 리허설 배포에서 Cloudflare Pages로 정함(무료). **11-20 수정:** DB 지역은 일본 동부(koreacentral B1ms 생성 거부, SKU 그대로) |
| D17 평가셋 규모 | 결정됨 | 60문항(Cloud Engineer·Data Scientist 동의) |
| D16 멀티턴 | 결정됨 | 포함 |
| D12 수준별 답변 | 결정됨 | 사용자 선택 3단계, 기본값 "입문", 버튼은 채팅 화면으로 이동 |
| Azure 키 관리자 | 결정됨 | Cloud Engineer, Key Vault로만 전달 |
| 범위 조정 | 결정됨 | 재계획 루프·계획 JSON 유지, 약 −18h 축소. **11-21 2차:** 약 −24h 더 축소(약 194.5h, 아래 11-21 결과). **11-22 3차:** 실측 뒤 약 −11.5h(남은 일 약 53.5h, 아래 11-22 결과) |
| D4 ETF 개수 | 결정됨 | 5개: TIGER 미국나스닥100(133690), KODEX 미국나스닥100(379810, 옛 이름 KODEX 미국나스닥100TR), ACE 미국나스닥100(367380, 자사), KODEX 200(069500), TIGER 미국배당다우존스(458730) |
| D5 공시 조회 | 결정됨 | 제외. 샘플 공시 끄기(Data Scientist, 1h) |
| 각자 빠지는 날 | 받음(11-22) | AI Engineer 11-28~29, Data Scientist 11-27 10~18시 |

같은 날 평가 실행 운영(AI Engineer, 첫 실행은 Cloud Engineer가 함께 확인)과 승인 필수 PR 4개 영역(팀 동의, 설정은 Cloud Engineer)도 정했습니다.

| 안건 | 주도 역할 | 함께 정할 역할 | 이유 | 필요한 정보 | 선택지 | 기한 |
|---|---|---|---|---|---|---|
| 각자 빠지는 날(용량 확인) | AI Solutions Architect | 전원 | 용량 재계산과 일정 조정 일이 생김 / 모든 역할의 작업량이 영향받음 | 기본 용량 4명 × 10일 × 하루 약 5.07~5.73h = 약 203~229h, 공수 약 232h([plan.md](plan.md) 6-1) | 각자 주말(11-21·22)·평일에 빠지는 날을 채팅방에 적음. 기본값과 크게 다르면 용량을 고침 | 11-18 18:00 |
| 코드 들여오기 | Cloud Engineer(저장소 관리) | AI Solutions Architect, AI Engineer | 저장소 구조·CI 설정을 바꾸는 일이 생김 / 코드 구조·이력과 아키텍처·일정이 영향받음 | 저장소 CI·Makefile은 `app agent data pipeline eval` 폴더를 검사(Python은 3.14로 맞춤). FastAPI 기반 코드는 자체 Makefile·Docker Compose·웹 린트가 있음 → 어느 쪽이든 한쪽 설정을 바꿔야 함. 경로 변경 공수는 확인 필요 | 구조: 저장소 뼈대(`app/`, `agent/`, `pipeline/`) / FastAPI 기반 코드 구조(`apps/api/` 등)<br>이력: 기존 git 이력 살림 / 한 번에 복사 | 11-18 18:00 |
| D9 배포처 | Cloud Engineer | AI Solutions Architect | 배포 작업이 생김 / 일정·비용·제출요건(URL)이 영향받음 | [배포처 정리](deploy_candidates.md)(CE). 11-21 배포 리허설 전에 정해야 함<br>**요약** ① 무료 크레딧은 Azure만 쓸 수 있어 API는 Azure Container Apps가 남음(무료 제공량 있음, 유휴 시 0으로 줄어 첫 요청이 느림, 요청 시간 상한 240초). HF Spaces·App Runner·Cloud Run은 제외 이유가 정리됨<br>② DB: Azure PostgreSQL(크레딧이 끝나면 함께 멈춤) / Neon(무료, 유휴 시 멈췄다가 자동 재개) / Supabase(1주 미사용 시 수동 재개)<br>③ 웹은 API 컨테이너에 함께 넣을 수 있음. 최소 복제본 0·1과 메모리는 11-21 리허설에서 측정 | HF Spaces(Docker) / AWS App Runner / GCP Cloud Run / Azure Container Apps. API·웹·DB를 각각 어디에 둘지. Streamlit Cloud는 FastAPI·React를 올릴 수 없어 뺌(확인 필요) | 11-18 18:00 |
| D17 평가셋 규모 | AI Solutions Architect | Data Scientist(정답값), AI Engineer(의도 라벨), Cloud Engineer(실행·비용) | 레드팀·정상 문항과 채점 기준 작업이 생김 / 정답값·라벨·실행 비용이 문항 수에 따라 늘어남 | 공수가 이미 용량을 약 3~29h 넘음. 140문항이면 약 +40h·크레딧 약 2.3배 | 60문항 / 140문항 | 11-18 18:00 |
| D5 공시 조회 | Data Scientist | AI Engineer | 공시 실데이터 연결 작업이 생김 / 공시 도구와 답변 흐름이 영향받음 | RFP 공시 항목. 포함 시 실데이터 연결 약 8h(여유 시간으로만), 제외 시 샘플 공시 끄기 1h | 제외 / 포함 | 11-18 18:00 |
| D4 ETF 개수 | Data Scientist | AI Solutions Architect | 수집·적재 작업이 생김 / 범위·일정과 평가 문항이 영향받음 | 현재 5개(나스닥100 비교군 3개 + 국내 대표 + 월배당). 10개면 약 +12h(여유 시간으로만) | 5개 / 10개 안팎 | 11-18 18:00 |
| D16 멀티턴 | AI Engineer | AI Solutions Architect | 멀티턴 유지·끄기 작업이 생김 / RFP 해석과 평가 문항이 영향받음 | 이미 있어 0h. RFP "자연어 질문의 문맥" 해석 | 포함 / 제외 | 11-18 18:00 |
| D12 수준별 답변 | AI Engineer | AI Solutions Architect | 프롬프트·답변 방식 작업이 생김 / RFP 해석과 평가 기준이 영향받음 | 이미 있어 0h. RFP "다양한 지식수준" | 사용자 선택 3단계 / 자동 2단계 | 11-18 18:00 |
| Azure 키 관리자 지정 | Cloud Engineer | 전원 | 11-19 Azure 모델 연결 전에 키 전달 방식이 정해져야 함 | Key Vault·GitHub Secrets 등록 절차(`scripts/set-secret.sh`), 팀원 `.env` 전달 방식 | 관리자 1명(역할로 지정)과 키 전달 방식 | 11-18 18:00 |
| 범위 조정 | AI Solutions Architect | 전원 | 범위·일정을 다시 짜는 일이 생김 / 모든 역할의 작업이 줄거나 바뀜 | 용량 약 203~229h(10일) < 공수 약 232h → **약 3~29h 초과**. 아래 "뺄 것 후보" 표 | 후보 중 무엇을 뺄지 / 빼지 않고 11-22 공수 실측 뒤 다시 정함 | 11-18 18:00 |

#### 범위 조정: 뺄 것 후보 (공수가 큰 순서, 결정 당시 자료)

**결과:** 재계획 루프·계획 JSON은 유지. 프롬프트 수정 축소(−4h), 문서 검색 튜닝 축소(−4h), 사용자 테스트 10명 → 5명(약 −4h), 앱 토큰 집계 대신 Azure 포털 사용량(약 −6h). 합계 약 −18h.

공수는 공통 기능 집합 공수표 기준 추정입니다. 초과분은 약 3~29h입니다.

| 항목 | 줄어드는 공수 | 빠지면 생기는 영향 |
|---|---|---|
| 재계획 루프(N=1) | 약 12h | **에이전틱 구조:** 결과가 부족할 때 다시 계획하는 단계가 빠지고 "계획 → 병렬 도구 → 검증·재작성"만 남음. D11 결정을 다시 정해야 함. RFP·제출요건: 직접 영향 없음 |
| LLM 계획 JSON(수집 도구·인자 결정) | 약 10h(재계획 루프와 함께 빼면 약 22h) | **에이전틱 구조:** LLM이 도구와 인자를 고르는 핵심이 빠지고 기존 의도 분류 흐름으로 돌아감. 재계획 루프는 이것을 전제로 하므로 함께 빠짐 |
| 사용자 테스트(모집·진행·설문) | 약 8h | 기획의 필수 범위(평가)에서 빠짐. 실제 사용자 반응 근거가 없어짐. 제출요건: 영향 없음 |
| 프롬프트 수정 축소(8h → 4h) | 약 4h | 개발용 평가 결과를 반영하는 횟수가 줄어 답변 품질 개선 여지가 작아짐 |
| 실제 문서 검색 튜닝 축소(8h → 4h) | 약 4h | RFP의 개념·용어 설명 답변 품질이 낮아질 수 있음 |

- 개인정보 차단, 숫자 대조, 실데이터, 배포·로그인 없는 접근·하루 질문 상한, README는 안전장치나 제출요건이라 후보에 넣지 않았습니다.

### 11-19(목) 12:00까지

**결과(11-19 기록).** D7 사실 비교표만, D8 같은 분기 이내로 결정됨(기한까지 반대 없음). D6은 용어집 + 투자설명서로 결정됨(기존 개념 문서를 고쳐 씀, [glossary_check.md](glossary_check.md)). 모듈 간 입출력 형식은 AI Engineer 초안으로 확정됨([interface.md](interface.md)). 같은 날 모델 배치(생성 `gpt-6-sol`, 계획·검증 `gpt-6-luna`)도 정함. 자세한 내용은 [decisions.md](decisions.md) 결정됨 표에 있습니다.

| 안건 | 주도 역할 | 함께 정할 역할 | 이유 | 필요한 정보 | 선택지 | 기한 |
|---|---|---|---|---|---|---|
| D7 타사 비교 범위 | AI Solutions Architect | AI Engineer | 비교·순위 표현 가드 기준 작업이 생김 / 비교 의도와 프롬프트가 영향받음 | 광고 규제 관련 고객사 확인 사항. 자사(ACE) 상품은 1개(D4) | 사실 비교표만 / 자사 상품만<br>**결정됨: 사실 비교표만.** 자사만이면 비교 기능이 사라짐. 평가 표현 금지, 순위는 기준·기준일 명시 | 11-19 12:00(결정됨) |
| D6 FAQ/VOC 대체 자료 | Data Scientist | AI Solutions Architect | 용어집 작성·색인 작업이 생김 / 개념 질문 품질과 평가 문항이 영향받음 | 문서 검색 품질, 용어집 작성 시간 | 용어집 + 투자설명서 / 투자설명서만<br>**11-22 변경: 투자설명서 색인 뺌, 개념 문서 13개로 마무리**(아래 11-22 결과)<br>**결정됨(11-19): 용어집 + 투자설명서.** 기존 개념 문서 13개를 고쳐 쓰고, sample_products.md·pension_isa.md는 적재에서 제외, fees_tax.md 세금 절 삭제, TR ETF 문서 새로 작성(Data Scientist, 약 4.5~5h, [glossary_check.md](glossary_check.md)) | 11-19 12:00(결정됨) |
| D8 실부담비용 기준일 범위 | AI Solutions Architect | Data Scientist | 주의 문구·가드 규칙 작업이 생김 / 기준일 데이터 수집·검증이 영향받음 | ETF 5개의 실부담비용 기준일: 모두 2026-10-30 | 같은 분기 이내 / 1년 이내<br>**결정됨: 같은 분기 이내.** 5개 기준일이 같아 지금은 주의 문구가 붙지 않음 | 11-19 12:00(결정됨) |
| 모듈 간 입출력 형식(계획 JSON·응답 형식) | AI Engineer | AI Solutions Architect, Data Scientist | 개인정보 차단·숫자 대조·데이터 파이프라인 옮기기가 같은 형식을 써야 함 | 계획 JSON·응답 형식 초안(AIE), 옮겨 올 코드의 입출력 | 초안 확정 / 수정 후 확정<br>**결정됨: 초안 확정.** 형식과 규칙은 [interface.md](interface.md) | 11-19 12:00(결정됨) |

### 11-21(토) 12:00까지

**결과(11-21 기록).** 범위 조정 2차가 확정됐습니다(AI Engineer·Data Scientist·Cloud Engineer 동의). 같은 날 계획 JSON `refuse` 범위 확대, 순자산 기준일 표시, 11-21 리허설 순서도 정했습니다. 자세한 내용은 [decisions.md](decisions.md) 결정됨 표에 있습니다.

| 항목 | 담당 | 바뀐 것 | 줄어드는 공수 |
|---|---|---|---|
| 실데이터 파이프라인 | Data Scientist | 공공데이터 API 자동 수집(가격·NAV)·KRX 구성종목 뺌, ETF 5개 수동 CSV 검증·적재, 순자산은 기준일과 함께 | 약 12h |
| 문서 검색 튜닝 | Data Scientist | 기본 설정, 개념 질문 4개만 손 확인 | 4h |
| 개발용 평가 | AI Engineer | 2회 → 1회, 프롬프트 수정 4h → 2h | 약 4h |
| 사용자 테스트 | Cloud Engineer | 5명 → 최소 3명, 더 구할 수 있으면 추가, 입문 수준 1명 필수. 설문은 AI Solutions Architect가 줄임 | 약 2h |
| 설명형 사람 채점 | Data Scientist, AI Solutions Architect | 2명 교차 → 1명 채점 + 1명 일부 확인 | 약 2h |

- 합계 약 −24h: 공수 약 218.5h → **약 194.5h**, 용량(약 203~229h) 대비 약 +8.5~+34.5h 여유. 11-22 실측 뒤 다시 검토합니다.
- 숫자 대조, 계획 JSON, 재계획 루프, 가드, 배포, 시험용 평가는 그대로입니다.

### 11-22(일) 채팅방

**결과(11-22 기록).** 모두 팀원 동의를 받았습니다. 자세한 내용은 [decisions.md](decisions.md) 결정됨 표에 있습니다.

**공수 실측**
- 지금까지 쓴 시간: AI Engineer 16h, Data Scientist 19h, Cloud Engineer 18h, AI Solutions Architect 25h(합계 78h)
- 남은 일: 약 65h(AI Engineer 20.5h + 평가 실행기 5h, Data Scientist 11.5h, Cloud Engineer 13h, AI Solutions Architect 약 15h)
- 하루 평균 약 3~4h라 남은 7일 용량으로 충분합니다. 194.5h 추정은 온보딩 등을 넉넉히 잡은 값이었습니다.

**범위 조정 3차(약 −11.5h → 남은 일 약 53.5h)**

| 항목 | 담당 | 바뀐 것 | 줄어드는 공수 |
|---|---|---|---|
| 재계획 루프 | AI Engineer | 결과 0건·항목 빠짐 2개만 재계획. ETF 이름 애매·문서 점수 낮음은 바로 고정 문구 | 5h → 3h(−2h) |
| 평가 실행기 | AI Engineer | 수치 규칙만([grading.md](grading.md) 8장 3번). 레드팀 자동 검사·근거 인용률(8·9번)은 채점 때 손으로, 9번은 "출처 부착률"로 보고 | 5h → 2h(−3h) |
| 정답값 DB 대조 | Data Scientist | 스크립트로 | 2h → 0.5h(−1.5h) |
| 발표 데이터 | Data Scientist | 평가 결과 표 재사용 | 2h → 1h(−1h) |
| 시연 | Cloud Engineer | 라이브 + 백업 캡처·화면 녹화 | 3h → 1h(−2h) |
| gen11 조사 | — | 조사 안 함(11-21 리허설 표 답변 `judge:ungrounded`) | −1h |
| 사용자 테스트 설문 | Cloud Engineer, AI Solutions Architect | 12문항(#45), 구글 폼은 11-26까지 | Cloud Engineer 4h → 3.5h(−0.5h), AI Solutions Architect −0.5h |
| 익명 발급 제한(이슈 #18) | — | 넣지 않음. 하루 상한은 질문 수만 막고 익명 토큰 발급 자체는 막지 않음 | 0h(남은 일 목록에 없던 항목) |
| 발표 자료 | AI Solutions Architect | 기획서·README·평가 표 재사용 | −11.5h에 넣지 않음(SA 남은 일 15h에 이미 반영) |

**일정 조정**
- 빠지는 날: AI Engineer 11-28~29, Data Scientist 11-27 10~18시
- 사용자 테스트 11-27 오전 진행·오후 버그 수정, AI Engineer가 11-27에 손볼 곳 메모, Data Scientist 사용자 테스트 지원은 11-28
- 11-28 제출, 28일 밤 큰 버그는 29일까지 예비. 발표 리허설 11-30 오전
- 재계획 루프는 11-24까지 머지가 가장 중요

**그 밖**
- D6 변경: 투자설명서 색인 뺌(평가 정답이 DB·개념 문서에서 나옴, PDF 표 쪼개기·보수 숫자 불일치 위험, 배포 적재 방법 필요). 개념 문서 13개로 마무리
- DART 키·수집 코드 삭제(#39), `DATA_GO_KR` 키는 원래 없음
- 하루 상한 200건 유지(리허설 실측)
- 시세 미제공 안내(#35·#41): 특정 ETF 시세 질문은 `etf_info`
- 문서만 바꾸는 PR은 리뷰 없이 머지(승인 필수 4영역은 그대로)
- 채점 기준([grading.md](grading.md) 8장): 3·7번(실행기도 숫자 대조 규칙, 답변 수준 입문 고정) 정해짐, 8·9번 손 채점, 1·2·4·10·11번 동의

### 11-24(월) 18:00 채팅방과 운영진 공지

**결과(11-24 기록).** 1~3은 채팅방에서 18시까지 반대 없이 확정, 4는 운영진 공지입니다. 자세한 내용은 [decisions.md](decisions.md) 결정됨 표에 있습니다.

1. **D3 로컬 LLM 실측: 포함(계획 단계만), 배포는 Azure 유지.** 코드 변경 없이 환경변수만 바꿔 Ollama 모델로 계획(의도 분류) 단계를 교체, 개발용 일반 20문항: 키워드 규칙만 15/20, `exaone3.5:2.4b` 15/20(중앙값 1.8초), `gemma3:12b` 18/20(중앙값 5.8초). 소형은 규칙과 정확도가 같고, 12b는 계획 한 번에 약 6초라 응답 시간 목표에 안 맞음. Azure 계획 모델과 같은 20문항 비교는 개발용 평가의 의도 정확도로 채움([local_llm.md](local_llm.md))
2. **배포·릴리스:** `dev` → `main` 릴리스 PR 머지 시 API·웹 자동 배포(v1.0·v1.1 확인), `dev` 머지만으로는 배포 안 됨. 평소 Cloud Engineer, 부재 시 팀원 누구나 [git-flow.md](git-flow.md) "릴리스" 절차. 코드 변경 없는 재배포는 Actions → deploy → Run workflow(`main`). Cloudflare 계정 초대 안 함, `rg-etf-agent` 권한은 AI Solutions Architect(Key Vault 키 값 열람 불가), 다른 팀원은 요청 시. 11-28 오전 Data Scientist가 한 번 따라 해 봄
3. **멘토 피드백:** 11-30만 하루 상한을 올렸다가 복구(Cloud Engineer, D10도 이때), AI Engineer 실행 메모(11-27 전), Data Scientist 데이터 기준일·갱신 주기 한 줄, AI Solutions Architect RFP 범위 표([rfp_scope.md](rfp_scope.md))
4. **운영진 공지:** 제출물(GitHub 링크·PPT·최종 URL, 팀장 조은서 취합·제출, PPT 제출 시점 확인 중), AI Solutions Architect PO 업무 겸임(PPT 주도, 사용자 인수 테스트 11-27), 역할별 마지막 점검, 발표 형식(슬라이드 초안 11-26 → 통합 11-27 → 완성 11-28). SA 발표 자료 2.5h → PPT 약 6h

### 나중에 정하는 안건

| 안건 | 주도 역할 | 함께 정할 역할 | 이유 | 필요한 정보 | 선택지 | 기한 |
|---|---|---|---|---|---|---|
| D3 로컬 LLM 실측 | AI Engineer | Cloud Engineer | 로컬 모델 연결·실측 작업이 생김 / 실행 환경·자원이 영향받음 | 11-25 MVP 뒤 남은 여유. 포함 시 약 4h | 제외 / 포함<br>**결정됨(11-24): 포함(계획 단계만), 배포는 Azure 유지** | 11-25(수, 11-24 결정) |
| D10 시연 질문 캐시 | Cloud Engineer | AI Solutions Architect | 캐시 준비·시연 운영 작업이 생김 / 발표 진행과 설명이 영향받음 | 시연 질문 목록, 배포 안정성 | 캐시 / 실시간<br>**결정됨(11-28): 실시간 + 발표 직전 워밍업(전날 캐시 안 함)** | 11-29(일, 11-28 결정) |

## 3. 확정 뒤 바로 할 일

- [x] decisions.md에 결정 기록(AI Solutions Architect). 11-18·11-19·11-20·11-21·11-22·11-24 기록
- [ ] 작업 카드 만들기: 담당자 1명 = 브랜치 1개(전원). [roles.md](roles.md) 3장의 (a)·(b)·(c)를 먼저 만듭니다
- [x] README 팀원별 역할에 이름 채우기(AI Solutions Architect, 제출 전)
- [x] 코드 들여오기(Cloud Engineer, #6)
- [x] `.env.example` 변수 이름을 들여온 코드에 맞추기(Cloud Engineer, #6)
- [x] 웹 배포 방식 정하고 D9 고치기(Cloud Engineer가 Cloudflare Pages로 정함, D9 수정 11-20)
- [x] `azure_models.md` 6장 추천표를 모델 배치 결정에 맞게 갱신(Cloud Engineer, 11-24. 결정된 배치는 5장에 넣음)
- [x] 익명 발급 반복 호출 제한 결정(이슈 #18): 넣지 않음(11-22)
- [x] 웹 배포 계정에 팀원 1명 추가 또는 재배포 방법 문서화(Cloud Engineer, D9). 계정 초대 대신 `main` 머지 시 자동 배포(#43)와 [git-flow.md](git-flow.md) "릴리스" 절차로 정함(11-24)
- [x] API(한국)·DB(일본) 응답 시간 측정, p90 10초 목표(Cloud Engineer, 11-21 리허설). 12문항 p90 6.25초, 최대 9.6초([infra/azure/README.md](../infra/azure/README.md)). 시험용 평가(11-26)에서 다시 잼
- [x] 11-21 리허설: 시드 다음 `python -m jobs.load_real` → API 재시작 → 손 테스트 12문항(캐시 끔), 단계별 시간을 트레이스로 확인(Cloud Engineer)
- [ ] 계획 JSON `refuse`에 범위 밖 부분(공시·뉴스 등) 반영(AI Engineer, 11-23 계획 JSON 도입 때)
- [x] 비교·순위 답변에 상품별 순자산 기준일 표시(담당은 채팅방에서 정함). 비교표에 순자산 기준일 행이 나옴(11-25 배포 URL에서 확인)
- [x] 사용자 테스트 설문을 12문항으로 줄이기(AI Solutions Architect, 11-22 결정, #45)
- [x] 사용자 테스트 구글 폼 만들기(Cloud Engineer, 11-26까지). 11-27 사용자 테스트에 씀
- [x] 재계획 루프 머지(AI Engineer, #47)
- [x] D3 로컬 LLM 실측(계획 단계만, #53)
- [ ] PPT 제출 시점(11-28 마감에 같이 내는지) 운영진 확인(AI Solutions Architect)
- [x] 11-28 오전 Data Scientist 릴리스 따라 하기(`v1.3.1`, #77)
- [x] D10 결정(11-28): 실시간 + 발표 직전 워밍업(전날 캐시 안 함)
- [ ] 11-30 하루 상한 올림(1,000건)·워밍업·복구(200건)(Cloud Engineer, 절차는 [infra/azure/README.md](../infra/azure/README.md) "11-30 발표 당일 절차", #79)
