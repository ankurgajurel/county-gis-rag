.PHONY: db db-down migrate discover ingest list clean

db:
	docker compose up -d

db-down:
	docker compose down

migrate:
	uv run alembic upgrade head

discover:
	uv run python -m src.cli discover $(COUNTY)

ingest:
	uv run python -m src.cli ingest $(COUNTY)

list:
	uv run python -m src.cli list

clean:
	docker compose down -v
