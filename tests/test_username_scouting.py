"""Unit tests for username-based Statlocker ID resolution and auto-scouting."""

from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest

from api_client import DeadlockClient
from id_parser import is_direct_id_or_url
from models import PlayerSearchResult
from scout import get_statlocker_ids_by_usernames, run_scouting, scout_by_usernames


def test_is_direct_id_or_url() -> None:
    """Verify distinction between direct IDs/URLs and raw player usernames."""
    # Direct IDs / URLs
    assert is_direct_id_or_url("165672503") is True
    assert is_direct_id_or_url("https://statlocker.gg/profile/165672503") is True
    assert is_direct_id_or_url("[U:1:165672503]") is True
    assert is_direct_id_or_url("https://steamcommunity.com/profiles/76561198125938231") is True
    assert is_direct_id_or_url("https://tracklock.gg/players/165672503") is True

    # Raw Usernames
    assert is_direct_id_or_url("GreenGobbler") is False
    assert is_direct_id_or_url("BrickMac") is False
    assert is_direct_id_or_url("balls") is False
    assert is_direct_id_or_url("Himedere Uke Lash") is False
    assert is_direct_id_or_url("") is False


@pytest.mark.asyncio
async def test_search_player_by_username_exact_match() -> None:
    """Verify DeadlockClient selects exact personaname match with highest 30d match volume."""
    client = DeadlockClient()

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "account_id": 99999999,
            "personaname": "Green Gobbler Alt",
            "matches_played_last_30d": 50,
            "profileurl": "https://steamcommunity.com/id/alt/",
        },
        {
            "account_id": 165672503,
            "personaname": "GreenGobbler",
            "matches_played_last_30d": 43,
            "profileurl": "https://steamcommunity.com/id/main/",
        },
    ]

    mock_http = MagicMock(spec=httpx.AsyncClient)
    mock_http.get = AsyncMock(return_value=mock_resp)

    res = await client.search_player_by_username("greengobbler", client=mock_http)
    assert res.success is True
    assert res.account_id == 165672503
    assert res.personaname == "GreenGobbler"
    assert res.statlocker_url == "https://statlocker.gg/profile/165672503"
    assert res.matches_played_last_30d == 43


@pytest.mark.asyncio
async def test_get_statlocker_ids_by_usernames_mapping() -> None:
    """Verify get_statlocker_ids_by_usernames returns a dict mapping username to ID."""
    mock_client = MagicMock(spec=DeadlockClient)
    mock_client.resolve_usernames_to_ids = AsyncMock(
        return_value=[
            PlayerSearchResult(search_query="GreenGobbler", account_id=165672503, success=True),
            PlayerSearchResult(search_query="BrickMac", account_id=138808374, success=True),
        ]
    )

    id_map = await get_statlocker_ids_by_usernames(
        ["GreenGobbler", "BrickMac"], deadlock_client=mock_client
    )
    assert id_map == {"GreenGobbler": 165672503, "BrickMac": 138808374}


@pytest.mark.asyncio
async def test_scout_by_usernames_success() -> None:
    """Verify scout_by_usernames resolves all 6 usernames and runs auto scouting."""
    mock_d_client = MagicMock(spec=DeadlockClient)
    mock_d_client.resolve_usernames_to_ids = AsyncMock(
        return_value=[
            PlayerSearchResult(search_query="P1", account_id=105829141, success=True),
            PlayerSearchResult(search_query="P2", account_id=89410294, success=True),
            PlayerSearchResult(search_query="P3", account_id=120489110, success=True),
            PlayerSearchResult(search_query="P4", account_id=145920391, success=True),
            PlayerSearchResult(search_query="P5", account_id=77489201, success=True),
            PlayerSearchResult(search_query="P6", account_id=99381023, success=True),
        ]
    )
    mock_d_client.fetch_all_players_hero_stats = AsyncMock(return_value={})
    mock_d_client.fetch_steam_profiles = AsyncMock(return_value={})
    mock_d_client.connected = True

    with patch("scout.run_scouting") as mock_run:
        from models import ExecutiveScoutingReport
        mock_report = ExecutiveScoutingReport(team_name="Texas A&M White")
        mock_run.return_value = mock_report

        report, search_results = await scout_by_usernames(
            ["P1", "P2", "P3", "P4", "P5", "P6"],
            team_name="Texas A&M White",
            deadlock_client=mock_d_client,
        )

        assert report == mock_report
        assert len(search_results) == 6
        assert search_results[0].account_id == 105829141
        # Check that run_scouting was called with the resolved IDs
        mock_run.assert_called_once()
        called_inputs = mock_run.call_args.kwargs["opponent_inputs"]
        assert called_inputs == ["105829141", "89410294", "120489110", "145920391", "77489201", "99381023"]


@pytest.mark.asyncio
async def test_scout_by_usernames_unresolved_error() -> None:
    """Verify scout_by_usernames raises ValueError when a username cannot be resolved."""
    mock_d_client = MagicMock(spec=DeadlockClient)
    mock_d_client.resolve_usernames_to_ids = AsyncMock(
        return_value=[
            PlayerSearchResult(search_query="ValidUser", account_id=123456, success=True),
            PlayerSearchResult(search_query="NonExistentGhost", success=False, message="Not found"),
        ]
    )

    with pytest.raises(ValueError, match="Failed to resolve 1 player username"):
        await scout_by_usernames(
            ["ValidUser", "NonExistentGhost"],
            deadlock_client=mock_d_client,
        )
