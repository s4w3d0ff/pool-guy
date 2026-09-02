"""Smoke tests for the twitch-cli mock server session fixtures."""
import json
import urllib.request


def test_mock_session_configured(mock_units):
    client = mock_units["client"]
    assert client["ID"] and client["Secret"]
    users = mock_units["users"]
    assert len(users) >= 20, f"expected >=20 generated users, got {len(users)}"
    partners = [u for u in users if u.get("broadcaster_type") == "partner"]
    assert partners, "no partner user discovered from /units/users"
    rich = mock_units["rich_partner"]
    assert rich["id"] in {u["id"] for u in partners}
    assert mock_units["follower_totals"][rich["id"]] > 0


def test_mock_urls_local(mock_api_prefix, mock_ws_url):
    assert mock_api_prefix == "http://127.0.0.1:8000/mock"
    assert mock_ws_url == "ws://127.0.0.1:8090/ws"


def test_units_clients_live():
    with urllib.request.urlopen("http://127.0.0.1:8000/units/clients", timeout=5) as r:
        body = json.load(r)
    assert body["data"] and "ID" in body["data"][0]


def test_session_state_stable(mock_units, request):
    again = request.getfixturevalue("mock_units")
    assert mock_units is again
