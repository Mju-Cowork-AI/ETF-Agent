# 로컬 개발 명령 모음. `make help`로 목록을 봅니다.
BIN := .venv/bin

.DEFAULT_GOAL := help
.PHONY: help setup lint format compile test check clean

help: ## 사용 가능한 명령 보기
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  make %-8s %s\n", $$1, $$2}'

setup: ## 가상환경(.venv) 생성 + 의존성 설치 + .env 준비
	@scripts/setup-dev.sh

lint: ## ruff 검사
	$(BIN)/ruff check .

format: ## ruff 자동 수정 + 포맷
	$(BIN)/ruff check --fix .
	$(BIN)/ruff format .

compile: ## 문법 오류 검사
	$(BIN)/python -m compileall -q app agent data pipeline eval

test: ## pytest 실행
	$(BIN)/pytest -q

check: lint compile test ## CI와 동일한 검사 (PR 올리기 전에 실행)

clean: ## 가상환경과 캐시 삭제
	rm -rf .venv .ruff_cache .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
