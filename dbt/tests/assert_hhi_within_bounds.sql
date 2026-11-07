-- The HHI lies between 0 and 10 000, and partner shares between 0 and 1.
select *
from {{ ref('mart_concentration') }}
where hhi < 0
   or hhi > 10000
   or top_partner_share > 1
   or top5_share > 1.000001
