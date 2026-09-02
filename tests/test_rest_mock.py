"""REST response handling against twitch-cli mock-api: real wire format, no fakes."""


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
