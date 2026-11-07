import numpy as np
import pandas as pd

from mti.segmentation import FEATURES, build_features, describe_segment, segment_partners

YEARS = [2019, 2020, 2021, 2022, 2023]


def synthetic_trade():
    """Three clear groups: big export markets, suppliers, small growing partners."""
    rows, auto = [], []
    rng = np.random.default_rng(0)
    groups = {
        "market": dict(codes=range(1, 6), exports=4e9, imports=1e9, growth=0.03, auto=0.5),
        "supplier": dict(codes=range(11, 16), exports=3e8, imports=3e9, growth=0.02, auto=0.0),
        "small": dict(codes=range(21, 26), exports=1.5e8, imports=1.5e8, growth=0.25, auto=0.05),
    }
    for group in groups.values():
        for code in group["codes"]:
            noise = 1 + rng.normal(0, 0.03)
            for i, year in enumerate(YEARS):
                factor = (1 + group["growth"]) ** i * noise
                exports = group["exports"] * factor
                rows.append((code, f"P{code}", year, "X", exports))
                rows.append((code, f"P{code}", year, "M", group["imports"] * factor))
                auto.append((code, year, exports * group["auto"]))
    trade = pd.DataFrame(rows, columns=["partner_code", "partner_name", "year", "flow_code", "trade_value_usd"])
    automotive = pd.DataFrame(auto, columns=["partner_code", "year", "trade_value_usd"])
    return trade, automotive


def test_features_are_computed_per_partner():
    trade, automotive = synthetic_trade()
    features = build_features(trade, automotive, YEARS)
    assert len(features) == 15
    market = features.set_index("partner_code").loc[1]
    assert 0.75 < market["export_share"] < 0.85
    assert abs(market["automotive_export_share"] - 0.5) < 1e-9
    assert abs(market["growth_rate"] - 0.03) < 1e-6


def test_small_partners_are_filtered_out():
    trade, automotive = synthetic_trade()
    features = build_features(trade, automotive, YEARS, min_trade_usd=1e10)
    assert features.empty


def test_segmentation_recovers_the_three_groups():
    trade, automotive = synthetic_trade()
    result = segment_partners(build_features(trade, automotive, YEARS))
    assert result.summary["k"] == 3
    segments = result.assignments.set_index("partner_code")["segment_id"]
    for codes in (range(1, 6), range(11, 16), range(21, 26)):
        assert segments.loc[list(codes)].nunique() == 1
    assert set(FEATURES) <= set(result.assignments.columns)
    assert result.profiles["partner_count"].sum() == 15


def test_segmentation_is_reproducible():
    trade, automotive = synthetic_trade()
    features = build_features(trade, automotive, YEARS)
    first = segment_partners(features).assignments
    second = segment_partners(features).assignments
    pd.testing.assert_frame_equal(first, second)


def test_too_few_partners_are_skipped():
    trade, automotive = synthetic_trade()
    features = build_features(trade, automotive, YEARS).head(2)
    result = segment_partners(features)
    assert result.summary["status"] == "skipped"
    assert result.assignments.empty


def test_labels_describe_the_profile():
    assert describe_segment(5e9, 0.8, 0.02, 0.4) == "Grands partenaires — débouchés à l'export, orientés automobile"
    assert describe_segment(3e8, 0.2, -0.05, 0.0) == "Petits partenaires — fournisseurs, en recul"
