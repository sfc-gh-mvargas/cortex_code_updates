-- =============================================================================
-- Similarity Model: Duplicate Skills Detection
-- Stored Procedure + Task for PRODUCT.UPDATES
-- =============================================================================

USE DATABASE PRODUCT;
USE SCHEMA UPDATES;
USE WAREHOUSE COCO_WH;

-- -----------------------------------------------------------------------------
-- 1. Output table for duplicate flags
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS PRODUCT.UPDATES.SKILLS_DUPLICATE_FLAGS (
    FLAG_ID         VARCHAR(256)    NOT NULL,
    SKILL_NAME_A    VARCHAR(256)    NOT NULL,
    SKILL_NAME_B    VARCHAR(256)    NOT NULL,
    DESCRIPTION_A   VARCHAR(16384),
    DESCRIPTION_B   VARCHAR(16384),
    SIMILARITY_SCORE FLOAT          NOT NULL,
    IS_DUPLICATE    BOOLEAN         NOT NULL DEFAULT TRUE,
    CDC_ACTION_A    VARCHAR(16),
    CDC_ACTION_B    VARCHAR(16),
    DETECTED_DATE_A DATE,
    DETECTED_DATE_B DATE,
    FLAGGED_AT      TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- -----------------------------------------------------------------------------
-- 2. Python Stored Procedure: similarity matching via embeddings
-- -----------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE PRODUCT.UPDATES.SP_FLAG_DUPLICATE_SKILLS(
    SIMILARITY_THRESHOLD FLOAT
)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'run'
EXECUTE AS CALLER
AS
$$
from snowflake.snowpark import Session

def run(session: Session, similarity_threshold: float) -> str:
    session.sql("USE DATABASE PRODUCT").collect()
    session.sql("USE SCHEMA UPDATES").collect()

    session.sql("""
        CREATE OR REPLACE TEMPORARY TABLE PRODUCT.UPDATES._TMP_SKILLS_EMBEDDED AS
        SELECT
            CDC_KEY,
            SKILL_NAME,
            SKILL_DESCRIPTION,
            CDC_ACTION,
            DETECTED_DATE,
            SNOWFLAKE.CORTEX.EMBED_TEXT_768(
                'snowflake-arctic-embed-m-v1.5',
                SKILL_NAME || ': ' || COALESCE(SKILL_DESCRIPTION, '')
            )::VECTOR(FLOAT, 768) AS EMBEDDING
        FROM PRODUCT.UPDATES.SKILLS_CDC_EVENTS
        WHERE SKILL_DESCRIPTION IS NOT NULL
    """).collect()

    session.sql("TRUNCATE TABLE IF EXISTS PRODUCT.UPDATES.SKILLS_DUPLICATE_FLAGS").collect()

    session.sql(f"""
        INSERT INTO PRODUCT.UPDATES.SKILLS_DUPLICATE_FLAGS
        SELECT
            MD5(a.SKILL_NAME || '|' || b.SKILL_NAME || '|' || a.DETECTED_DATE::VARCHAR) AS FLAG_ID,
            a.SKILL_NAME AS SKILL_NAME_A,
            b.SKILL_NAME AS SKILL_NAME_B,
            a.SKILL_DESCRIPTION AS DESCRIPTION_A,
            b.SKILL_DESCRIPTION AS DESCRIPTION_B,
            VECTOR_COSINE_SIMILARITY(a.EMBEDDING, b.EMBEDDING) AS SIMILARITY_SCORE,
            CASE
                WHEN VECTOR_COSINE_SIMILARITY(a.EMBEDDING, b.EMBEDDING) >= {similarity_threshold}
                THEN TRUE ELSE FALSE
            END AS IS_DUPLICATE,
            a.CDC_ACTION AS CDC_ACTION_A,
            b.CDC_ACTION AS CDC_ACTION_B,
            a.DETECTED_DATE AS DETECTED_DATE_A,
            b.DETECTED_DATE AS DETECTED_DATE_B,
            CURRENT_TIMESTAMP() AS FLAGGED_AT
        FROM PRODUCT.UPDATES._TMP_SKILLS_EMBEDDED a
        JOIN PRODUCT.UPDATES._TMP_SKILLS_EMBEDDED b
            ON a.SKILL_NAME < b.SKILL_NAME
        WHERE VECTOR_COSINE_SIMILARITY(a.EMBEDDING, b.EMBEDDING) >= {similarity_threshold}
    """).collect()

    result = session.sql("SELECT COUNT(*) AS CNT FROM PRODUCT.UPDATES.SKILLS_DUPLICATE_FLAGS WHERE IS_DUPLICATE = TRUE").collect()
    count = result[0]["CNT"]

    session.sql("DROP TABLE IF EXISTS PRODUCT.UPDATES._TMP_SKILLS_EMBEDDED").collect()

    return f"Flagged {count} duplicate pairs (threshold={similarity_threshold})"
$$;

-- -----------------------------------------------------------------------------
-- 3. Task: runs daily at 6 AM UTC
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TASK PRODUCT.UPDATES.TASK_FLAG_DUPLICATE_SKILLS
    WAREHOUSE = COCO_WH
    SCHEDULE = 'USING CRON 0 6 * * * UTC'
AS
    CALL PRODUCT.UPDATES.SP_FLAG_DUPLICATE_SKILLS(0.9);

-- Enable the task
ALTER TASK PRODUCT.UPDATES.TASK_FLAG_DUPLICATE_SKILLS RESUME;
