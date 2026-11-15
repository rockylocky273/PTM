import pytest
from mars_analog.data.quality import parse_bbox, validate_time


def test_bbox_valido():
    assert parse_bbox("-69,-24,-68,-23") == (-69.0, -24.0, -68.0, -23.0)


@pytest.mark.parametrize("bad", ["-69,-24,-68", "-69,-24,-70,-23", "-181,-24,-68,-23", "nan,0,1,2", "170,-5,-170,5"])
def test_bbox_invalido(bad):
    with pytest.raises(ValueError):
        parse_bbox(bad)


def test_time():
    assert validate_time("2024-01-01", "2024-02-01") == ("2024-01-01", "2024-02-01")
    with pytest.raises(ValueError):
        validate_time("2024-02-01", "2024-01-01")
