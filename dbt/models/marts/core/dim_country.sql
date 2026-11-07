-- One row per country or area code seen as reporter or partner.

with flows as (

    select * from {{ ref('stg_comtrade__trade_flows') }}

),

codes as (

    select reporter_code as country_code, reporter_iso as iso3, reporter_name as country_name from flows
    union all
    select partner_code, partner_iso, partner_name from flows

),

ranked as (

    select
        *,
        row_number() over (partition by country_code order by country_name nulls last, iso3) as rank_in_code
    from codes

),

mirror_reporters as (

    select distinct reporter_code
    from flows
    where reporter_code <> {{ var('morocco_code') }}

)

select
    r.country_code,
    r.iso3,
    coalesce(r.country_name, 'Code ' || r.country_code) as country_name,
    r.country_code = 0 as is_world,
    -- Comtrade pseudo-partners: bunkers, free zones, special categories, "areas, nes"...
    (
        r.country_code in (837, 838, 839, 899)
        or regexp_matches(coalesce(r.country_name, ''), '\bnes\b')
    ) as is_special_area,
    r.country_code = {{ var('morocco_code') }} as is_morocco,
    m.reporter_code is not null as is_mirror_partner
from ranked as r
left join mirror_reporters as m
    on m.reporter_code = r.country_code
where r.rank_in_code = 1
