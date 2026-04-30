# Quickstart

## Prerequisites

- [uv](https://docs.astral.sh/uv/) installed
- [Cortex Code CLI](https://docs.snowflake.com/en/user-guide/cortex-code) installed (`cortex --version`)
- Snowflake connection configured in `~/.snowflake/connections.toml`

## 1. Install Python dependencies

```bash
uv venv --python 3.13
uv add snowflake-connector-python pyyaml
```

## 2. Ingest skills (run weekly)

```bash
SNOWFLAKE_CONNECTION_NAME=default uv run python src/ingest_skills.py
```

## 3. Run dbt CDC models

### Option A: Against real data (PRODUCT)

```bash
cd cortex_skills_cdc
uv run dbt deps
uv run dbt run --vars '{"source_database": "PRODUCT"}'
uv run dbt test
```

### Option B: Against mock data (local CI validation)

```bash
cd cortex_skills_cdc
uv run dbt deps
uv run dbt seed --target ci --vars '{"use_seed": true, "source_database": "PRODUCT_DEV"}'
uv run dbt run --target ci --vars '{"use_seed": true, "source_database": "PRODUCT_DEV"}' --full-refresh
uv run dbt test --target ci --vars '{"use_seed": true, "source_database": "PRODUCT_DEV"}'
```

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SNOWFLAKE_CONNECTION_NAME` | `default` | Connection for `ingest_skills.py` |
| `DBT_SOURCE_DATABASE` | `PRODUCT` | Overrides `var('source_database')` in dbt |

## Project structure

```
newsletter/
├── src/
│   └── ingest_skills.py          # Bronze ingestion script
├── cortex_skills_cdc/
│   ├── dbt_project.yml           # Parametrized with var('source_database')
│   ├── profiles/profiles.yml     # dev + ci targets
│   ├── models/
│   │   ├── staging/
│   │   │   ├── sources.yml
│   │   │   └── stg_skills_latest.sql
│   │   └── silver/
│   │       ├── schema.yml
│   │       └── skills_cdc_events.sql
│   └── seeds/
│       ├── schema.yml
│       └── raw_skills_mock.csv   # Mock data (2 weeks)
├── .github/workflows/ci.yml      # GitHub Actions CI
└── QUICKSTART.md
```
