{{ config(severity = 'warn') }}

-- Reconciliation: the sum of HS chapters should match the reported total
-- (Morocco with the world). Differences above 1 % are reported as warnings.

with chapters as (

    select f.year, f.flow_code, sum(f.trade_value_usd) as chapters_value_usd
    from {{ ref('fct_trade') }} as f
    inner join {{ ref('dim_product') }} as p
        on p.cmd_code = f.cmd_code
    where f.reporter_code = {{ var('morocco_code') }}
      and f.partner_code = 0
      and p.product_level = 'HS2 chapter'
    group by f.year, f.flow_code

),

total as (

    select year, flow_code, trade_value_usd as total_value_usd
    from {{ ref('fct_trade') }}
    where reporter_code = {{ var('morocco_code') }}
      and partner_code = 0
      and cmd_code = 'TOTAL'

)

select
    t.year,
    t.flow_code,
    t.total_value_usd,
    c.chapters_value_usd,
    abs(c.chapters_value_usd - t.total_value_usd) / nullif(t.total_value_usd, 0) as relative_gap
from total as t
inner join chapters as c
    on c.year = t.year and c.flow_code = t.flow_code
where abs(c.chapters_value_usd - t.total_value_usd) / nullif(t.total_value_usd, 0) > 0.01
