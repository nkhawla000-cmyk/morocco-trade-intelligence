-- Trade values cannot be negative.
select *
from {{ ref('fct_trade') }}
where trade_value_usd < 0
