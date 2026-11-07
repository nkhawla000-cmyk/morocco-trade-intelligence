"""Generate the Power BI project of Morocco Trade Intelligence.

Output (Power BI Project format, opened with Power BI Desktop):
    powerbi/MoroccoTradeIntelligence.pbip
    powerbi/MoroccoTradeIntelligence.SemanticModel/   semantic model in TMDL
    powerbi/MoroccoTradeIntelligence.Report/          report in PBIR (JSON)

The semantic model reads the tables published in data/marts on GitHub, so a
refresh in Power BI Desktop always loads the latest monthly data.

Run from the repository root:  python tools/build_powerbi.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "powerbi"
NAME = "MoroccoTradeIntelligence"
BASE_URL = "https://raw.githubusercontent.com/nkhawla000-cmyk/morocco-trade-intelligence/main/data/marts/"
NAMESPACE = uuid.UUID("6b1d6a8e-2f0e-4f39-9c55-3a8f6d0c2b11")

INT, NUM, TEXT, BOOL = "int64", "double", "string", "boolean"
M_TYPES = {INT: "Int64.Type", NUM: "type number", TEXT: "type text", BOOL: "type logical"}


def tag(*parts: str) -> str:
    """Stable lineage tag (UUID) so regenerating the project gives the same files."""
    return str(uuid.uuid5(NAMESPACE, "|".join(parts)))


def object_id(*parts: str) -> str:
    """Stable 20-character name for pages and visuals."""
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:20]


# --------------------------------------------------------------------------
# Semantic model
# --------------------------------------------------------------------------

def table(name, file, columns, filter_m=None, measures=(), derived=()):
    """filter_m: Power Query row filter on the step named Prepared.
    derived: (name, M expression) text columns added in Power Query, used for French labels."""
    return {"name": name, "file": file, "columns": columns, "filter_m": filter_m,
            "measures": list(measures), "derived": list(derived)}


FLOW_LABEL = ("flow_label", 'if [flow_code] = "X" then "Exportations" else "Importations"')
LEVEL_LABEL = ("concentration_label",
               'if [concentration_level] = "Low" then "Faible" '
               'else if [concentration_level] = "Moderate" then "Modérée" else "Élevée"')


def yes_no(name: str, column: str) -> tuple[str, str]:
    return (name, f'if [{column}] = true then "Oui" else "Non"')


def measure(name, expression, fmt):
    return {"name": name, "expression": expression.strip("\n"), "format": fmt}


OVERVIEW = "mart_trade_overview"
CONCENTRATION_COLUMNS = [
        ("year", INT), ("flow_code", TEXT), ("cmd_code", TEXT), ("product_description", TEXT), ("scope_label", TEXT),
        ("partner_count", INT), ("total_value_usd", NUM), ("hhi", NUM), ("concentration_level", TEXT),
        ("top_partner_code", INT), ("top_partner_name", TEXT), ("top_partner_share", NUM), ("top5_share", NUM),
]
TABLES = [
    table("dim_year", "dim_year.parquet", [("year", INT), ("is_latest_year", BOOL)], measures=[
        measure("Année affichée", "SELECTEDVALUE ( dim_year[year], MAX ( dim_year[year] ) )", "0"),
    ]),
    table("dim_flow", "dim_flow.parquet", [("flow_code", TEXT), ("flow_name", TEXT), ("flow_name_fr", TEXT)]),
    table("dim_country", "dim_country.parquet", [
        ("country_code", INT), ("iso3", TEXT), ("country_name", TEXT), ("is_world", BOOL),
        ("is_special_area", BOOL), ("is_morocco", BOOL), ("is_mirror_partner", BOOL),
    ]),
    table("dim_product", "dim_product.parquet", [
        ("cmd_code", TEXT), ("product_description", TEXT), ("product_level", TEXT), ("hs_chapter", TEXT),
        ("hs_level", INT), ("focus_group", TEXT), ("focus_label", TEXT), ("focus_label_fr", TEXT),
        ("is_focus_product", BOOL),
    ]),
    table("fct_trade", "fct_trade.parquet", [
        ("year", INT), ("reporter_code", INT), ("partner_code", INT), ("flow_code", TEXT), ("cmd_code", TEXT),
        ("trade_value_usd", NUM), ("cif_value_usd", NUM), ("fob_value_usd", NUM), ("net_weight_kg", NUM),
        ("is_reported", BOOL), ("source_dataset", TEXT),
    ], measures=[
        measure("Exportations automobiles (USD)", """
CALCULATE (
    SUM ( fct_trade[trade_value_usd] ),
    fct_trade[reporter_code] = 504,
    fct_trade[flow_code] = "X",
    dim_product[focus_group] = "Automotive",
    dim_country[is_world] = TRUE ()
)""", "#,0"),
        measure("Importations automobiles (USD)", """
CALCULATE (
    SUM ( fct_trade[trade_value_usd] ),
    fct_trade[reporter_code] = 504,
    fct_trade[flow_code] = "M",
    dim_product[focus_group] = "Automotive",
    dim_country[is_world] = TRUE ()
)""", "#,0"),
    ]),
    table(OVERVIEW, "mart_trade_overview.csv", [
        ("year", INT), ("exports_usd", NUM), ("imports_usd", NUM), ("trade_balance_usd", NUM),
        ("coverage_ratio", NUM), ("exports_growth", NUM), ("imports_growth", NUM), ("possible_series_break", BOOL),
    ], derived=[yes_no("series_break_label", "possible_series_break")], measures=[
        measure("Exportations (USD)", "SUM ( mart_trade_overview[exports_usd] )", "#,0"),
        measure("Importations (USD)", "SUM ( mart_trade_overview[imports_usd] )", "#,0"),
        measure("Solde commercial (USD)", "SUM ( mart_trade_overview[trade_balance_usd] )", "#,0"),
        measure("Dernière année", "MAX ( mart_trade_overview[year] )", "0"),
        measure("Exportations", """
VAR LastYear = MAX ( mart_trade_overview[year] )
RETURN
    CALCULATE ( [Exportations (USD)], mart_trade_overview[year] = LastYear )""", "#,0"),
        measure("Importations", """
VAR LastYear = MAX ( mart_trade_overview[year] )
RETURN
    CALCULATE ( [Importations (USD)], mart_trade_overview[year] = LastYear )""", "#,0"),
        measure("Solde commercial", """
[Exportations] - [Importations]""", "#,0"),
        measure("Taux de couverture", """
DIVIDE ( [Exportations], [Importations] )""", "0.0%"),
    ]),
    table("mart_partner_shares", "mart_partner_shares.csv", [
        ("year", INT), ("flow_code", TEXT), ("partner_code", INT), ("partner_name", TEXT), ("is_special_area", BOOL),
        ("trade_value_usd", NUM), ("world_value_usd", NUM), ("share_of_world", NUM), ("partner_rank", INT),
    ], measures=[
        measure(f"Part des {label}", f"""
VAR SelectedYear = [Année affichée]
RETURN
    CALCULATE (
        SUM ( mart_partner_shares[share_of_world] ),
        mart_partner_shares[year] = SelectedYear,
        mart_partner_shares[flow_code] = "{flow}",
        mart_partner_shares[partner_rank] <= {top},
        mart_partner_shares[is_special_area] = FALSE ()
    )""", "0.0%")
        for label, flow, top in [
            ("exportations (top 10)", "X", 10), ("importations (top 10)", "M", 10),
            ("5 premiers clients", "X", 5), ("5 premiers fournisseurs", "M", 5),
        ]
    ]),
    table("mart_chapter_structure", "mart_chapter_structure.csv", [
        ("year", INT), ("flow_code", TEXT), ("hs_chapter", TEXT), ("product_description", TEXT),
        ("chapter_label", TEXT), ("trade_value_usd", NUM), ("share_of_chapters", NUM), ("chapter_rank", INT),
        ("growth_vs_previous_year", NUM),
    ], measures=[
        measure(f"Part des {label} par chapitre (top 10)", f"""
VAR SelectedYear = [Année affichée]
RETURN
    CALCULATE (
        SUM ( mart_chapter_structure[share_of_chapters] ),
        mart_chapter_structure[year] = SelectedYear,
        mart_chapter_structure[flow_code] = "{flow}",
        mart_chapter_structure[chapter_rank] <= 10
    )""", "0.0%")
        for label, flow in [("exportations", "X"), ("importations", "M")]
    ]),
    table("mart_concentration", "mart_concentration.csv", CONCENTRATION_COLUMNS, derived=[FLOW_LABEL, LEVEL_LABEL], measures=[
        measure("HHI exportations", """
CALCULATE ( AVERAGE ( mart_concentration[hhi] ), mart_concentration[flow_code] = "X" )""", "#,0"),
        measure("HHI importations", """
CALCULATE ( AVERAGE ( mart_concentration[hhi] ), mart_concentration[flow_code] = "M" )""", "#,0"),
    ]),
    table("mart_concentration_latest", "mart_concentration.csv", CONCENTRATION_COLUMNS,
          filter_m="Table.SelectRows(Prepared, each [year] = List.Max(Prepared[year]))",
          derived=[FLOW_LABEL, LEVEL_LABEL]),
    table("mart_mirror_gaps", "mart_mirror_gaps.csv", [
        ("year", INT), ("flow_code", TEXT), ("comparison", TEXT), ("counterpart_code", INT),
        ("counterpart_name", TEXT), ("declared_value_usd", NUM), ("mirror_value_usd", NUM), ("gap_usd", NUM),
        ("gap_ratio", NUM), ("needs_review", BOOL),
    ], derived=[FLOW_LABEL, yes_no("review_label", "needs_review")], measures=[
        measure("Comparaisons miroir", "COUNTROWS ( mart_mirror_gaps )", "0"),
        measure("Comparaisons à examiner", """
CALCULATE ( COUNTROWS ( mart_mirror_gaps ), mart_mirror_gaps[needs_review] = TRUE () )""", "0"),
    ]),
    table("mart_flow_anomalies", "mart_flow_anomalies.csv", [
        ("year", INT), ("flow_code", TEXT), ("partner_code", INT), ("partner_name", TEXT),
        ("previous_value_usd", NUM), ("trade_value_usd", NUM), ("change_ratio", NUM),
        ("typical_change_ratio", NUM), ("robust_z", NUM), ("partners_compared", INT), ("is_anomaly", BOOL),
    ], filter_m="Table.SelectRows(Prepared, each [is_anomaly] = true)", derived=[FLOW_LABEL], measures=[
        measure("Anomalies détectées", "COUNTROWS ( mart_flow_anomalies )", "0"),
    ]),
    table("mart_partner_segments", "mart_partner_segments.csv", [
        ("partner_code", INT), ("partner_name", TEXT), ("segment_id", INT), ("segment_code", TEXT), ("segment_label", TEXT),
        ("exports_avg_usd", NUM), ("imports_avg_usd", NUM), ("log10_trade_usd", NUM), ("export_share", NUM),
        ("growth_rate", NUM), ("automotive_export_share", NUM),
    ], measures=[
        measure("Part des exportations (moyenne)", "AVERAGE ( mart_partner_segments[export_share] )", "0.0%"),
        measure("Croissance annuelle (moyenne)", "AVERAGE ( mart_partner_segments[growth_rate] )", "0.0%"),
        measure("Commerce moyen (USD)", """
SUM ( mart_partner_segments[exports_avg_usd] ) + SUM ( mart_partner_segments[imports_avg_usd] )""", "#,0"),
        measure("Partenaires segmentés", "COUNTROWS ( mart_partner_segments )", "0"),
    ]),
    table("mart_segment_profiles", "mart_segment_profiles.csv", [
        ("segment_id", INT), ("segment_code", TEXT), ("segment_label", TEXT), ("partner_count", INT), ("total_trade_avg_usd", NUM),
        ("median_export_share", NUM), ("median_growth_rate", NUM), ("median_automotive_export_share", NUM),
        ("example_partners", TEXT),
    ]),
]

RELATIONSHIPS = [
    ("fct_trade", "year", "dim_year", "year"),
    ("fct_trade", "flow_code", "dim_flow", "flow_code"),
    ("fct_trade", "partner_code", "dim_country", "country_code"),
    ("fct_trade", "cmd_code", "dim_product", "cmd_code"),
    ("mart_concentration", "year", "dim_year", "year"),
    ("mart_mirror_gaps", "year", "dim_year", "year"),
    ("mart_flow_anomalies", "year", "dim_year", "year"),
]


def column_format(name: str, kind: str) -> str | None:
    if kind == INT:
        return "0"
    if kind != NUM:
        return None
    if name.endswith("_usd") or name.endswith("_kg") or name == "hhi":
        return "#,0"
    if any(word in name for word in ("share", "ratio", "growth", "rate")):
        return "0.0%"
    return "0.00"


def m_source(spec: dict) -> list[str]:
    url = BASE_URL + spec["file"]
    names = [name for name, _ in spec["columns"]]
    types = ", ".join(f'{{"{name}", {M_TYPES[kind]}}}' for name, kind in spec["columns"])
    if spec["file"].endswith(".parquet"):
        lines = [
            "let",
            f'    Source = Parquet.Document(Binary.Buffer(Web.Contents("{url}"))),',
            "    Selected = Table.SelectColumns(Source, {" + ", ".join(f'"{n}"' for n in names) + "}),",
            f'    Typed = Table.TransformColumnTypes(Selected, {{{types}}}, "en-US")',
        ]
    else:
        lines = [
            "let",
            f'    Source = Csv.Document(Web.Contents("{url}"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
            "    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
            '    Blanks = Table.ReplaceValue(Headers, "", null, Replacer.ReplaceValue, {'
            + ", ".join(f'"{n}"' for n in names) + "}),",
            f'    Typed = Table.TransformColumnTypes(Blanks, {{{types}}}, "en-US")',
        ]
    previous = "Typed"
    for number, (name, expression) in enumerate(spec["derived"], start=1):
        lines[-1] += ","
        lines.append(f'    Derived{number} = Table.AddColumn({previous}, "{name}", each {expression}, type text)')
        previous = f"Derived{number}"
    lines[-1] += ","
    lines.append(f"    Prepared = {previous}")
    if spec["filter_m"]:
        lines[-1] += ","
        lines += [f"    Result = {spec['filter_m']}", "in", "    Result"]
    else:
        lines += ["in", "    Prepared"]
    return lines


def quote(name: str) -> str:
    return name if name.replace("_", "").isalnum() and name.isascii() else "'" + name.replace("'", "''") + "'"


def table_tmdl(spec: dict) -> str:
    t = spec["name"]
    out = [f"table {t}", f"\tlineageTag: {tag('table', t)}", ""]
    for m in spec["measures"]:
        out.append(f"\tmeasure {quote(m['name'])} = ```")
        out += ["\t\t\t" + line for line in m["expression"].strip().splitlines()]
        out.append("\t\t\t```")
        out.append(f"\t\tformatString: {m['format']}")
        out.append(f"\t\tlineageTag: {tag('measure', t, m['name'])}")
        out.append("")
    for name, kind in spec["columns"] + [(name, TEXT) for name, _ in spec["derived"]]:
        out.append(f"\tcolumn {quote(name)}")
        out.append(f"\t\tdataType: {kind}")
        fmt = column_format(name, kind)
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out.append(f"\t\tlineageTag: {tag('column', t, name)}")
        out.append("\t\tsummarizeBy: none")
        out.append(f"\t\tsourceColumn: {name}")
        out.append("")
        out.append("\t\tannotation SummarizationSetBy = User")
        out.append("")
    out.append(f"\tpartition {t} = m")
    out.append("\t\tmode: import")
    out.append("\t\tsource =")
    out += ["\t\t\t\t" + line for line in m_source(spec)]
    out.append("")
    out.append("\tannotation PBI_ResultType = Table")
    out.append("")
    return "\n".join(out)


def write_semantic_model(folder: Path) -> None:
    definition = folder / "definition"
    (definition / "tables").mkdir(parents=True)
    (folder / "definition.pbism").write_text(json.dumps({"version": "4.1", "settings": {}}, indent=2), encoding="utf-8")
    (definition / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1567\n\n", encoding="utf-8")
    order = json.dumps([spec["name"] for spec in TABLES])
    model = [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tsourceQueryCulture: en-US",
        "\tdataAccessOptions",
        "\t\tlegacyRedirects",
        "\t\treturnErrorValuesAsNull",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",
        "",
        f"annotation PBI_QueryOrder = {order}",
        "",
    ] + [f"ref table {spec['name']}" for spec in TABLES] + [""]
    (definition / "model.tmdl").write_text("\n".join(model), encoding="utf-8")
    relationships = []
    for from_table, from_column, to_table, to_column in RELATIONSHIPS:
        relationships += [
            f"relationship {tag('relationship', from_table, from_column, to_table)}",
            f"\tfromColumn: {from_table}.{from_column}",
            f"\ttoColumn: {to_table}.{to_column}",
            "",
        ]
    (definition / "relationships.tmdl").write_text("\n".join(relationships), encoding="utf-8")
    for spec in TABLES:
        (definition / "tables" / f"{spec['name']}.tmdl").write_text(table_tmdl(spec), encoding="utf-8")


# --------------------------------------------------------------------------
# Report (PBIR)
# --------------------------------------------------------------------------

BG, HEADER, PANEL, BORDER = "#0C1728", "#10223A", "#182A43", "#2C4260"
TEXT_MAIN, TEXT_MUTED = "#F2F7FF", "#A7B9CF"
TEAL, BLUE, PINK, AMBER, VIOLET = "#53D7C2", "#77A6FF", "#FF7F9D", "#FFC86E", "#B8A5FF"
CONTAINER_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.4.0/schema.json"
CARD_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.7.0/schema.json"


def lit(value: str) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def color(hex_code: str) -> dict:
    return {"solid": {"color": lit(f"'{hex_code}'")}}


def column_field(entity: str, prop: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def measure_field(entity: str, prop: str) -> dict:
    return {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def projection(field, active: bool = False) -> dict:
    """field, or (field, French header shown in the visual)."""
    field, display = field if isinstance(field, tuple) else (field, None)
    kind = "Column" if "Column" in field else "Measure"
    entity = field[kind]["Expression"]["SourceRef"]["Entity"]
    prop = field[kind]["Property"]
    item = {"field": field, "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}
    if display:
        item["displayName"] = display
    if active:
        item["active"] = True
    return item


def panel_objects(title: str | None) -> dict:
    objects = {
        "background": [{"properties": {"show": lit("true"), "color": color(PANEL), "transparency": lit("0D")}}],
        "border": [{"properties": {"show": lit("true"), "color": color(BORDER), "radius": lit("12D"), "width": lit("1D")}}],
        "padding": [{"properties": {"left": lit("14D"), "right": lit("14D"), "top": lit("9D"), "bottom": lit("7D")}}],
        "visualHeader": [{"properties": {"show": lit("false")}}],
        "subTitle": [{"properties": {"show": lit("false")}}],
    }
    if title:
        objects["title"] = [{"properties": {
            "show": lit("true"), "text": lit("'" + title.replace("'", "''") + "'"), "fontColor": color(TEXT_MAIN),
            "fontSize": lit("12D"), "fontFamily": lit("'Segoe UI Semibold'"), "bold": lit("true"),
        }}]
    else:
        objects["title"] = [{"properties": {"show": lit("false")}}]
    return objects


class Page:
    def __init__(self, key: str, display_name: str, title: str, subtitle: str, footer: str):
        self.name = object_id("page", key)
        self.display_name = display_name
        self.visuals: list[dict] = []
        self.z = 0
        self.shape(0, 0, 1280, 100, HEADER)
        self.shape(0, 0, 10, 100, TEAL)
        self.textbox(40, 14, 1100, 44, title, 28, TEXT_MAIN, "Segoe UI Semibold")
        self.textbox(42, 58, 1180, 30, subtitle, 14, TEXT_MUTED, "Segoe UI")
        self.textbox(40, 684, 1200, 28, footer, 12, TEXT_MUTED, "Segoe UI")

    def add(self, x, y, w, h, visual: dict, schema: str = CONTAINER_SCHEMA) -> None:
        self.z += 1
        key = f"{len(self.visuals)}-{visual['visualType']}"
        self.visuals.append({
            "$schema": schema,
            "name": object_id("visual", self.name, key),
            "position": {"x": x, "y": y, "z": self.z * 100, "height": h, "width": w, "tabOrder": self.z},
            "visual": visual,
        })

    def shape(self, x, y, w, h, fill) -> None:
        self.add(x, y, w, h, {
            "visualType": "shape",
            "objects": {
                "shape": [{"properties": {"tileShape": lit("'rectangle'")}}],
                "fill": [{"properties": {"fillColor": color(fill), "transparency": lit("0D")}, "selector": {"id": "default"}}],
                "outline": [{"properties": {"show": lit("false")}, "selector": {"id": "default"}}],
            },
            "visualContainerObjects": {
                "background": [{"properties": {"show": lit("false")}}],
                "border": [{"properties": {"show": lit("false")}}],
                "padding": [{"properties": {"left": lit("0D"), "right": lit("0D"), "top": lit("0D"), "bottom": lit("0D")}}],
            },
        })

    def textbox(self, x, y, w, h, text, size, text_color, font) -> None:
        self.add(x, y, w, h, {
            "visualType": "textbox",
            "objects": {"general": [{"properties": {"paragraphs": [{
                "textRuns": [{"value": text, "textStyle": {"fontFamily": font, "fontSize": f"{size}px", "color": text_color}}],
                "horizontalTextAlignment": "left",
            }]}}]},
            "visualContainerObjects": {
                "title": [{"properties": {"show": lit("false")}}],
                "background": [{"properties": {"show": lit("false")}}],
                "border": [{"properties": {"show": lit("false")}}],
                "padding": [{"properties": {"left": lit("0D"), "right": lit("0D"), "top": lit("0D"), "bottom": lit("0D")}}],
            },
        })

    def card(self, x, y, w, h, entity, measure_name, accent, billions=False) -> None:
        value = {"fontColor": color(TEXT_MAIN), "fontSize": lit("24D")}
        if billions:
            value["labelDisplayUnits"] = lit("1000000000D")
            value["labelPrecision"] = lit("1L")
        else:
            value["labelDisplayUnits"] = lit("1D")
        self.add(x, y, w, h, {
            "visualType": "cardVisual",
            "query": {"queryState": {"Data": {"projections": [projection(measure_field(entity, measure_name))]}}},
            "objects": {
                "accentBar": [{"properties": {"show": lit("true"), "color": color(accent), "width": lit("4D"),
                                              "position": lit("'Left'")}, "selector": {"id": "default"}}],
                "outline": [{"properties": {"show": lit("false")}, "selector": {"id": "default"}}],
                "value": [{"properties": value, "selector": {"id": "default"}}],
                "label": [{"properties": {"fontColor": color(TEXT_MUTED), "fontSize": lit("12D"), "show": lit("true")},
                           "selector": {"id": "default"}}],
            },
            "visualContainerObjects": panel_objects(None),
            "drillFilterOtherVisuals": True,
        }, schema=CARD_SCHEMA)

    def slicer(self, x, y, w, h, entity, column, title) -> None:
        self.add(x, y, w, h, {
            "visualType": "slicer",
            "query": {"queryState": {"Values": {"projections": [projection(column_field(entity, column), active=True)]}}},
            "objects": {
                "data": [{"properties": {"mode": lit("'Dropdown'")}}],
                "selection": [{"properties": {"singleSelect": lit("true")}}],
                "header": [{"properties": {"show": lit("false")}}],
                "items": [{"properties": {"fontColor": color(TEXT_MAIN), "fontSize": lit("13D")}}],
            },
            "visualContainerObjects": panel_objects(title),
            "drillFilterOtherVisuals": True,
        })

    def chart(self, x, y, w, h, visual_type, title, category, values, series=None, sort_by=None,
              data_color=None, labels=False, categorical=False) -> None:
        state = {
            "Category": {"projections": [projection(category, active=True)]},
            "Y": {"projections": [projection(v) for v in values]},
        }
        if series:
            state["Series"] = {"projections": [projection(series)]}
        query = {"queryState": state}
        if sort_by:
            query["sortDefinition"] = {"sort": [{"field": sort_by, "direction": "Descending"}], "isDefaultSort": True}
        category_axis = {"fontSize": lit("11D"), "labelColor": color("#DCE9F8"), "showAxisTitle": lit("false")}
        if categorical:
            category_axis["axisType"] = lit("'Categorical'")
        objects = {
            "categoryAxis": [{"properties": category_axis}],
            "valueAxis": [{"properties": {"fontSize": lit("11D"), "labelColor": color("#B8CBE1"),
                                          "showAxisTitle": lit("false")}}],
            "legend": [{"properties": {"show": lit("true" if (series or len(values) > 1) else "false"),
                                       "showTitle": lit("false"), "labelColor": color("#DCE9F8"),
                                       "fontSize": lit("11D")}}],
        }
        if data_color:
            objects["dataPoint"] = [{"properties": {"defaultColor": color(data_color)}}]
        if labels:
            objects["labels"] = [{"properties": {"show": lit("true"), "color": color(TEXT_MAIN), "fontSize": lit("10D")}}]
        self.add(x, y, w, h, {
            "visualType": visual_type,
            "query": query,
            "objects": objects,
            "visualContainerObjects": panel_objects(title),
            "drillFilterOtherVisuals": True,
        })

    def table(self, x, y, w, h, title, fields, sort_by=None, ascending=False) -> None:
        query = {"queryState": {"Values": {"projections": [projection(f) for f in fields]}}}
        if sort_by:
            query["sortDefinition"] = {"sort": [{"field": sort_by, "direction": "Ascending" if ascending else "Descending"}]}
        self.add(x, y, w, h, {
            "visualType": "tableEx",
            "query": query,
            "objects": {
                "columnHeaders": [{"properties": {"fontSize": lit("11D"), "fontColor": color(TEXT_MAIN),
                                                  "backColor": color(HEADER)}}],
                "values": [{"properties": {"fontSize": lit("10D"), "wordWrap": lit("true"), "fontColorPrimary": color(TEXT_MAIN),
                                           "backColorPrimary": color(PANEL), "fontColorSecondary": color(TEXT_MAIN),
                                           "backColorSecondary": color("#1D3250")}}],
            },
            "visualContainerObjects": panel_objects(title),
            "drillFilterOtherVisuals": True,
        })

    def scatter(self, x, y, w, h, title, details, legend, x_measure, y_measure, size_measure) -> None:
        self.add(x, y, w, h, {
            "visualType": "scatterChart",
            "query": {"queryState": {
                "Category": {"projections": [projection(details, active=True)]},
                "Series": {"projections": [projection(legend)]},
                "X": {"projections": [projection(x_measure)]},
                "Y": {"projections": [projection(y_measure)]},
                "Size": {"projections": [projection(size_measure)]},
            }},
            "objects": {
                "categoryAxis": [{"properties": {"fontSize": lit("11D"), "labelColor": color("#DCE9F8")}}],
                "valueAxis": [{"properties": {"fontSize": lit("11D"), "labelColor": color("#B8CBE1")}}],
                "legend": [{"properties": {"show": lit("true"), "showTitle": lit("false"), "labelColor": color("#DCE9F8"),
                                           "fontSize": lit("11D"), "position": lit("'Right'")}}],
            },
            "visualContainerObjects": panel_objects(title),
            "drillFilterOtherVisuals": True,
        })

    def page_json(self) -> dict:
        background = {"color": color(BG), "transparency": lit("0D")}
        return {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
            "name": self.name,
            "displayName": self.display_name,
            "displayOption": "FitToPage",
            "width": 1280,
            "height": 720,
            "objects": {"background": [{"properties": background}], "outspace": [{"properties": background}]},
        }


SOURCE_NOTE = "Source : UN Comtrade (API publique), traitement Morocco Trade Intelligence. Valeurs en dollars US courants."


def build_pages() -> list[Page]:
    C, M = column_field, measure_field
    pages = []

    p = Page("overview", "Vue d'ensemble", "01 / VUE D'ENSEMBLE",
             "Commerce extérieur du Maroc avec le monde, 2019–2025 · cartes : dernière année disponible",
             "Attention : rupture de série à partir de 2024 dans les données déclarées par le Maroc "
             "(voir la page Qualité des données). " + SOURCE_NOTE)
    cards = [("Dernière année", TEAL, False), ("Exportations", TEAL, True), ("Importations", BLUE, True),
             ("Solde commercial", PINK, True), ("Taux de couverture", AMBER, False)]
    for i, (name, accent, billions) in enumerate(cards):
        p.card(20 + i * 248, 114, 236, 110, OVERVIEW, name, accent, billions=billions)
    p.chart(20, 240, 760, 430, "lineChart", "Exportations et importations (USD)", C(OVERVIEW, "year"),
            [M(OVERVIEW, "Exportations (USD)"), M(OVERVIEW, "Importations (USD)")], categorical=True)
    p.chart(800, 240, 460, 430, "clusteredColumnChart", "Solde commercial (USD)", C(OVERVIEW, "year"),
            [M(OVERVIEW, "Solde commercial (USD)")], data_color=PINK, categorical=True)
    pages.append(p)

    shares = "mart_partner_shares"
    p = Page("partners", "Partenaires", "02 / PARTENAIRES",
             "Principaux clients et fournisseurs du Maroc · choisir une année (par défaut : la plus récente)",
             "Parts calculées sur le total mondial de l'année ; zones non spécifiées exclues du classement. " + SOURCE_NOTE)
    p.slicer(20, 112, 260, 80, "dim_year", "year", "Année")
    p.card(300, 112, 220, 80, "dim_year", "Année affichée", TEAL)
    p.card(540, 112, 350, 80, shares, "Part des 5 premiers clients", TEAL)
    p.card(910, 112, 350, 80, shares, "Part des 5 premiers fournisseurs", BLUE)
    for i, (title, measure_name, accent) in enumerate([
        ("Principaux clients : part des exportations", "Part des exportations (top 10)", TEAL),
        ("Principaux fournisseurs : part des importations", "Part des importations (top 10)", BLUE),
    ]):
        p.chart(20 + i * 630, 208, 610, 462, "clusteredBarChart", title, C(shares, "partner_name"),
                [M(shares, measure_name)], sort_by=M(shares, measure_name), data_color=accent, labels=True)
    pages.append(p)

    chapters = "mart_chapter_structure"
    p = Page("products", "Produits", "03 / PRODUITS",
             "Structure des échanges par chapitre du Système harmonisé (SH) · choisir une année",
             "Part de chaque chapitre dans le total des chapitres de l'année. " + SOURCE_NOTE)
    p.slicer(20, 112, 260, 80, "dim_year", "year", "Année")
    p.card(300, 112, 220, 80, "dim_year", "Année affichée", TEAL)
    for i, (title, measure_name, accent) in enumerate([
        ("Principaux chapitres exportés", "Part des exportations par chapitre (top 10)", TEAL),
        ("Principaux chapitres importés", "Part des importations par chapitre (top 10)", BLUE),
    ]):
        p.chart(20 + i * 630, 208, 610, 462, "clusteredBarChart", title, C(chapters, "chapter_label"),
                [M(chapters, measure_name)], sort_by=M(chapters, measure_name), data_color=accent, labels=True)
    pages.append(p)

    latest = "mart_concentration_latest"
    p = Page("automotive", "Automobile et concentration", "04 / AUTOMOBILE ET CONCENTRATION",
             "Voitures, pièces et faisceaux de câbles · concentration des partenaires (indice HHI)",
             "HHI = 10 000 × somme des parts au carré ; moins de 1 500 : faible, 1 500 à 2 500 : modérée, "
             "plus de 2 500 : élevée. " + SOURCE_NOTE)
    p.chart(20, 112, 610, 280, "clusteredColumnChart", "Exportations automobiles (USD)", C("dim_year", "year"),
            [M("fct_trade", "Exportations automobiles (USD)")], series=C("dim_product", "focus_label_fr"),
            categorical=True)
    p.chart(650, 112, 610, 280, "lineChart", "Concentration des clients à l'export (HHI)",
            C("mart_concentration", "year"), [M("mart_concentration", "HHI exportations")],
            series=C("mart_concentration", "scope_label"), categorical=True)
    p.table(20, 406, 1240, 264, "Concentration des partenaires — dernière année", [
        (C(latest, "scope_label"), "Produits"), (C(latest, "flow_label"), "Flux"),
        (C(latest, "partner_count"), "Partenaires"), (C(latest, "hhi"), "HHI"),
        (C(latest, "concentration_label"), "Concentration"), (C(latest, "top_partner_name"), "Premier partenaire"),
        (C(latest, "top_partner_share"), "Part du premier"), (C(latest, "top5_share"), "Part des 5 premiers"),
    ], sort_by=C(latest, "hhi"))
    pages.append(p)

    mirror, anomalies = "mart_mirror_gaps", "mart_flow_anomalies"
    p = Page("quality", "Qualité des données", "05 / QUALITÉ DES DONNÉES",
             "Statistiques miroirs, anomalies par partenaire et rupture de série · filtrer par année",
             "Écart miroir = (déclaration du partenaire − déclaration du Maroc) / déclaration du Maroc ; "
             "au-delà de 20 % : à examiner. Anomalie : score z robuste > 3,5. " + SOURCE_NOTE)
    p.slicer(20, 112, 260, 80, "dim_year", "year", "Année")
    p.card(300, 112, 300, 80, mirror, "Comparaisons miroir", TEAL)
    p.card(620, 112, 300, 80, mirror, "Comparaisons à examiner", PINK)
    p.card(940, 112, 320, 80, anomalies, "Anomalies détectées", AMBER)
    p.table(20, 206, 760, 270, "Statistiques miroirs : Maroc et partenaires", [
        (C(mirror, "year"), "Année"), (C(mirror, "flow_label"), "Flux du Maroc"),
        (C(mirror, "counterpart_name"), "Partenaire"), (C(mirror, "declared_value_usd"), "Déclaré par le Maroc (USD)"),
        (C(mirror, "mirror_value_usd"), "Déclaré par le partenaire (USD)"), (C(mirror, "gap_ratio"), "Écart"),
        (C(mirror, "review_label"), "À examiner"),
    ], sort_by=C(mirror, "declared_value_usd"))
    p.table(800, 206, 460, 270, "Rupture de série : variation annuelle du total", [
        (C(OVERVIEW, "year"), "Année"), (C(OVERVIEW, "exports_growth"), "Exportations"),
        (C(OVERVIEW, "imports_growth"), "Importations"), (C(OVERVIEW, "series_break_label"), "Rupture possible"),
    ], sort_by=C(OVERVIEW, "year"), ascending=True)
    p.table(20, 490, 1240, 180, "Variations anormales par partenaire", [
        (C(anomalies, "year"), "Année"), (C(anomalies, "flow_label"), "Flux"),
        (C(anomalies, "partner_name"), "Partenaire"), (C(anomalies, "previous_value_usd"), "Année précédente (USD)"),
        (C(anomalies, "trade_value_usd"), "Année (USD)"), (C(anomalies, "change_ratio"), "Variation"),
        (C(anomalies, "robust_z"), "Score z robuste"),
    ], sort_by=C(anomalies, "year"))
    pages.append(p)

    segments, profiles = "mart_partner_segments", "mart_segment_profiles"
    p = Page("segments", "Segmentation", "06 / SEGMENTATION DES PARTENAIRES",
             "k-means sur 4 indicateurs : taille, part des exportations, croissance, part automobile (2019–2023)",
             "Période 2019–2023, avant la rupture de série ; nombre de segments choisi par le score de silhouette. "
             + SOURCE_NOTE)
    p.scatter(20, 112, 1240, 334,
              "Chaque point est un pays : à droite, débouchés à l'export ; à gauche, fournisseurs ; "
              "en haut, forte croissance ; taille = volume des échanges",
              C(segments, "partner_name"), C(segments, "segment_code"),
              M(segments, "Part des exportations (moyenne)"), M(segments, "Croissance annuelle (moyenne)"),
              M(segments, "Commerce moyen (USD)"))
    p.table(20, 458, 1240, 212, "Profil des segments", [
        (C(profiles, "segment_code"), "Segment"), (C(profiles, "segment_label"), "Profil"),
        (C(profiles, "partner_count"), "Partenaires"), (C(profiles, "median_export_share"), "Part export (médiane)"),
        (C(profiles, "median_growth_rate"), "Croissance (médiane)"),
        (C(profiles, "median_automotive_export_share"), "Part automobile (médiane)"),
        (C(profiles, "example_partners"), "Exemples"),
    ], sort_by=C(profiles, "segment_code"), ascending=True)
    pages.append(p)
    return pages


THEME = {
    "name": "CY26SU02",
    "dataColors": [TEAL, BLUE, PINK, AMBER, VIOLET, "#67B6D1"],
    "background": BG,
    "foreground": TEXT_MAIN,
    "tableAccent": TEAL,
}


def write_report(folder: Path) -> None:
    definition = folder / "definition"
    definition.mkdir(parents=True)
    (folder / "definition.pbir").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}},
    }, indent=2), encoding="utf-8")
    theme_dir = folder / "StaticResources" / "SharedResources" / "BaseThemes"
    theme_dir.mkdir(parents=True)
    (theme_dir / "CY26SU02.json").write_text(json.dumps(THEME, indent=2), encoding="utf-8")
    write_json(definition / "version.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0",
    })
    write_json(definition / "report.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.0.0/schema.json",
        "themeCollection": {"baseTheme": {
            "name": "CY26SU02",
            "reportVersionAtImport": {"visual": "2.7.0", "report": "3.2.0", "page": "2.1.0"},
            "type": "SharedResources",
        }},
        "resourcePackages": [{"name": "SharedResources", "type": "SharedResources", "items": [
            {"name": "CY26SU02", "path": "BaseThemes/CY26SU02.json", "type": "BaseTheme"},
        ]}],
        "settings": {"useStylableVisualContainerHeader": True, "useEnhancedTooltips": True},
    })
    pages = build_pages()
    write_json(definition / "pages" / "pages.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [page.name for page in pages],
        "activePageName": pages[0].name,
    })
    for page in pages:
        page_dir = definition / "pages" / page.name
        write_json(page_dir / "page.json", page.page_json())
        for visual in page.visuals:
            write_json(page_dir / "visuals" / visual["name"] / "visual.json", visual)


def write_json(path: Path, content: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_dax_reference(path: Path) -> None:
    """All measures in one readable file (used by the manual guide)."""
    lines = ["// Mesures DAX du rapport Morocco Trade Intelligence (générées par tools/build_powerbi.py)", ""]
    for spec in TABLES:
        for m in spec["measures"]:
            lines.append(f"// Table : {spec['name']} · format : {m['format']}")
            lines.append(f"{m['name']} =")
            lines += ["    " + line for line in m["expression"].strip().splitlines()]
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    for folder in (OUT / f"{NAME}.SemanticModel", OUT / f"{NAME}.Report"):
        shutil.rmtree(folder, ignore_errors=True)
    OUT.mkdir(exist_ok=True)
    write_json(OUT / f"{NAME}.pbip", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    })
    write_semantic_model(OUT / f"{NAME}.SemanticModel")
    write_dax_reference(OUT / "mesures.dax")
    write_report(OUT / f"{NAME}.Report")
    print(f"Power BI project written to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
