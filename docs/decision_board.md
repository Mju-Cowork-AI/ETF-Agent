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
| **11-18(수) 18:00** | 코드 들여오기, D9, D17, D5, D4, D16, D12, Azure 키 관리자, 각자 빠지는 날(용량 확인) |
| **11-19(목) 12:00** | D7, D6, D8, 모듈 간 입출력 형식 |
| 11-25(수) | D3 |
| 11-29(일) | D10 |

## 1. 공유: D1 FastAPI 기반 (결정됨)

- FastAPI 기반(Python + FastAPI + Postgres(pgvector) + React + Docker + LangGraph)으로 정했습니다. 근거는 남은 기간과 기능 완성도입니다. Streamlit 기반은 옮겨 올 강점의 출처로만 씁니다.
- 위험: 여유가 작음(약 11~43h), 배포 복잡도(API·웹·DB 따로 배포, 로그인 없는 접근)
- 대응: 11-21 배포 리허설, 11-22 공수 실측. 옮겨 온 코드는 원 코드 작성자가 리뷰합니다.
- **올리는 역할:** AI Solutions Architect / **확인:** 전원(이견이 있으면 11-18 18:00까지 채팅방에)

## 2. 안건

이유 칸은 "주도: 일이 생김 / 함께: 영향받음"입니다.

### 11-18(수) 18:00까지

| 안건 | 주도 역할 | 함께 정할 역할 | 이유 | 필요한 정보 | 선택지 | 기한 |
|---|---|---|---|---|---|---|
| 각자 빠지는 날(용량 확인) | AI Solutions Architect | 전원 | 용량 재계산과 일정 조정 일이 생김 / 모든 역할의 작업량이 영향받음 | 기본 용량 4명 × 12일 × 하루 약 5.07~5.73h = 약 243~275h, 공수 약 232h([plan.md](plan.md) 6-1) | 각자 주말(11-21·22, 11-28·29)·평일에 빠지는 날을 채팅방에 적음. 기본값과 크게 다르면 용량을 고침 | 11-18 18:00 |
| 코드 들여오기 | Cloud Engineer(저장소 관리) | AI Solutions Architect, AI Engineer | 저장소 구조·CI 설정을 바꾸는 일이 생김 / 코드 구조·이력과 아키텍처·일정이 영향받음 | 저장소 CI·Makefile은 `app agent data pipeline eval` 폴더를 검사(Python은 3.14로 맞춤). FastAPI 기반 코드는 자체 Makefile·Docker Compose·웹 린트가 있음 → 어느 쪽이든 한쪽 설정을 바꿔야 함. 경로 변경 공수는 확인 필요 | 구조: 저장소 뼈대(`app/`, `agent/`, `pipeline/`) / FastAPI 기반 코드 구조(`apps/api/` 등)<br>이력: 기존 git 이력 살림 / 한 번에 복사 | 11-18 18:00 |
| D9 배포처 | Cloud Engineer | AI Solutions Architect | 배포 작업이 생김 / 일정·비용·제출요건(URL)이 영향받음 | [배포처 후보 조건표](deploy_candidates.md)(CE). 11-21 배포 리허설 전에 정해야 함 | HF Spaces(Docker) / AWS App Runner / GCP Cloud Run / Azure Container Apps. API·웹·DB를 각각 어디에 둘지. Streamlit Cloud는 FastAPI·React를 올릴 수 없어 뺌(확인 필요) | 11-18 18:00 |
| D17 평가셋 규모 | AI Solutions Architect | Data Scientist(정답값), AI Engineer(의도 라벨), Cloud Engineer(실행·비용) | 레드팀·정상 문항과 채점 기준 작업이 생김 / 정답값·라벨·실행 비용이 문항 수에 따라 늘어남 | 남은 여유 약 11~43h, 140문항이면 약 +40h·크레딧 약 2.3배 | 60문항 / 140문항 | 11-18 18:00 |
| D5 공시 조회 | Data Scientist | AI Engineer | 공시 실데이터 연결 작업이 생김 / 공시 도구와 답변 흐름이 영향받음 | RFP 공시 항목. 포함 시 실데이터 연결 약 8h(여유 시간으로만), 제외 시 샘플 공시 끄기 1h | 제외 / 포함 | 11-18 18:00 |
| D4 ETF 개수 | Data Scientist | AI Solutions Architect | 수집·적재 작업이 생김 / 범위·일정과 평가 문항이 영향받음 | 현재 5개(나스닥100 비교군 3개 + 국내 대표 + 월배당). 10개면 약 +12h(여유 시간으로만) | 5개 / 10개 안팎 | 11-18 18:00 |
| D16 멀티턴 | AI Engineer | AI Solutions Architect | 멀티턴 유지·끄기 작업이 생김 / RFP 해석과 평가 문항이 영향받음 | 이미 있어 0h. RFP "자연어 질문의 문맥" 해석 | 포함 / 제외 | 11-18 18:00 |
| D12 수준별 답변 | AI Engineer | AI Solutions Architect | 프롬프트·답변 방식 작업이 생김 / RFP 해석과 평가 기준이 영향받음 | 이미 있어 0h. RFP "다양한 지식수준" | 사용자 선택 3단계 / 자동 2단계 | 11-18 18:00 |
| Azure 키 관리자 지정 | Cloud Engineer | 전원 | 11-19 Azure 모델 연결 전에 키 전달 방식이 정해져야 함 | Key Vault·GitHub Secrets 등록 절차(`scripts/set-secret.sh`), 팀원 `.env` 전달 방식 | 관리자 1명(역할로 지정)과 키 전달 방식 | 11-18 18:00 |

### 11-19(목) 12:00까지

| 안건 | 주도 역할 | 함께 정할 역할 | 이유 | 필요한 정보 | 선택지 | 기한 |
|---|---|---|---|---|---|---|
| D7 타사 비교 범위 | AI Solutions Architect | AI Engineer | 비교·순위 표현 가드 기준 작업이 생김 / 비교 의도와 프롬프트가 영향받음 | 광고 규제 관련 고객사 확인 사항 | 사실 비교표만 / 자사 상품만 | 11-19 12:00 |
| D6 FAQ/VOC 대체 자료 | Data Scientist | AI Solutions Architect | 용어집 작성·색인 작업이 생김 / 개념 질문 품질과 평가 문항이 영향받음 | 문서 검색 품질, 용어집 작성 시간 | 용어집 + 투자설명서 / 투자설명서만 | 11-19 12:00 |
| D8 실부담비용 기준일 범위 | AI Solutions Architect | Data Scientist | 주의 문구·가드 규칙 작업이 생김 / 기준일 데이터 수집·검증이 영향받음 | ETF 5개의 실부담비용 기준일 | 같은 분기 이내 / 1년 이내 | 11-19 12:00 |
| 모듈 간 입출력 형식(계획 JSON·응답 형식) | AI Engineer | AI Solutions Architect, Data Scientist | 개인정보 차단·숫자 대조·데이터 파이프라인 옮기기가 같은 형식을 써야 함 | 계획 JSON·응답 형식 초안(AIE), 옮겨 올 코드의 입출력 | 초안 확정 / 수정 후 확정 | 11-19 12:00 |

### 나중에 정하는 안건

| 안건 | 주도 역할 | 함께 정할 역할 | 이유 | 필요한 정보 | 선택지 | 기한 |
|---|---|---|---|---|---|---|
| D3 로컬 LLM 실측 | AI Engineer | Cloud Engineer | 로컬 모델 연결·실측 작업이 생김 / 실행 환경·자원이 영향받음 | 11-25 MVP 뒤 남은 여유. 포함 시 약 4h | 제외 / 포함 | 11-25(수) |
| D10 시연 질문 캐시 | Cloud Engineer | AI Solutions Architect | 캐시 준비·시연 운영 작업이 생김 / 발표 진행과 설명이 영향받음 | 시연 질문 목록, 배포 안정성 | 캐시 / 실시간 | 11-29(일) |

## 3. 확정 뒤 바로 할 일

- [ ] decisions.md에 결정 기록(AI Solutions Architect)
- [ ] 작업 카드 만들기: 담당자 1명 = 브랜치 1개(전원). [roles.md](roles.md) 3장의 (a)·(b)·(c)를 먼저 만듭니다
- [ ] README 팀원별 역할에 이름 채우기(AI Solutions Architect)
- [ ] 코드 들여오기 시작(Cloud Engineer, 위 결정대로)
- [ ] `.env.example` 변수 이름을 들여온 코드에 맞추기(Cloud Engineer)
