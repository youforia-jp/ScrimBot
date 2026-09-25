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
