-- Clean, typed and deduplicated trade records.
-- Grain: one row per reporter, partner, flow, year and product code.

with source as (

    select * from {{ source('comtrade', 'comtrade_records') }}

),

renamed as (

    select
        cast(refYear as integer)        as year,
        cast(reporterCode as integer)   as reporter_code,
        reporterISO                     as reporter_iso,
        reporterDesc                    as reporter_name,
        upper(flowCode)                 as flow_code,
        cast(partnerCode as integer)    as partner_code,
        partnerISO                      as partner_iso,
        partnerDesc                     as partner_name,
        cast(cmdCode as varchar)        as cmd_code,
        cmdDesc                         as cmd_description,
        cast(aggrLevel as integer)      as hs_level,
        cast(primaryValue as double)    as trade_value_usd,
        cast(cifvalue as double)        as cif_value_usd,
        cast(fobvalue as double)        as fob_value_usd,
        cast(netWgt as double)          as net_weight_kg,
        cast(isReported as boolean)     as is_reported,
        _dataset                        as source_dataset,
        _request_id                     as source_request_id,
        cast(_fetched_at as timestamp)  as fetched_at
    from source
    where freqCode = 'A'

),

deduplicated as (

    -- The same record can be fetched twice (for example by a re-run);
    -- keep the most recent copy. Conflicting copies are caught by a data test.
    select
        *,
        row_number() over (
            partition by reporter_code, partner_code, flow_code, year, cmd_code
            order by fetched_at desc, source_request_id
        ) as copy_number
    from renamed

)

select * exclude (copy_number)
from deduplicated
where copy_number = 1
