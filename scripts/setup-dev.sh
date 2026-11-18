#!/usr/bin/env bash
# 호스트 개발 환경을 만듭니다: API 의존성(uv) + 웹 의존성(npm) + .env 준비
# make test / make lint / make check 를 호스트에서 돌리기 위한 준비입니다.
# 어느 브랜치에서든 다시 실행해도 안전합니다.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
  echo "오류: uv를 찾을 수 없습니다. 설치: https://docs.astral.sh/uv/" >&2
  exit 1
fi
# uv가 Python 3.14를 자동으로 받아 apps/api/.venv를 만듭니다
(cd apps/api && uv sync --locked)

if command -v npm >/dev/null 2>&1; then
  (cd apps/web && npm ci)
else
  echo "! npm이 없어 웹 의존성 설치를 건너뜁니다. Node.js 24를 설치한 뒤 다시 실행하세요." >&2
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "→ .env 를 만들었습니다. 필요한 키 값을 채워 주세요. (커밋 금지)"
fi

echo
echo "완료. 다음 중 하나로 사용하세요:"
echo "  ./scripts/run-fake.sh        # API 키 없이 DB·API·웹 실행"
echo "  make check                   # CI와 같은 검사 실행(DB 컨테이너 필요)"
