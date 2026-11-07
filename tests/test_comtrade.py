import pytest

from mti.comtrade import ComtradeClient, ComtradeError, TruncatedResponseError
from mti.config import ComtradeRequest
from mti.fake_api import FakeResponse

REQUEST = ComtradeRequest("partners_total", 2023, "504", "X", "TOTAL", None)


def record(reporter=504, year=2023):
    return {"reporterCode": reporter, "refYear": year, "primaryValue": 1.0}


class ScriptedSession:
    """Returns the prepared responses one after the other."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, params, timeout):
        self.calls += 1
        return self.responses.pop(0)


def client(session, waits):
    return ComtradeClient(session=session, pause_seconds=0, max_retries=3, sleep=waits.append)


def test_retries_after_rate_limit():
    waits = []
    session = ScriptedSession(
        FakeResponse({}, status_code=429, headers={"Retry-After": "7"}),
        FakeResponse({"data": [record()], "error": ""}),
    )
    assert client(session, waits).fetch(REQUEST) == [record()]
    assert session.calls == 2
    assert 7.0 in waits


def test_gives_up_after_max_retries():
    session = ScriptedSession(*[FakeResponse({}, status_code=503) for _ in range(3)])
    with pytest.raises(ComtradeError, match="gave up"):
        client(session, []).fetch(REQUEST)


def test_client_error_is_not_retried():
    session = ScriptedSession(FakeResponse({}, status_code=400))
    with pytest.raises(ComtradeError, match="HTTP 400"):
        client(session, []).fetch(REQUEST)
    assert session.calls == 1


def test_api_error_message_is_raised():
    session = ScriptedSession(FakeResponse({"data": [], "error": "invalid parameter"}))
    with pytest.raises(ComtradeError, match="invalid parameter"):
        client(session, []).fetch(REQUEST)


def test_truncated_answer_is_rejected():
    session = ScriptedSession(FakeResponse({"data": [record()] * 500, "error": ""}))
    with pytest.raises(TruncatedResponseError):
        client(session, []).fetch(REQUEST)


def test_unexpected_reporter_is_rejected():
    session = ScriptedSession(FakeResponse({"data": [record(reporter=250)], "error": ""}))
    with pytest.raises(ComtradeError, match="unexpected reporter"):
        client(session, []).fetch(REQUEST)


def test_unexpected_year_is_rejected():
    session = ScriptedSession(FakeResponse({"data": [record(year=2022)], "error": ""}))
    with pytest.raises(ComtradeError, match="unexpected year"):
        client(session, []).fetch(REQUEST)


def test_empty_answer_is_accepted():
    session = ScriptedSession(FakeResponse({"data": [], "error": ""}))
    assert client(session, []).fetch(REQUEST) == []
