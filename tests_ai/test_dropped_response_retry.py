"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-07).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

Seen 2026-10-01 (a graded test) and 2026-10-07 (refuse_locked_wo48_reschedule): the connection
dropped mid-response with http.client.IncompleteRead. On 10-07 it was the verifier's AgentMemory read,
so a correct refusal scored unevaluated. Reads now retry a dropped response; writes still do not,
because the server may already have applied a write whose response was lost.

Run: python -m pytest tests_ai/test_dropped_response_retry.py -q
"""
import http.client

import pytest

from prod_agent import mcp_client


class FakeResponse:
    status = 200

    def __init__(self, body=b'{"ok": true}'):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def scripted(monkeypatch):
    monkeypatch.setattr(mcp_client.time, "sleep", lambda s: None)
    calls = []

    def install(*outcomes):
        queue = list(outcomes)

        def urlopen(req, timeout=None):
            calls.append(req.get_method())
            outcome = queue.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        monkeypatch.setattr(mcp_client.urllib.request, "urlopen", urlopen)
        return calls

    return install


def test_a_read_cut_mid_response_is_retried(scripted):
    calls = scripted(http.client.IncompleteRead(b"x" * 10, 20), FakeResponse())
    assert mcp_client._http("https://h/api/AgentMemory") == (200, {"ok": True})
    assert calls == ["GET", "GET"]


def test_a_connection_reset_on_a_read_is_retried(scripted):
    calls = scripted(ConnectionResetError(), FakeResponse())
    assert mcp_client._http("https://h/api/mcp", body={"method": "tools/call"}, read_only=True)[0] == 200
    assert len(calls) == 2


def test_a_write_cut_mid_response_is_not_retried(scripted):
    """The server may already have applied it; repeating could write twice."""
    calls = scripted(http.client.IncompleteRead(b"", 5), FakeResponse())
    with pytest.raises(http.client.IncompleteRead):
        mcp_client._http("https://h/api/mcp", body={"method": "tools/call"}, read_only=False)
    assert len(calls) == 1


def test_a_read_that_keeps_dropping_still_fails(scripted):
    drops = [http.client.IncompleteRead(b"", 5) for _ in range(mcp_client.CONNECT_RETRIES + 1)]
    calls = scripted(*drops)
    with pytest.raises(http.client.IncompleteRead):
        mcp_client._http("https://h/api/AgentMemory")
    assert len(calls) == mcp_client.CONNECT_RETRIES + 1
