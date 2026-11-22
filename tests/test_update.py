import hashlib

import httpx
import pytest

from dotanalyst import update

SETUP = b"MZ fake setup"


def client(tag: str, checksum: str) -> httpx.Client:
    def answer(request: httpx.Request) -> httpx.Response:
        if request.url == update.RELEASES:
            assets = [{"name": n, "browser_download_url": f"https://example.test/{n}"} for n in (update.SETUP, f"{update.SETUP}.sha256")]
            return httpx.Response(200, json={"tag_name": tag, "assets": assets})
        if request.url.path.endswith(".sha256"):
            return httpx.Response(200, text=f"{checksum}  {update.SETUP}\n")
        return httpx.Response(200, content=SETUP)

    return httpx.Client(transport=httpx.MockTransport(answer))


def test_a_newer_release_is_downloaded(tmp_path):
    path = update.download(client("v0.1.10", hashlib.sha256(SETUP).hexdigest().upper()), "0.1.9", tmp_path / "update")
    assert path.read_bytes() == SETUP


def test_the_same_or_an_older_release_is_not(tmp_path):
    assert update.download(client("v0.1.9", "unused"), "0.1.9", tmp_path) is None
    assert update.download(client("v0.0.99", "unused"), "0.1.9", tmp_path) is None


def test_a_setup_that_does_not_match_its_checksum_is_not_kept(tmp_path):
    with pytest.raises(ValueError):
        update.download(client("v0.1.10", "0" * 64), "0.1.9", tmp_path)
    assert not (tmp_path / update.SETUP).exists()


def test_a_run_from_the_repo_never_updates():
    assert update.installed_version() is None
