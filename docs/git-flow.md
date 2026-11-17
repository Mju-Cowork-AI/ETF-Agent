# Git 작업 흐름 가이드

처음이어도 이 문서만 따라 하면 됩니다. 명령은 위에서 아래로 그대로 실행하세요.

## 한눈에 보기

```
main  ●───────────────────────●──────────►  릴리스 (v1.0, v1.1 …)   selee1012만 머지
       \                     ↗ merge commit
dev     ●────●────●────●────●────────────►  개발 통합 (기본 브랜치)
              ↖ squash  ↖ squash
feat/…         ●──●──●   │
fix/…                    ●──●               내 작업 브랜치
```

- **`main`**: 릴리스된 코드. 직접 건드리지 않습니다.
- **`dev`**: 모두의 작업이 모이는 곳. 여기도 직접 push할 수 없고 **PR로만** 들어갑니다.
- **작업 브랜치**: 내가 실제로 코드를 고치는 곳. `dev`에서 만들고 `dev`로 돌아갑니다.

기억할 것은 세 가지입니다.

1. 작업은 항상 **`dev`에서 새 브랜치**를 만들어 시작한다.
2. 끝나면 **`dev`로 PR**을 올리고, CI가 초록색이면 **내가 직접 Squash 머지**한다.
3. `main`은 신경 쓰지 않는다. (릴리스는 selee1012가 합니다)

## 처음 한 번만

```bash
git clone git@github.com:Mju-Cowork-AI/ETF-Agent.git
cd ETF-Agent
make setup
```

## 매번 반복하는 흐름

### 1단계. 최신 dev에서 브랜치 만들기

```bash
git switch dev
git pull
git switch -c feat/etf-search
```

브랜치 이름은 `타입/짧은-설명`입니다. 타입은 `feat`, `fix`, `refactor`, `docs`, `chore`, `data`, `infra`, `prompt`, `eval`, `test` 중 하나입니다.

### 2단계. 작업하고 커밋하기

```bash
git add .
git commit -m "feat: ETF 종목 검색 추가"
```

- 커밋 메시지는 `타입: 내용` 형식입니다. 한글로 써도 됩니다.
- 커밋은 작게 여러 번 해도 됩니다. 머지할 때 하나로 합쳐집니다(squash).

### 3단계. 올리기 전에 검사하기

```bash
make check
```

여기서 통과하면 CI도 통과합니다. 실패하면 `make format`으로 자동 수정되는 것이 많습니다.

### 4단계. push하고 PR 만들기

```bash
git push -u origin feat/etf-search
gh pr create --base dev --fill
```

`gh`가 없으면 push 후 GitHub 페이지에 뜨는 **Compare & pull request** 버튼을 누르세요. base가 `dev`인지 확인합니다.

PR 제목도 `타입: 내용` 형식으로 적습니다. 이 제목이 `dev`에 남는 커밋 메시지가 됩니다.

### 5단계. CI 통과 후 직접 머지하기

1. PR 페이지에서 `ci` 검사가 초록색이 될 때까지 기다립니다 (보통 1분 이내).
2. **Squash and merge** 버튼을 누릅니다. 승인은 필수가 아니지만, 헷갈리는 변경은 팀원에게 리뷰를 부탁하세요.
   - **예외:** 개인정보 차단, 가드(검증), 숫자 대조, 데이터 파이프라인을 고치는 PR은 **팀원 1명의 승인**을 받은 뒤 머지합니다([dev-guide.md](dev-guide.md) 4장).
3. 작업 브랜치는 GitHub에서 자동으로 삭제됩니다.

명령으로 하려면:

```bash
gh pr merge --squash
```

### 6단계. 정리하고 다음 작업 시작하기

```bash
git switch dev
git pull
git branch -D feat/etf-search
```

`-D`(대문자)를 쓰는 이유: squash 머지는 커밋을 새로 만들기 때문에 git이 "머지 안 된 브랜치"로 보고 `-d`를 거부합니다. PR이 머지된 것을 확인했다면 지워도 안전합니다.

## 매일 아침: dev 받아 오기

작업이 며칠 걸리면 그동안 `dev`가 바뀝니다. 매일 한 번 받아서 충돌을 작게 유지하세요.

```bash
git fetch origin
git merge origin/dev
```

### 충돌이 났을 때

1. `git status`로 충돌 난 파일을 확인합니다.
2. 파일을 열어 `<<<<<<<`, `=======`, `>>>>>>>` 표시 사이에서 남길 내용을 고르고 표시를 지웁니다.
3. 정리 후:

```bash
git add <고친 파일>
git commit
make check
```

어느 쪽을 남겨야 할지 모르겠으면 그 코드를 쓴 팀원에게 물어보세요. 포기하고 되돌리려면 `git merge --abort`.

## 릴리스 (selee1012만)

```bash
gh pr create --base main --head dev --title "release: v1.0"
gh pr merge <PR번호> --merge
git fetch origin && git tag v1.0 origin/main && git push origin v1.0
```

- `main`으로는 `dev`에서 온 PR만 가능합니다. 다른 브랜치에서 올리면 CI가 실패합니다.
- 방식은 **merge commit**만 허용됩니다. `dev` 브랜치는 머지 후에도 삭제되지 않습니다.

## 자주 겪는 상황

| 상황 | 해결 |
|---|---|
| `dev`에 push했더니 거부됨 | 정상입니다. 브랜치를 만들어 PR로 올리세요. 이미 `dev`에 커밋했다면 아래 "dev에 커밋해 버렸을 때" 참고 |
| 머지 버튼이 비활성화됨 | `ci`가 실패했거나 아직 도는 중입니다. PR의 Checks 탭에서 로그를 확인하세요 |
| `ci`가 ruff에서 실패 | `make format` 후 다시 커밋·push |
| PR에 "conflicts" 표시 | "매일 아침" 절차대로 `origin/dev`를 머지해 충돌을 풀고 push |
| 브랜치 이름을 잘못 지음 | `git branch -m 새이름` (push 전) |
| 방금 커밋 메시지를 고치고 싶음 | `git commit --amend` (push 전) |
| API 키를 커밋해 버림 | 즉시 팀에 알리고 키를 **폐기 후 재발급**. 지우는 것만으로는 부족합니다 |

### dev에 커밋해 버렸을 때

push 전이라면 커밋을 그대로 새 브랜치로 옮길 수 있습니다.

```bash
git switch -c feat/내-작업        # 지금 커밋을 가진 새 브랜치 생성
git branch -f dev origin/dev      # 로컬 dev를 원격 상태로 되돌림
```

## 하지 말아야 할 것

- `dev`, `main`에 force push (막혀 있습니다)
- 다른 사람의 작업 브랜치에 force push
- `.env`나 API 키 커밋
- CI가 빨간색인 PR을 그대로 두기 — 고치거나 닫아 주세요
