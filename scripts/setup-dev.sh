#!/usr/bin/env bash
# 로컬 개발 환경을 만듭니다: .venv(Python 3.14) + 의존성 설치 + .env 준비
# 어느 브랜치에서든 다시 실행해도 안전합니다.
set -euo pipefail
cd "$(dirname "$0")/.."

if command -v uv >/dev/null 2>&1; then
  # uv가 있으면 Python 3.14이 없어도 자동으로 받아 옵니다
  [[ -d .venv ]] || uv venv --python 3.14 .venv
  uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt
else
  PY=""
  for c in python3.14 python3 python; do
    if command -v "$c" >/dev/null 2>&1 &&
      "$c" -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 14))'; then
      PY="$c"
      break
    fi
  done
  if [[ -z "$PY" ]]; then
    echo "오류: Python 3.14을 찾을 수 없습니다." >&2
    echo "  uv 설치(권장): https://docs.astral.sh/uv/  또는 Python 3.14을 설치하세요." >&2
    exit 1
  fi
  [[ -d .venv ]] || "$PY" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "→ .env 를 만들었습니다. 필요한 키 값을 채워 주세요. (커밋 금지)"
fi

echo
echo "완료. 다음 중 하나로 사용하세요:"
echo "  source .venv/bin/activate    # 가상환경 활성화"
echo "  make check                   # CI와 같은 검사 실행"
