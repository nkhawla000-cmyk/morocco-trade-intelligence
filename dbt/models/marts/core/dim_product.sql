-- One row per product code: TOTAL, HS chapters (2 digits) and HS headings (4 digits).

with products as (

    select
        cmd_code,
        max(cmd_description) as product_description,
        max(hs_level) as hs_level
    from {{ ref('stg_comtrade__trade_flows') }}
    group by cmd_code

)

select
    p.cmd_code,
    coalesce(p.product_description, p.cmd_code) as product_description,
    case
        when p.cmd_code = 'TOTAL' then 'Total'
        when length(p.cmd_code) = 2 then 'HS2 chapter'
        when length(p.cmd_code) = 4 then 'HS4 heading'
        else 'Other'
    end as product_level,
    case when p.cmd_code = 'TOTAL' then null else left(p.cmd_code, 2) end as hs_chapter,
    p.hs_level,
    f.focus_group,
    f.focus_label,
    f.cmd_code is not null as is_focus_product
from products as p
left join {{ ref('hs_focus_products') }} as f
    on f.cmd_code = p.cmd_code
