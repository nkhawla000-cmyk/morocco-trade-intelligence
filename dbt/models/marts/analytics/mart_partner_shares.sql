-- Morocco's trade by partner country: value, share of the world total and rank.

with totals as (

    select f.year, f.flow_code, f.partner_code, f.trade_value_usd
    from {{ ref('fct_trade') }} as f
    where f.reporter_code = {{ var('morocco_code') }}
      and f.cmd_code = 'TOTAL'

),

world as (

    select year, flow_code, trade_value_usd as world_value_usd
    from totals
    where partner_code = 0

)

select
    t.year,
    t.flow_code,
    t.partner_code,
    c.country_name as partner_name,
    c.is_special_area,
    t.trade_value_usd,
    w.world_value_usd,
    t.trade_value_usd / nullif(w.world_value_usd, 0) as share_of_world,
    -- Only real countries are ranked; pseudo-areas ("areas, nes"...) get no rank.
    case
        when not c.is_special_area then rank() over (
            partition by t.year, t.flow_code, c.is_special_area
            order by t.trade_value_usd desc
        )
    end as partner_rank
from totals as t
inner join world as w
    on w.year = t.year and w.flow_code = t.flow_code
inner join {{ ref('dim_country') }} as c
    on c.country_code = t.partner_code
where t.partner_code <> 0
