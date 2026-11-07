-- Mirror statistics: what Morocco declares versus what its partners declare.
--   Morocco's exports to P (usually FOB)  vs  P's imports from Morocco (usually CIF)
--   Morocco's imports from P (usually CIF) vs  P's exports to Morocco (usually FOB)
-- Gaps of a few percent are expected (freight, insurance, timing, classification);
-- large gaps are flagged for review, not treated as errors.

with declared as (

    select year, flow_code, partner_code as counterpart_code, trade_value_usd as declared_value_usd
    from {{ ref('fct_trade') }}
    where reporter_code = {{ var('morocco_code') }}
      and cmd_code = 'TOTAL'
      and partner_code <> 0

),

mirror as (

    select
        year,
        -- A partner's imports from Morocco mirror Morocco's exports, and vice versa.
        case flow_code when 'M' then 'X' when 'X' then 'M' end as flow_code,
        reporter_code as counterpart_code,
        trade_value_usd as mirror_value_usd
    from {{ ref('fct_trade') }}
    where partner_code = {{ var('morocco_code') }}
      and reporter_code <> {{ var('morocco_code') }}
      and cmd_code = 'TOTAL'

),

compared as (

    select
        d.year,
        d.flow_code,
        d.counterpart_code,
        d.declared_value_usd,
        m.mirror_value_usd,
        m.mirror_value_usd - d.declared_value_usd as gap_usd,
        (m.mirror_value_usd - d.declared_value_usd) / nullif(d.declared_value_usd, 0) as gap_ratio
    from declared as d
    inner join mirror as m
        on m.year = d.year
       and m.flow_code = d.flow_code
       and m.counterpart_code = d.counterpart_code

)

select
    c.year,
    c.flow_code,
    case c.flow_code
        when 'X' then 'Morocco exports vs partner imports'
        else 'Morocco imports vs partner exports'
    end as comparison,
    c.counterpart_code,
    k.country_name as counterpart_name,
    c.declared_value_usd,
    c.mirror_value_usd,
    c.gap_usd,
    c.gap_ratio,
    abs(c.gap_ratio) > {{ var('mirror_gap_threshold') }} as needs_review
from compared as c
inner join {{ ref('dim_country') }} as k
    on k.country_code = c.counterpart_code
