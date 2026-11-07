"""Extraction settings: which UN Comtrade data the pipeline collects.

Every API call is described by a ComtradeRequest. The request plan is kept
small on purpose: the public preview endpoint returns at most 500 records per
call, so each request is scoped to stay well below that limit.
"""

from __future__ import annotations

from dataclasses import dataclass

MOROCCO = 504
DEFAULT_YEARS = list(range(2019, 2026))  # 2019 to 2025

# Main trading partners used for mirror statistics (UN Comtrade country codes).
MIRROR_PARTNERS = {
    724: "Spain",
    251: "France",
    156: "China",
    842: "USA",
    276: "Germany",
    380: "Italy",
    792: "Türkiye",
    699: "India",
    528: "Netherlands",
    826: "United Kingdom",
    56: "Belgium",
    620: "Portugal",
    76: "Brazil",
    682: "Saudi Arabia",
    643: "Russian Federation",
}

# Automotive-related HS headings followed partner by partner.
AUTOMOTIVE_CODES = {
    "8703": "Motor cars for the transport of persons",
    "8708": "Parts and accessories of motor vehicles",
    "8544": "Insulated wire and cable, incl. vehicle wiring sets",
}

FLOWS = ("X", "M")  # X = exports, M = imports


@dataclass(frozen=True)
class ComtradeRequest:
    """One call to the UN Comtrade preview API (annual data, HS classification)."""

    dataset: str
    year: int
    reporter: str  # one code or a comma-separated list
    flow: str  # "X", "M" or "X,M"
    cmd: str  # "TOTAL", "AG2" (all HS chapters) or HS codes
    partner: str | None  # None = all partners

    @property
    def request_id(self) -> str:
        flow = self.flow.replace(",", "")
        cmd = self.cmd.replace(",", "-")
        return f"{self.dataset}__{self.year}__{flow}__{cmd}"

    @property
    def reporters(self) -> set[int]:
        return {int(code) for code in self.reporter.split(",")}

    def params(self) -> dict[str, str]:
        """Query parameters, named as in the official comtradeapicall package."""
        params = {
            "reportercode": self.reporter,
            "period": str(self.year),
            "flowCode": self.flow,
            "cmdCode": self.cmd,
            # Totals only: no breakdown by second partner, customs procedure
            # or transport mode, so one row = one reporter/partner/flow/product.
            "partner2Code": "0",
            "customsCode": "C00",
            "motCode": "0",
            "maxRecords": "500",
            "format": "JSON",
            "breakdownMode": "classic",
            "includeDesc": "True",
        }
        if self.partner is not None:
            params["partnerCode"] = self.partner
        return params


def build_request_plan(years: list[int] | None = None) -> list[ComtradeRequest]:
    """Return every API call needed for the given years."""
    years = years or DEFAULT_YEARS
    mirror_reporters = ",".join(str(code) for code in MIRROR_PARTNERS)
    morocco = str(MOROCCO)
    plan: list[ComtradeRequest] = []
    for year in years:
        # 1. Morocco's trade with the world, by HS chapter (about 2 x 97 rows).
        plan.append(ComtradeRequest("products_world", year, morocco, "X,M", "AG2", "0"))
        for flow in FLOWS:
            # 2. Morocco's total trade by partner country (about 230 rows).
            plan.append(ComtradeRequest("partners_total", year, morocco, flow, "TOTAL", None))
            # 3. Automotive headings by partner, one heading per call.
            for code in AUTOMOTIVE_CODES:
                plan.append(ComtradeRequest("automotive_partners", year, morocco, flow, code, None))
        # 4. Mirror data: what the main partners declare about trade with Morocco.
        plan.append(ComtradeRequest("mirror_partners", year, mirror_reporters, "X,M", "TOTAL", morocco))
    return plan
