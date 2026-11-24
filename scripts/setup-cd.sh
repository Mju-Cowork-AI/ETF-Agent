#!/usr/bin/env bash
# 자동 배포(.github/workflows/deploy.yml)가 Azure에 키 없이 로그인하도록 한 번만 설정합니다.
# - Entra 앱(gh-etf-agent-deploy)과 서비스 주체를 만들고, 이 저장소의 main 브랜치만 로그인할 수 있게 연결합니다.
# - 권한은 레지스트리 푸시(AcrPush)와 API 앱·설정 작업 수정(Contributor)만 줍니다. Key Vault 권한은 주지 않습니다.
# - ID 세 개를 GitHub Secrets에 넣습니다(비밀 값이 아니라 식별자입니다).
# 사전 조건: az login(구독 소유자), gh auth login. 다시 실행해도 됩니다.
set -euo pipefail

REPO="Mju-Cowork-AI/ETF-Agent"
APP_NAME="gh-etf-agent-deploy"
RG="rg-etf-agent"
REGISTRY="acretfagentb084"
API_APP="ca-etf-agent-api"
SETUP_JOB="caj-etf-agent-setup"

SUB=$(az account show --query id -o tsv)
TENANT=$(az account show --query tenantId -o tsv)

APP_ID=$(az ad app list --display-name "$APP_NAME" --query "[0].appId" -o tsv)
if [[ -z "$APP_ID" ]]; then
  APP_ID=$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)
fi
az ad sp show --id "$APP_ID" --query id -o tsv >/dev/null 2>&1 || az ad sp create --id "$APP_ID" -o none
SP_ID=$(az ad sp show --id "$APP_ID" --query id -o tsv)

# GitHub이 보내는 주체(subject)는 조직·저장소 ID가 붙은 형식이다(11-24 첫 릴리스에서 확인).
# 이름만 있는 예전 형식(github-main)도 함께 등록해 둔다.
OWNER_ID=$(gh api "repos/${REPO}" --jq .owner.id)
REPO_ID=$(gh api "repos/${REPO}" --jq .id)
add_cred() {
  if ! az ad app federated-credential list --id "$APP_ID" --query "[].name" -o tsv | grep -qx "$1"; then
    az ad app federated-credential create --id "$APP_ID" -o none --parameters "{
      \"name\": \"$1\",
      \"issuer\": \"https://token.actions.githubusercontent.com\",
      \"subject\": \"$2\",
      \"audiences\": [\"api://AzureADTokenExchange\"]
    }"
  fi
}
add_cred github-main "repo:${REPO}:ref:refs/heads/main"
add_cred github-main-ids "repo:${REPO%%/*}@${OWNER_ID}/${REPO##*/}@${REPO_ID}:ref:refs/heads/main"

SCOPE="/subscriptions/${SUB}/resourceGroups/${RG}/providers"
assign() {
  az role assignment create --assignee-object-id "$SP_ID" --assignee-principal-type ServicePrincipal \
    --role "$1" --scope "$2" -o none
  echo "권한: $1 → ${2##*/}"
}
assign AcrPush "${SCOPE}/Microsoft.ContainerRegistry/registries/${REGISTRY}"
assign Contributor "${SCOPE}/Microsoft.App/containerApps/${API_APP}"
assign Contributor "${SCOPE}/Microsoft.App/jobs/${SETUP_JOB}"

gh secret set AZURE_CLIENT_ID -R "$REPO" --body "$APP_ID"
gh secret set AZURE_TENANT_ID -R "$REPO" --body "$TENANT"
gh secret set AZURE_SUBSCRIPTION_ID -R "$REPO" --body "$SUB"

echo "끝. 남은 것: Cloudflare 토큰을 CLOUDFLARE_API_TOKEN, 계정 ID를 CLOUDFLARE_ACCOUNT_ID로 GitHub Secrets에 넣기(infra/azure/README.md)"
