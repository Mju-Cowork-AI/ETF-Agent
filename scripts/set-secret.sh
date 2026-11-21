#!/usr/bin/env bash
# API 키를 Azure Key Vault와 GitHub Secrets에 함께 저장합니다.
# 값은 화면에 표시되지 않고, 파일이나 셸 히스토리에도 남지 않습니다.
set -euo pipefail

REPO="Mju-Cowork-AI/ETF-Agent"

usage() {
  cat >&2 <<USAGE
사용법: KV_NAME=<Key Vault 이름> scripts/set-secret.sh <SECRET_NAME>
  예)  KV_NAME=kv-etfqa-1234 scripts/set-secret.sh LLM_API_KEY

  - SECRET_NAME: 대문자/숫자/언더스코어 (예: LLM_API_KEY)
  - Key Vault에는 언더스코어를 하이픈으로 바꿔 저장합니다 (LLM-API-KEY)
  - GitHub Secrets(${REPO})에는 그대로 저장합니다 (LLM_API_KEY)
  - 사전 조건: az login, gh auth login
USAGE
}

if [[ $# -ne 1 || -z "${KV_NAME:-}" ]]; then
  usage
  exit 1
fi

NAME="$1"
if [[ ! "$NAME" =~ ^[A-Z][A-Z0-9_]*$ ]]; then
  echo "오류: 시크릿 이름은 대문자/숫자/언더스코어만 가능합니다: $NAME" >&2
  usage
  exit 1
fi
KV_SECRET_NAME="${NAME//_/-}"

VALUE=""
trap 'unset VALUE' EXIT

read -r -s -p "${NAME} 값 입력 (화면에 표시되지 않음): " VALUE
echo
if [[ -z "$VALUE" ]]; then
  echo "오류: 값이 비어 있습니다. 아무것도 저장하지 않았습니다." >&2
  exit 1
fi

# 값은 표준입력(파이프)으로만 전달 — 프로세스 목록/히스토리에 남지 않음
printf '%s' "$VALUE" | az keyvault secret set \
  --vault-name "$KV_NAME" --name "$KV_SECRET_NAME" \
  --file /dev/stdin --encoding utf-8 --output none
echo "✔ Key Vault ${KV_NAME}: ${KV_SECRET_NAME}"

printf '%s' "$VALUE" | gh secret set "$NAME" -R "$REPO"
echo "✔ GitHub Secret ${REPO}: ${NAME}"

unset VALUE
