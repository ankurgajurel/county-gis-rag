.PHONY: db db-down migrate discover ingest list clean

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

clean:
	docker compose down -v
