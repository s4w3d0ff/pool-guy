"""TwitchApi.api_prefix: per-instance endpoint base url override."""
import poolguy.twitchapi as twitchapi_mod
from conftest import FakeStorage
from poolguy.twitchapi import TwitchApi


def make_full_api(**kwargs):
    return TwitchApi(
        client_id="test-client",
        redirect_uri="http://localhost:1/callback",
        storage=FakeStorage(),
        **kwargs,
    )


async def test_default_instance_endpoints_match_module_constants():
    api = make_full_api()
    assert api.apiEndpoints == twitchapi_mod.apiEndpoints
    for value in api.apiEndpoints.values():
        assert value.startswith("https://api.twitch.tv/helix")


async def test_api_prefix_rebuilds_endpoint_map_per_instance():
    prefix = "http://127.0.0.1:9"
    api = make_full_api(api_prefix=prefix)
    expected = {
        key: value.replace(twitchapi_mod.apiUrlPrefix, prefix)
        for key, value in twitchapi_mod.apiEndpoints.items()
    }
    assert api.apiEndpoints == expected


async def test_module_constants_untouched_when_prefixed():
    make_full_api(api_prefix="http://127.0.0.1:9")
    assert twitchapi_mod.apiUrlPrefix == "https://api.twitch.tv/helix"
    for value in twitchapi_mod.apiEndpoints.values():
        assert value.startswith("https://api.twitch.tv/helix")
