"""TokenHandler endpoint kwargs: id.twitch.tv urls overridable per instance."""
from conftest import FakeStorage, make_handler
import poolguy.core.oauth as oauth_mod
from poolguy.core.oauth import TokenHandler


async def test_default_endpoints_match_module_constants():
    handler = make_handler()
    assert handler.token_endpoint == oauth_mod.tokenEndpoint
    assert handler.oauth_endpoint == oauth_mod.oauthEndpoint
    assert handler.validate_endpoint == oauth_mod.validateEndoint


async def test_explicit_endpoints_override_defaults():
    handler = TokenHandler(
        client_id="client-abc",
        storage=FakeStorage(),
        token_endpoint="http://127.0.0.1:9/auth/token",
        oauth_endpoint="http://127.0.0.1:9/auth/authorize",
        validate_endpoint="http://127.0.0.1:9/oauth2/validate",
    )
    assert handler.token_endpoint == "http://127.0.0.1:9/auth/token"
    assert handler.oauth_endpoint == "http://127.0.0.1:9/auth/authorize"
    assert handler.validate_endpoint == "http://127.0.0.1:9/oauth2/validate"


async def test_module_constants_untouched_when_overridden():
    TokenHandler(
        client_id="client-abc",
        storage=FakeStorage(),
        token_endpoint="http://127.0.0.1:9/auth/token",
    )
    assert oauth_mod.tokenEndpoint == "https://id.twitch.tv/oauth2/token"
    assert oauth_mod.oauthEndpoint == "https://id.twitch.tv/oauth2/authorize"
    assert oauth_mod.validateEndoint == "https://id.twitch.tv/oauth2/validate"
