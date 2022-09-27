-- this should usually join stuff together, but we do not have anything to join to, so just build the customer as is...

select
    customer_id,
    coalesce(journeys, 0) as journeys,
    coalesce(amount_cents, 0) as amount_cents
-- Use the `ref` function to select from other models
from {{ ref('agg_journey_per_customer') }}
