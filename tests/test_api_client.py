"""Unit tests for Statlocker and Deadlock API clients and fallback resilience."""

from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest

from api_client import DeadlockClient, StatlockerClient
from config import settings


@pytest.mark.asyncio
async def test_statlocker_missing_api_key_fallback() -> None:
    client = StatlockerClient(api_key=None)
    account_ids = [105829141, 89410294]
    profiles = await client.fetch_profiles(account_ids)

    assert client.connected is False
    assert len(profiles) == 2
    assert profiles[105829141]["ppScore"] == 5000
    assert profiles[105829141]["estimatedRankNumber"] == 8
    assert profiles[89410294]["ppScore"] == 5000


@pytest.mark.asyncio
async def test_statlocker_http_error_graceful_fallback() -> None:
    client = StatlockerClient(api_key="invalid_test_key")
    account_ids = [105829141]

    # Mock response returning 401 Unauthorized
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 401
    mock_resp.text = '{"error": "Unauthorized"}'

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        profiles = await client.fetch_profiles(account_ids)

        assert client.connected is False
        assert profiles[105829141]["ppScore"] == 5000
        assert profiles[105829141]["estimatedRankNumber"] == 8


@pytest.mark.asyncio
async def test_statlocker_successful_response_parsing() -> None:
    client = StatlockerClient(api_key="valid_key")
    account_ids = [105829141, 89410294]

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"accountId": 105829141, "ppScore": 6850, "estimatedRankNumber": 92},
        {"accountId": 89410294, "ppScore": 7420, "estimatedRankNumber": 101},
    ]

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        profiles = await client.fetch_profiles(account_ids)

        assert client.connected is True
        assert profiles[105829141]["ppScore"] == 6850
        assert profiles[105829141]["estimatedRankNumber"] == 92
        assert profiles[89410294]["ppScore"] == 7420
        assert profiles[89410294]["estimatedRankNumber"] == 101


@pytest.mark.asyncio
async def test_statlocker_create_draft_lobby_missing_key() -> None:
    client = StatlockerClient(api_key=None)
    resp = await client.create_draft_lobby([105829141, 89410294])
    assert resp.success is False
    assert "not configured" in resp.message


@pytest.mark.asyncio
async def test_statlocker_create_draft_lobby_success() -> None:
    client = StatlockerClient(api_key="valid_key")
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "draftId": "lobby-12345",
        "draftUrl": "https://statlocker.gg/draft/lobby-12345",
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        resp = await client.create_draft_lobby([105829141, 89410294])
        assert resp.success is True
        assert resp.draft_url == "https://statlocker.gg/draft/lobby-12345"


@pytest.mark.asyncio
async def test_deadlock_hero_stats_parsing() -> None:
    client = DeadlockClient()
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"hero_id": 2, "matches_played": 50, "wins": 35},
        {"hero_id": 27, "matches_played": 30, "wins": 18},
    ]

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_resp)

    records = await client.fetch_player_hero_stats(mock_client, account_id=105829141)
    assert len(records) == 2
    assert records[0].hero_name == "Seven"
    assert records[0].matches_played == 50
    assert records[0].wins == 35
    assert pytest.approx(records[0].win_rate, rel=1e-3) == 0.7
    assert records[1].hero_name == "Yamato"


@pytest.mark.asyncio
async def test_deadlock_recent_matches_200_cap() -> None:
    """Verify that match history is capped to the most recent 200 games and aggregates correctly."""
    client = DeadlockClient()

    # Create 250 match records:
    # - Matches 0-119 (120 games): Seven (hero 2), 80 wins, 40 losses
    # - Matches 120-199 (80 games): Yamato (hero 27), 50 wins, 30 losses
    # - Matches 200-249 (50 games, older): Bebop (hero 15) -> Should be EXCLUDED by 200-game cap!
    raw_matches = []
    for idx in range(120):
        is_win = idx < 80
        raw_matches.append({
            "match_id": 1000 + idx,
            "hero_id": 2,
            "start_time": 2000000 - idx,
            "player_team": 0,
            "match_result": 0 if is_win else 1,
            "player_kills": 5,
            "player_deaths": 2,
            "player_assists": 8,
        })

    for idx in range(80):
        is_win = idx < 50
        raw_matches.append({
            "match_id": 2000 + idx,
            "hero_id": 27,
            "start_time": 1000000 - idx,
            "player_team": 1,
            "match_result": 1 if is_win else 0,
            "player_kills": 6,
            "player_deaths": 3,
            "player_assists": 6,
        })

    for idx in range(50):
        raw_matches.append({
            "match_id": 3000 + idx,
            "hero_id": 15,
            "start_time": 500000 - idx,
            "player_team": 0,
            "match_result": 0,
            "player_kills": 2,
            "player_deaths": 5,
            "player_assists": 4,
        })

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = raw_matches

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(return_value=mock_resp)

    records = await client.fetch_player_hero_stats(
        mock_client, account_id=105829141, max_matches=200
    )

    records_by_name = {r.hero_name: r for r in records}
    # Seven and Yamato should be present
    assert "Seven" in records_by_name
    assert "Yamato" in records_by_name
    # Bebop was only played in matches 201-250, so it must be excluded by the 200-game cap!
    assert "Bebop" not in records_by_name

    seven = records_by_name["Seven"]
    assert seven.matches_played == 120
    assert seven.wins == 80
    assert pytest.approx(seven.win_rate, rel=1e-3) == (80 / 120)
    assert seven.kills == 120 * 5
    assert seven.deaths == 120 * 2
    assert seven.assists == 120 * 8

    yamato = records_by_name["Yamato"]
    assert yamato.matches_played == 80
    assert yamato.wins == 50
    assert pytest.approx(yamato.win_rate, rel=1e-3) == (50 / 80)

