import requests
import pytest

from mars_analog.data.climate_power import _download_power_json
from test_climate_power import power_data

SITE = {"region_id": "r063_c140", "center_lat": 37., "center_lon_180": -79.}


class GoodResponse:
    headers = {"Content-Type": "application/json"}
    def __init__(self, data): self.data = data
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def raise_for_status(self): return None
    def iter_content(self, chunk_size):
        import json
        yield json.dumps(self.data).encode("utf8")


class FakeSession:
    def __init__(self, results): self.results = iter(results); self.calls = 0; self.timeouts = []
    def get(self, url, **kwargs):
        self.calls += 1
        self.timeouts.append(kwargs['timeout'])
        result = next(self.results)
        if isinstance(result, Exception): raise result
        return result


def http_error(code, retry_after=None):
    r = requests.Response()
    r.status_code = code
    if retry_after is not None: r.headers["Retry-After"] = retry_after
    return requests.HTTPError(f"HTTP {code}", response=r)


def test_transient_timeout_recovers(monkeypatch):
    delays = []
    monkeypatch.setattr('mars_analog.data.climate_power.time.sleep', delays.append)
    client = FakeSession([requests.exceptions.ReadTimeout("read timeout=15"), GoodResponse(power_data())])
    obj = _download_power_json(SITE, 2020, 2021, 1024, session=client,
                               read_timeout=180, connect_timeout=25, retries=2)
    assert 'T2M' in obj['properties']['parameter']
    assert client.calls == 2 and client.timeouts == [(25,180),(25,180)]
    assert delays == [2]


def test_does_not_retry_422(monkeypatch):
    delays=[]
    monkeypatch.setattr('mars_analog.data.climate_power.time.sleep', delays.append)
    client=FakeSession([http_error(422)])
    with pytest.raises(RuntimeError, match='1 intento'):
        _download_power_json(SITE, 2020, 2021, 1024, session=client)
    assert client.calls == 1 and delays == []


def test_429_then_503_then_success(monkeypatch):
    delays=[]
    monkeypatch.setattr('mars_analog.data.climate_power.time.sleep', delays.append)
    client=FakeSession([http_error(429,'10'), http_error(503), GoodResponse(power_data())])
    result=_download_power_json(SITE, 2020, 2021, 1024, session=client, retries=2)
    assert client.calls == 3 and delays == [10.,4.]
    assert result['properties']['parameter']['RH2M']


def test_retry_exhaustion(monkeypatch):
    delays=[]
    monkeypatch.setattr('mars_analog.data.climate_power.time.sleep', delays.append)
    client=FakeSession([requests.exceptions.ReadTimeout('timed out') for _ in range(3)])
    with pytest.raises(RuntimeError,match='después de 3 intento'):
        _download_power_json(SITE, 2020, 2021, 1024, session=client, retries=2)
    assert client.calls == 3 and delays == [2.,4.]


def test_invalid_retry_parameters():
    with pytest.raises(ValueError,match='Timeouts'):
        _download_power_json(SITE, 2020, 2021, 1024, session=FakeSession([]), read_timeout=0)
    with pytest.raises(ValueError,match='retries'):
        _download_power_json(SITE, 2020, 2021, 1024, session=FakeSession([]), retries=8)


def test_json_validation_failure_never_retry(monkeypatch):
    delays=[]
    monkeypatch.setattr('mars_analog.data.climate_power.time.sleep', delays.append)
    client=FakeSession([GoodResponse({})])
    with pytest.raises(ValueError,match='series mensuales'):
        _download_power_json(SITE, 2020, 2021, 1024, session=client)
    assert client.calls==1 and delays==[]
