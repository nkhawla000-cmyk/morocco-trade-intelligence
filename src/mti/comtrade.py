"""Minimal client for the public UN Comtrade preview API (no key required)."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import requests

from .config import ComtradeRequest

log = logging.getLogger(__name__)

PREVIEW_URL = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
MAX_RECORDS = 500
RETRY_STATUSES = {429, 500, 502, 503, 504}


class ComtradeError(RuntimeError):
    """The API answered with an error or an unexpected payload."""


class TruncatedResponseError(ComtradeError):
    """The API returned the maximum number of rows: the result may be incomplete."""


class ComtradeClient:
    """Fetch records with retries, pacing and response validation."""

    def __init__(
        self,
        session: Any | None = None,
        base_url: str = PREVIEW_URL,
        pause_seconds: float = 1.5,
        max_retries: int = 5,
        timeout: int = 90,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.session = session or requests.Session()
        self.base_url = base_url
        self.pause_seconds = pause_seconds
        self.max_retries = max_retries
        self.timeout = timeout
        self.sleep = sleep

    def fetch(self, request: ComtradeRequest) -> list[dict]:
        """Return the validated records of one request."""
        last_problem = "no attempt"
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(
                    self.base_url, params=request.params(), timeout=self.timeout
                )
            except requests.RequestException as exc:
                last_problem = f"network error: {exc}"
            else:
                if response.status_code == 200:
                    records = self._validate(response.json(), request)
                    self.sleep(self.pause_seconds)  # stay polite with the public API
                    return records
                if response.status_code not in RETRY_STATUSES:
                    raise ComtradeError(
                        f"HTTP {response.status_code} for {request.request_id}: "
                        f"{response.text[:300]}"
                    )
                last_problem = f"HTTP {response.status_code}"
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    self.sleep(float(retry_after))
                    continue
            wait = min(60.0, 2.0**attempt)
            log.warning("%s: %s, retry %d in %.0fs", request.request_id, last_problem, attempt, wait)
            self.sleep(wait)
        raise ComtradeError(
            f"{request.request_id}: gave up after {self.max_retries} attempts ({last_problem})"
        )

    @staticmethod
    def _validate(payload: Any, request: ComtradeRequest) -> list[dict]:
        if not isinstance(payload, dict) or "data" not in payload:
            raise ComtradeError(f"{request.request_id}: unexpected response {str(payload)[:200]}")
        if payload.get("error"):
            raise ComtradeError(f"{request.request_id}: API error {payload['error']}")
        records = payload["data"] or []
        if len(records) >= MAX_RECORDS:
            raise TruncatedResponseError(
                f"{request.request_id}: {len(records)} rows returned, the limit is "
                f"{MAX_RECORDS}; split this request into smaller ones"
            )
        expected = request.reporters
        for record in records:
            if int(record.get("reporterCode", -1)) not in expected:
                raise ComtradeError(
                    f"{request.request_id}: unexpected reporter {record.get('reporterCode')}"
                )
            if str(record.get("refYear", record.get("period"))) != str(request.year):
                raise ComtradeError(
                    f"{request.request_id}: unexpected year {record.get('refYear')}"
                )
        return records
