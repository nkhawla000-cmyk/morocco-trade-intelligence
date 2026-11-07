"""Partner segmentation: group Morocco's trading partners with k-means.

Each partner is described by four features computed over a window of years:
  - log10_trade_usd: size of the relationship (average exports + imports, log scale)
  - export_share: exports / (exports + imports); high = export market, low = supplier
  - growth_rate: compound annual growth of total trade over the window
  - automotive_export_share: share of cars, vehicle parts and wiring in exports

The window defaults to 2019-2023 because Morocco's reported values show a
series break from 2024 (see README). Features are standardised, k is chosen
by silhouette score and every segment receives a readable label.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

FEATURES = ["log10_trade_usd", "export_share", "growth_rate", "automotive_export_share"]
DEFAULT_WINDOW = list(range(2019, 2024))
MIN_TRADE_USD = 100_000_000
RANDOM_STATE = 42

ASSIGNMENT_COLUMNS = [
    "partner_code", "partner_name", "segment_id", "segment_code", "segment_label",
    "exports_avg_usd", "imports_avg_usd", *FEATURES,
]
PROFILE_COLUMNS = [
    "segment_id", "segment_code", "segment_label", "partner_count", "total_trade_avg_usd",
    "median_export_share", "median_growth_rate", "median_automotive_export_share",
    "example_partners",
]


@dataclass
class SegmentationResult:
    assignments: pd.DataFrame
    profiles: pd.DataFrame
    summary: dict = field(default_factory=dict)


def build_features(
    trade: pd.DataFrame,
    automotive: pd.DataFrame,
    years: list[int],
    min_trade_usd: float = MIN_TRADE_USD,
) -> pd.DataFrame:
    """One row per partner with the four clustering features.

    trade: partner_code, partner_name, year, flow_code (X/M), trade_value_usd (TOTAL)
    automotive: partner_code, year, trade_value_usd (exports of the focus headings)
    """
    trade = trade[trade["year"].isin(years)]
    automotive = automotive[automotive["year"].isin(years)]
    first, last = min(years), max(years)

    yearly = (
        trade.pivot_table(
            index=["partner_code", "year"], columns="flow_code",
            values="trade_value_usd", aggfunc="sum", fill_value=0.0,
        )
        .reindex(columns=["X", "M"], fill_value=0.0)
        .reset_index()
    )
    yearly["total"] = yearly["X"] + yearly["M"]
    grouped = yearly.groupby("partner_code")
    features = pd.DataFrame(
        {
            "exports_avg_usd": grouped["X"].sum() / len(years),
            "imports_avg_usd": grouped["M"].sum() / len(years),
            "exports_sum": grouped["X"].sum(),
            "first_total": yearly[yearly["year"] == first].set_index("partner_code")["total"],
            "last_total": yearly[yearly["year"] == last].set_index("partner_code")["total"],
        }
    )
    names = trade.drop_duplicates("partner_code").set_index("partner_code")["partner_name"]
    features["partner_name"] = names
    auto_sum = automotive.groupby("partner_code")["trade_value_usd"].sum()
    features["auto_exports_sum"] = auto_sum.reindex(features.index).fillna(0.0)

    features["total_avg_usd"] = features["exports_avg_usd"] + features["imports_avg_usd"]
    features = features[
        (features["total_avg_usd"] >= min_trade_usd)
        & (features["first_total"] > 0)
        & (features["last_total"] > 0)
    ].copy()
    periods = last - first
    features["log10_trade_usd"] = np.log10(features["total_avg_usd"])
    features["export_share"] = features["exports_avg_usd"] / features["total_avg_usd"]
    features["growth_rate"] = (features["last_total"] / features["first_total"]) ** (1 / periods) - 1
    features["automotive_export_share"] = (
        features["auto_exports_sum"] / features["exports_sum"].where(features["exports_sum"] > 0)
    ).fillna(0.0).clip(0, 1)
    return features.reset_index()[
        ["partner_code", "partner_name", "exports_avg_usd", "imports_avg_usd", "total_avg_usd", *FEATURES]
    ]


def describe_segment(total_trade_usd: float, export_share: float, growth: float, auto_share: float) -> str:
    """Readable French label built from the segment's median profile."""
    if total_trade_usd >= 2e9:
        size = "Grands partenaires"
    elif total_trade_usd >= 5e8:
        size = "Partenaires intermédiaires"
    else:
        size = "Petits partenaires"
    if export_share >= 0.7:
        role = "débouchés à l'export"
    elif export_share <= 0.3:
        role = "fournisseurs"
    else:
        role = "échanges équilibrés"
    label = f"{size} — {role}"
    if auto_share >= 0.25:
        label += ", orientés automobile"
    if growth >= 0.10:
        label += ", en forte croissance"
    elif growth < 0:
        label += ", en recul"
    return label


def segment_partners(features: pd.DataFrame, k_range: range = range(3, 7)) -> SegmentationResult:
    """Cluster partners with k-means; k is the value with the best silhouette score."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    candidates = [k for k in k_range if 2 <= k < len(features)]
    if not candidates:
        return SegmentationResult(
            pd.DataFrame(columns=ASSIGNMENT_COLUMNS),
            pd.DataFrame(columns=PROFILE_COLUMNS),
            {"status": "skipped", "reason": f"only {len(features)} partners"},
        )
    matrix = StandardScaler().fit_transform(features[FEATURES])
    scores = {}
    for k in candidates:
        labels = KMeans(n_clusters=k, n_init=20, random_state=RANDOM_STATE).fit_predict(matrix)
        scores[k] = float(silhouette_score(matrix, labels))
    best_k = max(scores, key=lambda k: (round(scores[k], 6), -k))
    labels = KMeans(n_clusters=best_k, n_init=20, random_state=RANDOM_STATE).fit_predict(matrix)

    data = features.assign(cluster=labels)
    # Number segments by decreasing trade size so that ids are stable and meaningful.
    order = data.groupby("cluster")["total_avg_usd"].median().sort_values(ascending=False).index
    data["segment_id"] = data["cluster"].map({cluster: rank + 1 for rank, cluster in enumerate(order)})

    profiles = []
    for segment_id, group in data.groupby("segment_id"):
        top = group.sort_values("total_avg_usd", ascending=False)["partner_name"].head(4)
        profiles.append(
            {
                "segment_id": int(segment_id),
                "partner_count": len(group),
                "total_trade_avg_usd": float(group["total_avg_usd"].median()),
                "median_export_share": float(group["export_share"].median()),
                "median_growth_rate": float(group["growth_rate"].median()),
                "median_automotive_export_share": float(group["automotive_export_share"].median()),
                "example_partners": ", ".join(top),
            }
        )
    profiles = pd.DataFrame(profiles)
    profiles["segment_code"] = "S" + profiles["segment_id"].astype(str)
    profiles["segment_label"] = [
        describe_segment(row.total_trade_avg_usd, row.median_export_share,
                         row.median_growth_rate, row.median_automotive_export_share)
        for row in profiles.itertuples()
    ]
    duplicated = profiles["segment_label"].duplicated(keep=False)
    profiles.loc[duplicated, "segment_label"] += " (segment " + profiles.loc[duplicated, "segment_id"].astype(str) + ")"

    data = data.merge(profiles[["segment_id", "segment_code", "segment_label"]], on="segment_id")
    assignments = data.sort_values(["segment_id", "total_avg_usd"], ascending=[True, False])[ASSIGNMENT_COLUMNS]
    summary = {
        "status": "done",
        "partners": len(features),
        "k": best_k,
        "silhouette": round(scores[best_k], 3),
        "silhouette_by_k": {str(k): round(v, 3) for k, v in scores.items()},
    }
    return SegmentationResult(assignments.reset_index(drop=True), profiles[PROFILE_COLUMNS], summary)


def run_segmentation(database, window: list[int] | None = None, morocco: int = 504) -> dict:
    """Read the warehouse, segment partners and write two tables back."""
    import duckdb

    with duckdb.connect(str(database)) as con:
        available = [row[0] for row in con.execute("SELECT year FROM main.dim_year ORDER BY year").fetchall()]
        years = [y for y in (window or DEFAULT_WINDOW) if y in available]
        base = f"""
            FROM main.fct_trade AS f
            JOIN main.dim_country AS c ON c.country_code = f.partner_code
            JOIN main.dim_product AS p ON p.cmd_code = f.cmd_code
            WHERE f.reporter_code = {morocco} AND NOT c.is_world AND NOT c.is_special_area
        """
        trade = con.execute(
            "SELECT f.partner_code, c.country_name AS partner_name, f.year, f.flow_code, f.trade_value_usd "
            + base + " AND p.product_level = 'Total'"
        ).df()
        automotive = con.execute(
            "SELECT f.partner_code, f.year, sum(f.trade_value_usd) AS trade_value_usd "
            + base + " AND p.focus_group = 'Automotive' AND f.flow_code = 'X' GROUP BY 1, 2"
        ).df()
        if len(years) >= 2:
            result = segment_partners(build_features(trade, automotive, years))
        else:
            result = segment_partners(pd.DataFrame(columns=FEATURES))
            result.summary["reason"] = "fewer than two years in the segmentation window"
        result.summary["window"] = years
        assignments, profiles = result.assignments, result.profiles  # noqa: F841 (used by DuckDB)
        con.execute("CREATE OR REPLACE TABLE main.mart_partner_segments AS SELECT * FROM assignments")
        con.execute("CREATE OR REPLACE TABLE main.mart_segment_profiles AS SELECT * FROM profiles")
    return result.summary
