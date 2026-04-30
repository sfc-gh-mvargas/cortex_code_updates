{{
    config(materialized='view')
}}

with ranked as (
    select
        skill_name,
        skill_description,
        skill_type,
        skill_path,
        cli_version,
        captured_at,
        ingestion_date,
        row_number() over (
            partition by skill_name, ingestion_date
            order by captured_at desc
        ) as rn
    from
        {% if var('use_seed', false) %}
            {{ ref('raw_skills_mock') }}
        {% else %}
            {{ source('raw_skills', 'CORTEX_CLI_BUNDLED_SKILLS_LOG') }}
        {% endif %}
)

select
    skill_name,
    skill_description,
    skill_type,
    skill_path,
    cli_version,
    captured_at,
    ingestion_date
from ranked
where rn = 1
