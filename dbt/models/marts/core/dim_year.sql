with years as (

    select distinct year
    from {{ ref('stg_comtrade__trade_flows') }}

)

select
    year,
    year = max(year) over () as is_latest_year
from years
