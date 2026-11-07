-- Fact table of the star schema.
-- Grain: one row per reporter, partner, flow, year and product code.
-- Product codes mix levels (TOTAL, chapters, headings): never sum values
-- across levels; filter on dim_product.product_level first.

select
    md5(concat_ws('|', reporter_code, partner_code, flow_code, year, cmd_code)) as trade_key,
    year,
    reporter_code,
    partner_code,
    flow_code,
    cmd_code,
    trade_value_usd,
    cif_value_usd,
    fob_value_usd,
    net_weight_kg,
    is_reported,
    source_dataset,
    fetched_at
from {{ ref('stg_comtrade__trade_flows') }}
