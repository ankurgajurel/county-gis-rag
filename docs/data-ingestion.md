# Setup

## Prerequisites

- Docker & Docker Compose
- Python 3.11+
- uv

## Start services

```
cd data-ingestion
make docker-up
```

## Database

- Host: `localhost` (or `db` from within Docker network)
- Port: `5432`
- Database: `county_gis`
- User: `gis_user`
- Password: `gis_password`

## pgAdmin

- URL: `http://localhost:5050`
- Email: `admin@local.dev`
- Password: `admin`

When adding a server connection in pgAdmin, use host `db` (not `localhost`) since pgAdmin runs inside Docker.

## Install dependencies

```
cd data-ingestion
cp .env.example .env
uv sync
```

## Run migrations

```
make migrate
```

## Run pipeline

```
make discover COUNTY=dupage
make ingest COUNTY=dupage
```
