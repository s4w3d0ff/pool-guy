"""REST response handling against twitch-cli mock-api: real wire format, no fakes."""

import pytest


async def test_followers_walks_all_pages_against_mock(mocked_api, mock_units):
    api = mocked_api()
    partner = mock_units["rich_partner"]
    total = mock_units["follower_totals"][partner["id"]]
    assert total >= 4, f"mock dataset too small to exercise pagination: {total}"
    page_size = max(2, total // 3)
    if total % page_size == 0:
        page_size += 1

    requests = []
    original = api._request

    async def counting_request(method, url, *args, **kwargs):
        requests.append((method, url))
        return await original(method, url, *args, **kwargs)

    api._request = counting_request

    out = await api.getChannelFollowers(broadcaster_id=partner["id"], first=page_size)

    ids = [row["user_id"] for row in out]
    assert len(ids) == total, f"expected all {total} followers, got {len(ids)}"
    assert len(set(ids)) == total, "follower rows duplicated across pages"
    expected_pages = -(-total // page_size)
    assert len(requests) == expected_pages, (
        f"expected {expected_pages} requests for {total} followers at first={page_size}, got {len(requests)}"
    )


async def test_followers_terminal_page_without_pagination_key(mocked_api, mock_units):
    api = mocked_api()
    partner = mock_units["rich_partner"]
    total = mock_units["follower_totals"][partner["id"]]

    out = await api.getChannelFollowers(broadcaster_id=partner["id"], first=total)
    assert len(out) == total, f"empty-pagination terminal page lost rows: {len(out)} != {total}"

    over_sized = await api.getChannelFollowers(broadcaster_id=partner["id"], first=total * 2)
    assert len(over_sized) == total, (
        f"terminal page without pagination key lost rows: {len(over_sized)} != {total}"
    )


async def test_unknown_route_surfaces_status_and_body(mocked_api):
    from poolguy.http import ApiRequestError

    api = mocked_api()
    url = "http://127.0.0.1:8000/mock/not-a-route"
    with pytest.raises(ApiRequestError) as excinfo:
        await api._request("get", url)
    assert excinfo.value.status == 404, f"status not surfaced: {excinfo.value.status}"
    assert "page not found" in excinfo.value.message.lower(), (
        f"response body not surfaced in message: {excinfo.value.message!r}"
    )


async def test_deprecated_route_surfaces_json_error_body(mocked_api):
    from poolguy.http import ApiRequestError

    api = mocked_api()
    url = "http://127.0.0.1:8000/mock/users/follows?source_id=1&target_id=2"
    with pytest.raises(ApiRequestError) as excinfo:
        await api._request("get", url)
    assert excinfo.value.status == 410, f"status not surfaced: {excinfo.value.status}"
    assert "deprecated" in excinfo.value.message.lower(), (
        f"JSON error body message not surfaced: {excinfo.value.message!r}"
    )
