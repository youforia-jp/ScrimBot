"""Unit tests for Steam32 and URL parsing logic."""

import pytest
from id_parser import (
    STEAM64_BASE,
    parse_opponent_roster,
    parse_single_id,
    steam64_to_steam32,
)


def test_parse_raw_steam32() -> None:
    assert parse_single_id("123456789") == 123456789
    assert parse_single_id("  105829141  ") == 105829141


def test_parse_statlocker_url() -> None:
    url = "https://statlocker.gg/profile/123456789"
    assert parse_single_id(url) == 123456789

    url_slash = "http://statlocker.gg/profile/987654321/"
    assert parse_single_id(url_slash) == 987654321


def test_parse_steam64_url() -> None:
    # 76561198083722517 - 76561197960265728 = 123456789
    steam64_val = 76561198083722517
    assert steam64_to_steam32(steam64_val) == 123456789

    url = f"https://steamcommunity.com/profiles/{steam64_val}"
    assert parse_single_id(url) == 123456789

    url_slash = f"https://steamcommunity.com/profiles/{steam64_val}/"
    assert parse_single_id(url_slash) == 123456789


def test_parse_raw_steam64() -> None:
    steam64_str = "76561198083722517"
    assert parse_single_id(steam64_str) == 123456789


def test_parse_steam_id3() -> None:
    assert parse_single_id("[U:1:123456789]") == 123456789
    assert parse_single_id("U:1:105829141") == 105829141


def test_parse_tracker_urls() -> None:
    assert parse_single_id("https://tracklock.gg/players/123456789") == 123456789
    assert parse_single_id("https://deadlocktracker.gg/player/987654321") == 987654321


def test_parse_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        parse_single_id("")

    with pytest.raises(ValueError):
        parse_single_id("   ")

    with pytest.raises(ValueError):
        parse_single_id("https://steamcommunity.com/id/randomname/")


def test_parse_opponent_roster() -> None:
    inputs = [
        "105829141",
        "https://statlocker.gg/profile/89410294",
        "https://steamcommunity.com/profiles/76561198080754838",  # 120489110
        "[U:1:145920391]",
        "https://tracklock.gg/players/77489201",
        "99381023",
    ]
    ids = parse_opponent_roster(inputs)
    assert len(ids) == 6
    assert ids[0] == 105829141
    assert ids[1] == 89410294
    assert ids[3] == 145920391
    assert ids[4] == 77489201
    assert ids[5] == 99381023
