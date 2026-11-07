-- Morocco's exports, imports and trade balance with the world, by year.

with world as (

    select year, flow_code, trade_value_usd
    from {{ ref('fct_trade') }}
    where reporter_code = {{ var('morocco_code') }}
      and partner_code = 0
      and cmd_code = 'TOTAL'

),

by_year as (

    select
        year,
        sum(case when flow_code = 'X' then trade_value_usd end) as exports_usd,
        sum(case when flow_code = 'M' then trade_value_usd end) as imports_usd
    from world
    group by year

),

with_growth as (

    select
        year,
        exports_usd,
        imports_usd,
        exports_usd - imports_usd as trade_balance_usd,
        exports_usd / nullif(imports_usd, 0) as coverage_ratio,
        exports_usd / nullif(lag(exports_usd) over (order by year), 0) - 1 as exports_growth,
        imports_usd / nullif(lag(imports_usd) over (order by year), 0) - 1 as imports_growth
    from by_year

)

select
    *,
    -- Flags a jump too large to be ordinary economic change; to be checked
    -- against national statistics and partners' mirror declarations.
    coalesce(
        abs(exports_growth) > {{ var('series_break_threshold') }}
        or abs(imports_growth) > {{ var('series_break_threshold') }},
        false
    ) as possible_series_break
from with_growth
