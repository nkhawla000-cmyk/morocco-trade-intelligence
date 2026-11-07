-- Partner concentration of Morocco's trade (Herfindahl-Hirschman index, HHI).
-- HHI = 10 000 x sum of squared partner shares: 10 000 means a single partner.
-- Scope: all products (TOTAL) and each automotive focus heading.
-- World and Comtrade pseudo-areas are excluded, so shares sum to 1.

with base as (

    select f.year, f.flow_code, f.cmd_code, f.partner_code, f.trade_value_usd
    from {{ ref('fct_trade') }} as f
    inner join {{ ref('dim_country') }} as c
        on c.country_code = f.partner_code
    inner join {{ ref('dim_product') }} as p
        on p.cmd_code = f.cmd_code
    where f.reporter_code = {{ var('morocco_code') }}
      and not c.is_world
      and not c.is_special_area
      and (p.product_level = 'Total' or p.focus_group = 'Automotive')
      and f.trade_value_usd > 0

),

shares as (

    select
        *,
        trade_value_usd / sum(trade_value_usd) over (partition by year, flow_code, cmd_code) as share,
        row_number() over (
            partition by year, flow_code, cmd_code
            order by trade_value_usd desc, partner_code
        ) as partner_rank
    from base

),

indicators as (

    select
        year,
        flow_code,
        cmd_code,
        count(*) as partner_count,
        sum(trade_value_usd) as total_value_usd,
        10000 * sum(share * share) as hhi,
        max(case when partner_rank = 1 then partner_code end) as top_partner_code,
        max(case when partner_rank = 1 then share end) as top_partner_share,
        sum(case when partner_rank <= 5 then share else 0 end) as top5_share
    from shares
    group by year, flow_code, cmd_code

)

select
    i.year,
    i.flow_code,
    i.cmd_code,
    p.product_description,
    i.partner_count,
    i.total_value_usd,
    round(i.hhi, 1) as hhi,
    -- Indicative thresholds (US horizontal merger guidelines, 2010).
    case
        when i.hhi < 1500 then 'Low'
        when i.hhi < 2500 then 'Moderate'
        else 'High'
    end as concentration_level,
    i.top_partner_code,
    c.country_name as top_partner_name,
    i.top_partner_share,
    i.top5_share
from indicators as i
inner join {{ ref('dim_product') }} as p
    on p.cmd_code = i.cmd_code
left join {{ ref('dim_country') }} as c
    on c.country_code = i.top_partner_code
