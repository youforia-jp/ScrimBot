"""Scouting orchestrator service coordinating data fetching, analysis, and draft creation."""

from __future__ import annotations

import logging
from typing import Sequence
from config import settings
from id_parser import parse_opponent_roster
from models import DraftLobbyResponse, ExecutiveScoutingReport, PlayerProfile
from api_client import DeadlockClient, StatlockerClient
from analyzer import analyze_player, calculate_team_target_bans
from mock_data import generate_mock_roster

logger = logging.getLogger(__name__)


async def run_scouting(
    opponent_inputs: Sequence[str],
    team_name: str = settings.default_team_name,
    create_draft: bool = False,
    mock_mode: bool = False,
    statlocker_client: StatlockerClient | None = None,
    deadlock_client: DeadlockClient | None = None,
) -> ExecutiveScoutingReport:
    """
    Execute full competitive scouting workflow for an opponent roster.

    Args:
        opponent_inputs: 6 player profile URLs, Steam vanity links, or Steam32 IDs.
        team_name: Collegiate team name.
        create_draft: Whether to create a public Statlocker draft lobby.
        mock_mode: If True, uses realistic collegiate mock data without external network calls.
        statlocker_client: Optional injected StatlockerClient.
        deadlock_client: Optional injected DeadlockClient.

    Returns:
        ExecutiveScoutingReport containing target bans, opponent breakdown, and draft link.
    """
    if mock_mode:
        roster = generate_mock_roster()
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
            target_bans=target_bans,
            draft_lobby=draft_response,
            statlocker_connected=True,
            deadlock_connected=True,
        )

    # 1. Parse Steam32 IDs
    account_ids = parse_opponent_roster(opponent_inputs)
    if not account_ids:
        raise ValueError("No valid Steam32 account IDs provided.")

    s_client = statlocker_client or StatlockerClient()
    d_client = deadlock_client or DeadlockClient()

    # 2. Concurrently fetch Statlocker ratings, Deadlock hero stats, and Steam persona names
    statlocker_task = s_client.fetch_profiles(account_ids)
    hero_stats_task = d_client.fetch_all_players_hero_stats(account_ids)
    persona_task = d_client.fetch_steam_profiles(account_ids)

    import asyncio
    statlocker_data, hero_stats_data, persona_names = await asyncio.gather(
        statlocker_task, hero_stats_task, persona_task, return_exceptions=False
    )

    # 3. Analyze each opponent player
    roster: list[PlayerProfile] = []
    for acc_id in account_ids:
        sl_profile = statlocker_data.get(acc_id, {})
        pp_score = int(sl_profile.get("ppScore", settings.default_pp_score))
        est_rank = int(sl_profile.get("estimatedRankNumber", settings.default_rank_number))
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

    # 4. Compute Cumulative Team Target Bans
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
        target_bans=target_bans,
        draft_lobby=draft_response,
        statlocker_connected=s_client.connected,
        deadlock_connected=d_client.connected,
    )
