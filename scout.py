"""Scouting orchestrator service coordinating data fetching, analysis, and draft creation."""

from __future__ import annotations

import logging
from typing import Sequence
from config import settings
from id_parser import is_direct_id_or_url, parse_opponent_roster, parse_single_id
from models import DraftLobbyResponse, ExecutiveScoutingReport, PlayerProfile, PlayerSearchResult
from api_client import DeadlockClient, StatlockerClient
from analyzer import analyze_player, calculate_ranked_characters, calculate_team_target_bans
from mock_data import generate_mock_roster

logger = logging.getLogger(__name__)


async def run_scouting(
    opponent_inputs: Sequence[str],
    team_name: str = settings.default_team_name,
    create_draft: bool = False,
    mock_mode: bool = False,
    max_recent_matches: int | None = settings.max_recent_matches,
    statlocker_client: StatlockerClient | None = None,
    deadlock_client: DeadlockClient | None = None,
) -> ExecutiveScoutingReport:
    """
    Execute full competitive scouting workflow for an opponent roster.

    Args:
        opponent_inputs: Player profile URLs, Steam vanity links, Steam32 IDs, or usernames (any count).
        team_name: Collegiate team name.
        create_draft: Whether to create a public Statlocker draft lobby.
        mock_mode: If True, uses realistic collegiate mock data without external network calls.
        max_recent_matches: Maximum recent games to analyze per player (e.g. 200). None for all.
        statlocker_client: Optional injected StatlockerClient.
        deadlock_client: Optional injected DeadlockClient.

    Returns:
        ExecutiveScoutingReport containing target bans, opponent breakdown, and draft link.
    """
    sample_window = (
        f"Past {max_recent_matches} Games"
        if max_recent_matches and max_recent_matches > 0
        else "All Recorded Games"
    )

    if mock_mode:
        roster = generate_mock_roster()
        ranked_characters = calculate_ranked_characters(roster)
        target_bans = calculate_team_target_bans(roster, top_n=3)
        draft_response = None
        if create_draft:
            draft_response = DraftLobbyResponse(
                draft_id="col-scrim-9921",
                draft_url="https://statlocker.gg/draft/col-scrim-9921",
                success=True,
                message="Mock draft room generated successfully.",
            )
        return ExecutiveScoutingReport(
            team_name=team_name,
            opponents=roster,
            ranked_characters=ranked_characters,
            target_bans=target_bans,
            draft_lobby=draft_response,
            statlocker_connected=True,
            deadlock_connected=True,
            sample_window=sample_window,
        )

    s_client = statlocker_client or StatlockerClient()
    d_client = deadlock_client or DeadlockClient()

    # 1. Parse or resolve opponent inputs to Steam32 account IDs
    account_ids: list[int] = []
    resolved_players_meta: list[PlayerSearchResult] = []

    for idx, item in enumerate(opponent_inputs, start=1):
        item_str = item.strip().strip("'\"")
        if not item_str:
            continue

        if is_direct_id_or_url(item_str):
            try:
                acc_id = parse_single_id(item_str)
                account_ids.append(acc_id)
                resolved_players_meta.append(
                    PlayerSearchResult(
                        search_query=item_str,
                        account_id=acc_id,
                        statlocker_url=f"https://statlocker.gg/profile/{acc_id}",
                        success=True,
                        message="Direct ID/URL parsed successfully.",
                    )
                )
            except ValueError as exc:
                raise ValueError(f"Player #{idx} ('{item_str}'): {exc}") from exc
        else:
            # Resolve username via Deadlock API
            search_res = await d_client.search_player_by_username(item_str)
            resolved_players_meta.append(search_res)
            if search_res.success and search_res.account_id is not None:
                account_ids.append(search_res.account_id)
            else:
                raise ValueError(
                    f"Could not resolve username #{idx} ('{item_str}') to a Statlocker ID: {search_res.message}"
                )

    if not account_ids:
        raise ValueError("No valid Steam32 account IDs or usernames provided.")

    # 2. Concurrently fetch Statlocker ratings, Deadlock hero stats, and Steam persona names
    statlocker_task = s_client.fetch_profiles(account_ids)
    hero_stats_task = d_client.fetch_all_players_hero_stats(
        account_ids, max_matches=max_recent_matches
    )
    persona_task = d_client.fetch_steam_profiles(account_ids)

    import asyncio
    statlocker_data, hero_stats_data, persona_names = await asyncio.gather(
        statlocker_task, hero_stats_task, persona_task, return_exceptions=False
    )

    # 3. Analyze each opponent player
    roster: list[PlayerProfile] = []
    for acc_id in account_ids:
        sl_profile = statlocker_data.get(acc_id, {}) or {}
        raw_pp = sl_profile.get("ppScore")
        pp_score = int(raw_pp) if raw_pp is not None else settings.default_pp_score
        raw_rank = sl_profile.get("estimatedRankNumber")
        est_rank = int(raw_rank) if raw_rank is not None else settings.default_rank_number
        persona = persona_names.get(acc_id, "")
        records = hero_stats_data.get(acc_id, [])

        profile = analyze_player(
            account_id=acc_id,
            personaname=persona,
            pp_score=pp_score,
            estimated_rank_number=est_rank,
            hero_records=records,
        )
        roster.append(profile)

    # 4. Compute Ranked Characters and Target Bans (un-accumulated)
    ranked_characters = calculate_ranked_characters(roster)
    target_bans = calculate_team_target_bans(roster, top_n=3)

    # 5. Optionally create draft lobby
    draft_response: DraftLobbyResponse | None = None
    if create_draft:
        draft_response = await s_client.create_draft_lobby(
            opponent_ids=account_ids,
            team_name=team_name,
        )

    return ExecutiveScoutingReport(
        team_name=team_name,
        opponents=roster,
        ranked_characters=ranked_characters,
        target_bans=target_bans,
        draft_lobby=draft_response,
        statlocker_connected=s_client.connected,
        deadlock_connected=d_client.connected,
        sample_window=sample_window,
        resolved_players=resolved_players_meta,
    )


async def get_statlocker_ids_by_usernames(
    usernames: Sequence[str],
    deadlock_client: DeadlockClient | None = None,
) -> dict[str, int | None]:
    """
    Get Statlocker / Steam32 account IDs based on player usernames alone.

    Args:
        usernames: Sequence of player usernames / Steam personanames.
        deadlock_client: Optional injected DeadlockClient.

    Returns:
        Dictionary mapping input username to its resolved integer Steam32 ID (or None if not found).
    """
    client = deadlock_client or DeadlockClient()
    results = await client.resolve_usernames_to_ids(usernames)
    return {res.search_query: res.account_id for res in results}


async def scout_by_usernames(
    usernames: Sequence[str],
    team_name: str = settings.default_team_name,
    create_draft: bool = False,
    max_recent_matches: int | None = settings.max_recent_matches,
    deadlock_client: DeadlockClient | None = None,
    statlocker_client: StatlockerClient | None = None,
) -> tuple[ExecutiveScoutingReport, list[PlayerSearchResult]]:
    """
    Get Statlocker IDs based on player usernames alone, and then auto-scout the roster.

    Args:
        usernames: Sequence of player usernames (any count, e.g. ['GreenGobbler', 'BrickMac', ...]).
        team_name: Collegiate team name.
        create_draft: Whether to create a Statlocker draft room.
        max_recent_matches: Match window (default: 200).
        deadlock_client: Optional injected DeadlockClient.
        statlocker_client: Optional injected StatlockerClient.

    Returns:
        Tuple of (ExecutiveScoutingReport, list[PlayerSearchResult]).
    """
    d_client = deadlock_client or DeadlockClient()
    s_client = statlocker_client or StatlockerClient()

    # 1. Resolve usernames to Statlocker IDs
    search_results = await d_client.resolve_usernames_to_ids(usernames)

    unresolved = [r for r in search_results if not r.success or r.account_id is None]
    if unresolved:
        unresolved_names = ", ".join(f"'{r.search_query}'" for r in unresolved)
        raise ValueError(
            f"Failed to resolve {len(unresolved)} player username(s) to Statlocker IDs: {unresolved_names}"
        )

    resolved_ids = [str(r.account_id) for r in search_results if r.account_id is not None]

    # 2. Automatically run competitive scouting
    report = await run_scouting(
        opponent_inputs=resolved_ids,
        team_name=team_name,
        create_draft=create_draft,
        max_recent_matches=max_recent_matches,
        statlocker_client=s_client,
        deadlock_client=d_client,
    )
    report.resolved_players = search_results

    return report, search_results

