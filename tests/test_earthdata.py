import pytest
from mars_analog.data import earthdata


class FakeGranule(dict):
    size = 2.5

    def data_links(self, access):
        assert access == "external"
        return ["https://example.org/granule.hdf"]


class FakeAPI:
    def __init__(self):
        self.calls = []

    def search_datasets(self, **kwargs):
        self.calls.append(("datasets", kwargs))
        return [{"meta": {"concept-id": "C123", "revision-id": 1},
                 "umm": {"EntryTitle": "Mock data", "ShortName": kwargs["short_name"], "Version": "061"}}]

    def search_data(self, **kwargs):
        self.calls.append(("granules", kwargs))
        return [FakeGranule({"meta": {"concept-id": "G1"}, "umm": {"GranuleUR": "granule1"}})]


def test_search_collections_mocked(monkeypatch):
    fake = FakeAPI()
    monkeypatch.setattr(earthdata, "_ea", lambda: fake)
    found = earthdata.discover_collections()
    assert found["modis_lst"]["collections"][0]["concept_id"] == "C123"
    assert fake.calls[0][1]["short_name"] == "MOD11C3"
    assert fake.calls[1][1]["short_name"] == "GPM_3IMERGM"


def test_granule_query_mocked(monkeypatch):
    fake = FakeAPI()
    monkeypatch.setattr(earthdata, "_ea", lambda: fake)
    got = earthdata.query_granules("gpm_monthly", "2024-01-01", "2024-02-01", bbox=(-69,-24,-68,-23))
    assert len(got) == 1
    assert fake.calls[0][1]["version"] == "07"
    assert fake.calls[0][1]["bounding_box"] == (-69.0,-24.0,-68.0,-23.0)
    assert earthdata.granule_summary(got[0])["size_mb"] == 2.5


def test_query_count_limit():
    with pytest.raises(ValueError):
        earthdata.query_granules("modis_lst", "2024-01-01", "2024-02-01", count=100)
