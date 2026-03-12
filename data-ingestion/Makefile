.PHONY: db db-down migrate discover ingest list clean embed chat serve

docker-up:
	docker compose up -d

docker-down:
	docker compose down

migrate:
	uv run alembic upgrade head

discover:
	uv run python -m src.cli discover $(COUNTY)

ingest:
	uv run python -m src.cli ingest $(COUNTY)

zoning:
	uv run python -m src.cli zoning $(COUNTY)

seed-zoning:
	uv run python -m src.cli seed-zoning

list:
	uv run python -m src.cli list

embed:
	uv run python -m src.cli embed

chat:
	uv run python -m src.cli chat

serve:
	uv run uvicorn src.api:app --reload --port 8000

clean:
	docker compose down -v
