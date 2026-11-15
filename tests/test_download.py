import hashlib
from pathlib import Path
import pytest
from mars_analog.data.download import fetch_file, DownloadError


class FakeResponse:
    def __init__(self, chunks, length=None, ctype="application/octet-stream"):
        self.chunks = chunks
        self.headers = {"Content-Type": ctype}
        if length is not None:
            self.headers["Content-Length"] = str(length)

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield from self.chunks

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        return self.response


def test_download_checksum_and_cache(tmp_path):
    raw = b"datos-mola-test"
    client = FakeSession(FakeResponse([raw], length=len(raw)))
    path = tmp_path / "topo.img"
    r1 = fetch_file("https://example.org/ok.img", path, "mola", session=client)
    assert path.read_bytes() == raw
    assert r1["sha256"] == hashlib.sha256(raw).hexdigest()
    assert Path(str(path) + ".metadata.json").exists()
    r2 = fetch_file("https://example.org/ok.img", path, "mola", session=client)
    assert r2["cached"] is True
    assert client.calls == 1


def test_limit_does_not_leave_partial(tmp_path):
    client = FakeSession(FakeResponse([b"x" * 2048], length=2048))
    path = tmp_path / "large.img"
    # Content-Length limit validated before writing
    with pytest.raises(DownloadError):
        fetch_file("https://example.org/large.img", path, "test", max_mb=1,
                   session=FakeSession(FakeResponse([b"x" * (1024 * 1024 + 1)])))
    assert not path.exists()
    assert not Path(str(path) + ".part").exists()


def test_html_rejected(tmp_path):
    with pytest.raises(DownloadError):
        fetch_file("https://example.org/error", tmp_path / "file.nc", "test",
                   session=FakeSession(FakeResponse([b"<html>error</html>"], ctype="text/html")))


def test_truncation_rejected(tmp_path):
    with pytest.raises(DownloadError):
        fetch_file("https://example.org/file", tmp_path / "file.img", "test",
                   session=FakeSession(FakeResponse([b"abc"], length=5)))
