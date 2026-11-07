-- The staging model keeps one copy per key. This test fails if two copies of
-- the same key carry different values: deduplication would then hide a real problem.
select
    reporterCode,
    partnerCode,
    flowCode,
    refYear,
    cmdCode,
    count(*) as copies,
    count(distinct primaryValue) as distinct_values
from {{ source('comtrade', 'comtrade_records') }}
group by reporterCode, partnerCode, flowCode, refYear, cmdCode
having count(distinct primaryValue) > 1
