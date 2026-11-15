import pytest
from mars_analog.data.noaa import build_etopo_url, download_etopo


def test_url_negatives_to_0360():
    url = build_etopo_url((-69, -24, -68, -23), stride=2)
    assert "291.000000" in url and "292.000000" in url
    assert "-24.000000" in url and "-23.000000" in url
    assert ":2:" in url
    assert url.startswith("https://oceanwatch.pifsc.noaa.gov/")


def test_url_no_crossing_zero():
    with pytest.raises(ValueError):
        build_etopo_url((-2, -5, 2, 5))


def test_subset_budget_blocks_before_http(tmp_path):
    with pytest.raises(ValueError, match="excede"):
        download_etopo((-100, -40, -50, 0), tmp_path, max_mb=1)


def test_url_boundary_zero():
    with pytest.raises(ValueError):
        build_etopo_url((-1, -5, 0, 5))


def test_url_positive():
    url = build_etopo_url((1, 10, 2, 11))
    assert "1.000000" in url and "2.000000" in url
