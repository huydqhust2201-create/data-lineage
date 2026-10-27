.PHONY: run test lint format typecheck check clean eval-chat

run:
	uvicorn src.main:app --reload --host 127.0.0.1 --port 8001

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

typecheck:
	mypy src/

check: lint format test

eval-chat:
	@test -n "$(DATABASE_ID)" || (echo "DATABASE_ID is required" && exit 1)
	@test -n "$(USER_ID)" || (echo "USER_ID is required" && exit 1)
	python -m eval.run_chat_eval --database-id $(DATABASE_ID) --user-id $(USER_ID) --runs $(or $(RUNS),3) --out $(or $(OUT),eval/results/chat-baseline.json)

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
