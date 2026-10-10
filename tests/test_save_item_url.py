"""SaveItem URL checks. Every URL here is invented; nothing is fetched."""

import pytest
from arcade_mcp_server.exceptions import RetryableToolError
from conftest import make_item

from arcade_matter.tools.items import MAX_URL_CHARS, check_save_url, save_item


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/attention",
        "http://example.com/a?utm_source=newsletter&id=42",
        "https://blog.example.co.uk:8443/posts/1#section",
        "https://93.184.215.14/article",
        "https://[2606:2800:21f:cb07:6820:80da:af6b:8b2c]/article",
        "https://cafe.example/menu",
    ],
)
def test_accepts_public_urls(url):
    assert check_save_url(f"  {url} ") == url


@pytest.mark.parametrize(
    "url",
    [
        "https://user:secret@example.com/a",
        "https://user@example.com/a",
        "https://:secret@example.com/a",
    ],
)
def test_rejects_embedded_credentials(url):
    with pytest.raises(RetryableToolError, match="username or password"):
        check_save_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "http://LOCALHOST.:8080/",
        "http://app.localhost/",
        "http://printer.local/",
        "http://metadata.google.internal/",
        "http://nas.home.arpa/",
        "http://intranet/wiki",
        "http://127.0.0.1/",
        "http://127.1/",
        "http://2130706433/",
        "http://0x7f.0.0.1/",
        "http://0177.0.0.1/",
        "http://0.0.0.0/",
        "http://10.1.2.3/",
        "http://172.16.0.1/",
        "http://192.168.1.10/",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.64.0.1/",
        "http://224.0.0.1/",
        "http://[::1]/",
        "http://[fe80::1]/",
        "http://[fd00::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[::ffff:10.0.0.1]/",
    ],
)
def test_rejects_local_and_private_hosts(url):
    with pytest.raises(RetryableToolError, match="local or private-network"):
        check_save_url(url)


@pytest.mark.parametrize("url", ["https://example.com:99999/", "http://[::1/", "https://:80/"])
def test_rejects_malformed_urls(url):
    with pytest.raises(RetryableToolError, match="not an http or https URL"):
        check_save_url(url)


def test_rejects_overlong_urls():
    url = "https://example.com/?q=" + "a" * MAX_URL_CHARS
    with pytest.raises(RetryableToolError, match="longer than"):
        check_save_url(url)


async def test_rejected_url_is_never_sent_to_matter(matter, context):
    with pytest.raises(RetryableToolError):
        await save_item(context, "http://169.254.169.254/latest/meta-data/")

    assert matter.requests == []


async def test_public_url_is_sent_exactly_as_given(matter, context):
    url = "https://example.com/a?ref=feed&page=2"
    matter.add("POST", "/items", make_item(url=url), status=201)

    await save_item(context, url)

    assert matter.last_json()["url"] == url
