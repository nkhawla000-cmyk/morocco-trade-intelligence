"""Synthetic stand-in for the UN Comtrade API, used only by tests and --offline runs.

It answers with the same JSON structure as the real preview endpoint, so the
whole pipeline (extraction, bronze, dbt models and tests, exports) can be
checked without network access. All values are invented and deterministic;
they must never be presented as real trade statistics.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .config import MOROCCO

COUNTRIES = {
    0: ("W00", "World"),
    504: ("MAR", "Morocco"),
    724: ("ESP", "Spain"),
    251: ("FRA", "France"),
    156: ("CHN", "China"),
    842: ("USA", "USA"),
    276: ("DEU", "Germany"),
    899: ("_X", "Areas, nes"),
}
PARTNERS = [724, 251, 156, 842, 276, 899]
CHAPTERS = {
    "27": "Mineral fuels, mineral oils and products of their distillation",
    "31": "Fertilizers",
    "85": "Electrical machinery and equipment and parts thereof",
    "87": "Vehicles other than railway or tramway rolling stock",
}
HEADINGS = {
    "8703": "Motor cars and other motor vehicles principally designed for the transport of persons",
    "8708": "Parts and accessories of the motor vehicles of headings 8701 to 8705",
    "8544": "Insulated wire, cable and other insulated electric conductors",
}
MIRROR_FACTORS = {"M": 1.06, "X": 0.95}  # partner imports are CIF, exports FOB
MIRROR_OUTLIER = 156  # one partner with a large gap, to exercise the review flag


def _leaf_value(reporter: int, partner: int, flow: str, cmd: str, year: int) -> float:
    digest = hashlib.sha256(f"{reporter}|{partner}|{flow}|{cmd}|{year}".encode()).hexdigest()
    base = 5_000_000 + (int(digest[:8], 16) % 1000) * 1_000_000
    return round(base * (1 + 0.04 * (year - 2019)), 2)


def trade_value(reporter: int, partner: int, flow: str, cmd: str, year: int) -> float:
    """Consistent synthetic values: World = sum of partners, TOTAL = sum of chapters."""
    if reporter != MOROCCO and partner == MOROCCO:
        mirror_flow = "X" if flow == "M" else "M"
        factor = MIRROR_FACTORS[flow] * (1.35 if reporter == MIRROR_OUTLIER else 1.0)
        return round(trade_value(MOROCCO, reporter, mirror_flow, cmd, year) * factor, 2)
    if partner == 0:
        return round(sum(trade_value(reporter, p, flow, cmd, year) for p in PARTNERS), 2)
    if cmd == "TOTAL":
        return round(sum(_leaf_value(reporter, partner, flow, c, year) for c in CHAPTERS), 2)
    return _leaf_value(reporter, partner, flow, cmd, year)


def _record(reporter: int, partner: int, flow: str, cmd: str, year: int) -> dict:
    value = trade_value(reporter, partner, flow, cmd, year)
    description = {"TOTAL": "All Commodities", **CHAPTERS, **HEADINGS}.get(cmd, cmd)
    return {
        "typeCode": "C",
        "freqCode": "A",
        "refPeriodId": int(f"{year}0101"),
        "refYear": year,
        "refMonth": 52,
        "period": str(year),
        "reporterCode": reporter,
        "reporterISO": COUNTRIES[reporter][0],
        "reporterDesc": COUNTRIES[reporter][1],
        "flowCode": flow,
        "flowDesc": "Export" if flow == "X" else "Import",
        "partnerCode": partner,
        "partnerISO": COUNTRIES[partner][0],
        "partnerDesc": COUNTRIES[partner][1],
        "partner2Code": 0,
        "classificationCode": "H6",
        "cmdCode": cmd,
        "cmdDesc": description,
        "aggrLevel": 0 if cmd == "TOTAL" else len(cmd),
        "isLeaf": False,
        "customsCode": "C00",
        "motCode": 0,
        "qtyUnitAbbr": "N/A",
        "qty": None,
        "netWgt": round(value / 900, 1),
        "cifvalue": value if flow == "M" else None,
        "fobvalue": value if flow == "X" else None,
        "primaryValue": value,
        "isReported": True,
        "isAggregate": True,
    }


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200, headers: dict | None = None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = str(payload)[:300]

    def json(self) -> dict:
        return self._payload


class FakeComtradeSession:
    """Mimics requests.Session().get() for the preview endpoint."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def get(self, url: str, params: dict[str, Any], timeout: int = 0) -> FakeResponse:
        self.calls.append(dict(params))
        year = int(params["period"])
        reporters = [int(code) for code in params["reportercode"].split(",")]
        reporters = [r for r in reporters if r in COUNTRIES]
        flows = params["flowCode"].split(",")
        cmd = params["cmdCode"]
        cmds = list(CHAPTERS) if cmd == "AG2" else cmd.split(",")
        if "partnerCode" in params:
            partners = [int(code) for code in params["partnerCode"].split(",")]
        else:
            partners = [0, *PARTNERS]
        data = [
            _record(r, p, f, c, year)
            for r in reporters
            for p in partners
            if p != r
            for f in flows
            for c in cmds
        ]
        return FakeResponse({"elapsedTime": "0.1 secs", "count": len(data), "data": data, "error": ""})
