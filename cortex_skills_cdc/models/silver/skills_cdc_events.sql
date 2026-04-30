{{
    config(
        materialized='incremental',
        unique_key='cdc_key',
        incremental_strategy='append'
    )
}}

with latest_date as (
    select max(ingestion_date) as max_date
    from {{ ref('stg_skills_latest') }}
),

previous_date as (
    select max(ingestion_date) as prev_date
    from {{ ref('stg_skills_latest') }}
    where ingestion_date < (select max_date from latest_date)
),

current_snapshot as (
    select
        skill_name,
        skill_description,
        skill_type,
        skill_path,
        cli_version,
        ingestion_date
    from {{ ref('stg_skills_latest') }}
    where ingestion_date = (select max_date from latest_date)
),

previous_snapshot as (
    select
        skill_name,
        skill_description,
        skill_type,
        skill_path,
        cli_version,
        ingestion_date
    from {{ ref('stg_skills_latest') }}
    where ingestion_date = (select prev_date from previous_date)
),

new_records as (
    select
        c.skill_name,
        c.skill_description,
        c.skill_type,
        c.skill_path,
        c.cli_version,
        c.ingestion_date as detected_date,
        'NEW' as cdc_action,
        null as change_detail
    from current_snapshot c
    left join previous_snapshot p on c.skill_name = p.skill_name
    where p.skill_name is null
),

deleted_records as (
    select
        p.skill_name,
        p.skill_description,
        p.skill_type,
        p.skill_path,
        p.cli_version,
        (select max_date from latest_date) as detected_date,
        'DELETED' as cdc_action,
        null as change_detail
    from previous_snapshot p
    left join current_snapshot c on p.skill_name = c.skill_name
    where c.skill_name is null
),

updated_records as (
    select
        c.skill_name,
        c.skill_description,
        c.skill_type,
        c.skill_path,
        c.cli_version,
        c.ingestion_date as detected_date,
        'UPDATED' as cdc_action,
        case
            when c.skill_description != p.skill_description or
                 (c.skill_description is null and p.skill_description is not null) or
                 (c.skill_description is not null and p.skill_description is null)
            then 'description_changed'
            when c.skill_type != p.skill_type
            then 'type_changed'
            when c.skill_path != p.skill_path
            then 'path_changed'
            else 'other_change'
        end as change_detail
    from current_snapshot c
    inner join previous_snapshot p on c.skill_name = p.skill_name
    where c.skill_description != p.skill_description
       or c.skill_type != p.skill_type
       or c.skill_path != p.skill_path
       or (c.skill_description is null and p.skill_description is not null)
       or (c.skill_description is not null and p.skill_description is null)
),

all_changes as (
    select * from new_records
    union all
    select * from deleted_records
    union all
    select * from updated_records
)

select
    md5(skill_name || '|' || detected_date::varchar || '|' || cdc_action) as cdc_key,
    skill_name,
    skill_description,
    skill_type,
    skill_path,
    cli_version,
    detected_date,
    cdc_action,
    change_detail,
    current_timestamp() as processed_at
from all_changes


