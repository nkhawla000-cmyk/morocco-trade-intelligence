-- Structure of Morocco's trade with the world by HS chapter: share, rank and growth.

with chapters as (

    select f.year, f.flow_code, f.cmd_code, p.product_description, f.trade_value_usd
    from {{ ref('fct_trade') }} as f
    inner join {{ ref('dim_product') }} as p
        on p.cmd_code = f.cmd_code
    where f.reporter_code = {{ var('morocco_code') }}
      and f.partner_code = 0
      and p.product_level = 'HS2 chapter'

)

select
    year,
    flow_code,
    cmd_code as hs_chapter,
    product_description,
    trade_value_usd,
    trade_value_usd / sum(trade_value_usd) over (partition by year, flow_code) as share_of_chapters,
    rank() over (partition by year, flow_code order by trade_value_usd desc) as chapter_rank,
    trade_value_usd / nullif(
        lag(trade_value_usd) over (partition by flow_code, cmd_code order by year), 0
    ) - 1 as growth_vs_previous_year
from chapters
