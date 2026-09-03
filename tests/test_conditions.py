"""Exact-condition assertions for every event type in the spec condition table."""
import pytest

from conftest import make_api


MODERATOR_EVENTS = [
    "automod.message.hold",
    "automod.message.update",
    "automod.settings.update",
    "automod.terms.update",
    "channel.follow",
    "channel.guest_star_session.begin",
    "channel.guest_star_session.end",
    "channel.guest_star_guest.update",
    "channel.guest_star_settings.update",
    "channel.moderate",
    "channel.shield_mode.begin",
    "channel.shield_mode.end",
    "channel.shoutout.create",
    "channel.shoutout.receive",
    "channel.suspicious_user.message",
    "channel.suspicious_user.update",
    "channel.unban_request.create",
    "channel.unban_request.resolve",
    "channel.warning.send",
    "channel.warning.acknowledge",
]

BROADCASTER_ONLY_EVENTS = [
    "channel.charity_campaign.donate",
    "channel.charity_campaign.progress",
    "channel.charity_campaign.start",
    "channel.charity_campaign.stop",
    "channel.goal.begin",
    "channel.goal.end",
    "channel.goal.progress",
    "channel.poll.begin",
    "channel.poll.progress",
    "channel.poll.end",
    "channel.prediction.begin",
    "channel.prediction.progress",
    "channel.prediction.lock",
    "channel.prediction.end",
    "channel.shared_chat.begin",
    "channel.shared_chat.update",
    "channel.shared_chat.end",
    "channel.vip.add",
    "channel.vip.remove",
    "channel.moderator.add",
    "channel.moderator.remove",
]

CHAT_USER_EVENTS = [
    "channel.chat.clear",
    "channel.chat.clear_user_messages",
    "channel.chat.message",
    "channel.chat.message_delete",
    "channel.chat.notification",
    "channel.chat.user_message_hold",
    "channel.chat.user_message_update",
    "channel.chat_settings.update",
]


@pytest.mark.parametrize("event", MODERATOR_EVENTS)
async def test_moderator_scoped_events_require_both_ids(event):
    api = make_api()
    cond = await api._determine_eventsub_condition(event)
    assert cond == {"broadcaster_user_id": "12345", "moderator_user_id": "12345"}


@pytest.mark.parametrize("event", BROADCASTER_ONLY_EVENTS)
async def test_broadcaster_only_events(event):
    api = make_api()
    cond = await api._determine_eventsub_condition(event)
    assert cond == {"broadcaster_user_id": "12345"}, event


async def test_charity_campaign_is_broadcaster_only():
    api = make_api()
    for event in ("channel.charity_campaign.donate", "channel.charity_campaign.stop"):
        cond = await api._determine_eventsub_condition(event)
        assert set(cond) == {"broadcaster_user_id"}


@pytest.mark.parametrize("event", CHAT_USER_EVENTS)
async def test_chat_events_keep_broadcaster_and_user_pair(event):
    api = make_api()
    cond = await api._determine_eventsub_condition(event)
    assert cond == {"broadcaster_user_id": "12345", "user_id": "12345"}


async def test_moderate_v2_uses_both_ids():
    api = make_api()
    cond = await api._determine_eventsub_condition("channel.moderate")
    assert set(cond) == {"broadcaster_user_id", "moderator_user_id"}


async def test_channel_raid_keeps_to_broadcaster():
    api = make_api()
    cond = await api._determine_eventsub_condition("channel.raid")
    assert cond == {"to_broadcaster_user_id": "12345"}


async def test_bid_override_replaces_default_broadcaster():
    api = make_api()
    cond = await api._determine_eventsub_condition("channel.charity_campaign.start", bid="999")
    assert cond == {"broadcaster_user_id": "999"}
    cond = await api._determine_eventsub_condition("automod.message.hold", bid="888")
    assert cond == {"broadcaster_user_id": "888", "moderator_user_id": "12345"}


async def test_unknown_type_rejected_with_logged_error(caplog):
    api = make_api()
    import logging
    with caplog.at_level(logging.ERROR, logger="poolguy.twitchapi"):
        with pytest.raises(ValueError):
            await api._determine_eventsub_condition("channel.nonexistent.event")
