{{ config(severity = 'warn') }}

-- Warns when Morocco's total exports or imports change by more than the
-- series_break_threshold from one year to the next. Such a jump usually comes
-- from a change in how the data are compiled, not from the economy itself.

select
    year,
    exports_usd,
    imports_usd,
    exports_growth,
    imports_growth
from {{ ref('mart_trade_overview') }}
where possible_series_break
