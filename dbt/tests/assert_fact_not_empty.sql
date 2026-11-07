-- Fails if the fact table is empty (for example when every API answer was empty).
select count(*) as row_count
from {{ ref('fct_trade') }}
having count(*) = 0
