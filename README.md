# Cortex CLI Skills CDC Pipeline

Tracks changes to Cortex Code CLI skills over time. Captures skill metadata daily and detects NEW, DELETED, and UPDATED skills via CDC logic.

## Architecture

```
cortex skill list → ingest_skills.py → BRONZE (append-only)
                                            ↓
                                    STG_SKILLS_LATEST (dedup view)
                                            ↓
                                    V_SKILLS_CDC_PENDING (diff view)
                                            ↓
                                    SKILLS_CDC_EVENTS (silver table)
```

## Setup

```bash
uv venv --python 3.13
uv add snowflake-connector-python pyyaml
```

Deploy Snowflake objects:

```bash
# Run configs.sql against your Snowflake account
# Or execute via snowsql / cortex
```

## Run Pipeline

```bash
# 1. Ingest current skills snapshot (appends to bronze)
SNOWFLAKE_CONNECTION_NAME=default uv run python src/ingest_skills.py

# 2. Materialize CDC events (run in Snowflake after ingestion)
```

```sql
INSERT INTO PRODUCT.UPDATES.SKILLS_CDC_EVENTS
SELECT * FROM PRODUCT.UPDATES.V_SKILLS_CDC_PENDING p
WHERE NOT EXISTS (
    SELECT 1 FROM PRODUCT.UPDATES.SKILLS_CDC_EVENTS e
    WHERE e.cdc_key = p.cdc_key
);
```

## Query CDC Results

```sql
-- All changes detected today
SELECT * FROM PRODUCT.UPDATES.SKILLS_CDC_EVENTS
WHERE DETECTED_DATE = CURRENT_DATE()
ORDER BY CDC_ACTION, SKILL_NAME;

-- History of a specific skill
SELECT * FROM PRODUCT.UPDATES.SKILLS_CDC_EVENTS
WHERE SKILL_NAME = 'cortex-agent'
ORDER BY DETECTED_DATE;

-- Summary by action type
SELECT CDC_ACTION, COUNT(*) AS cnt
FROM PRODUCT.UPDATES.SKILLS_CDC_EVENTS
GROUP BY CDC_ACTION;
```

## Snowflake Objects

| Object | Type | Purpose |
|--------|------|---------|
| `PRODUCT.UPDATES.CORTEX_CLI_BUNDLED_SKILLS_LOG` | Table | Bronze append-only log |
| `PRODUCT.UPDATES.STG_SKILLS_LATEST` | View | Dedup (latest per skill per day) |
| `PRODUCT.UPDATES.V_SKILLS_CDC_PENDING` | View | CDC detection (today vs previous) |
| `PRODUCT.UPDATES.SKILLS_CDC_EVENTS` | Table | Silver CDC events (append-only) |

## dbt Project

The `cortex_skills_cdc/` directory contains equivalent dbt models. Requires keypair or password auth in `~/.dbt/profiles.yml` (PAT not supported by dbt-snowflake 1.11.3).

```bash
cd cortex_skills_cdc
dbt deps
dbt run
```
