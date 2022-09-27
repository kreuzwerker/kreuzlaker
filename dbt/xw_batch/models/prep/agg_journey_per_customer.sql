{{ config(materialized='table') }}

with journeys as (
    select *
    -- use source function to access the source datasets
    from {{ source('data_lake_converted', 'journeys') }}
)

select
    customer_id,
    count(*) as journeys,
    sum(amount_cents) as amount_cents
from journeys
group by customer_id
