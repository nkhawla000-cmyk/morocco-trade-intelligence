-- Unusual year-on-year changes in Morocco's trade with a partner.
-- Each partner's change is compared with the changes of all partners in the
-- same year and flow (robust z-score built on the median and the median
-- absolute deviation, MAD). A shift that moves every partner at once, such as
-- the 2024 series break, is therefore not flagged by itself.

with partner_flows as (

    select f.year, f.flow_code, f.partner_code, c.country_name as partner_name, f.trade_value_usd
    from {{ ref('fct_trade') }} as f
    inner join {{ ref('dim_country') }} as c
        on c.country_code = f.partner_code
    where f.reporter_code = {{ var('morocco_code') }}
      and f.cmd_code = 'TOTAL'
      and not c.is_world
      and not c.is_special_area

),

changes as (

    select
        *,
        lag(year) over (partition by flow_code, partner_code order by year) as previous_year,
        lag(trade_value_usd) over (partition by flow_code, partner_code order by year) as previous_value_usd
    from partner_flows

),

eligible as (

    -- Small flows move a lot for trivial reasons: only partners above a
    -- minimum value in the previous year are scored.
    select
        *,
        ln(trade_value_usd / previous_value_usd) as log_change
    from changes
    where previous_year = year - 1
      and previous_value_usd >= {{ var('anomaly_min_value_usd') }}
      and trade_value_usd > 0

),

medians as (

    select year, flow_code, median(log_change) as median_log_change
    from eligible
    group by year, flow_code

),

deviations as (

    select
        e.*,
        m.median_log_change,
        abs(e.log_change - m.median_log_change) as abs_deviation
    from eligible as e
    inner join medians as m
        on m.year = e.year and m.flow_code = e.flow_code

),

spread as (

    select year, flow_code, median(abs_deviation) as mad, count(*) as partners_compared
    from deviations
    group by year, flow_code

),

scored as (

    select
        d.year,
        d.flow_code,
        d.partner_code,
        d.partner_name,
        d.previous_value_usd,
        d.trade_value_usd,
        exp(d.log_change) - 1 as change_ratio,
        exp(d.median_log_change) - 1 as typical_change_ratio,
        -- 1.4826 x MAD estimates the standard deviation for normal data.
        (d.log_change - d.median_log_change) / nullif(1.4826 * s.mad, 0) as robust_z,
        s.partners_compared
    from deviations as d
    inner join spread as s
        on s.year = d.year and s.flow_code = d.flow_code

)

select
    *,
    coalesce(abs(robust_z) > {{ var('anomaly_z_threshold') }}, false) as is_anomaly
from scored
