"""Unit tests for Discord bot integration and embed formatting."""

import pytest
from mock_data import generate_mock_roster
from analyzer import calculate_ranked_characters, calculate_team_target_bans
from models import ExecutiveScoutingReport, DraftLobbyResponse
from discord_cog import DeadlockScoutCog, HAS_DISCORD


@pytest.mark.skipif(not HAS_DISCORD, reason="discord.py is required for this test")
def test_discord_embed_generation() -> None:
    roster = generate_mock_roster()
    ranked_chars = calculate_ranked_characters(roster)
    bans = calculate_team_target_bans(roster, top_n=3)
    draft_lobby = DraftLobbyResponse(
        draft_id="lobby-test-1",
        draft_url="https://statlocker.gg/draft/lobby-test-1",
        success=True,
    )
    report = ExecutiveScoutingReport(
        team_name="Texas A&M White",
        opponents=roster,
        ranked_characters=ranked_chars,
        target_bans=bans,
        draft_lobby=draft_lobby,
        statlocker_connected=True,
        deadlock_connected=True,
    )

    cog = DeadlockScoutCog(bot=None)
    embeds = cog.build_report_embeds(report)

    assert len(embeds) == 2

    # Main Embed (Ranked Character Threats)
    main_embed = embeds[0]
    assert "Collegiate Deadlock Scouting Report" in main_embed.title
    ban_field = next((f for f in main_embed.fields if "Ranked Character Threat List" in f.name), None)
    assert ban_field is not None
    assert "Seven" in ban_field.value
    assert "Yamato" in ban_field.value
    assert "KDA:" in ban_field.value

    # Draft link field
    draft_field = next((f for f in main_embed.fields if "Statlocker Draft Room" in f.name), None)
    assert draft_field is not None
    assert "https://statlocker.gg/draft/lobby-test-1" in draft_field.value

    # Roster Embed
    roster_embed = embeds[1]
    assert "Opponent Roster" in roster_embed.title
    assert len(roster_embed.fields) == 6

    # AggieHunter should have ONE-TRICK in value
    aggie_field = next((f for f in roster_embed.fields if "AggieHunter" in f.name), None)
    assert aggie_field is not None
    assert "ONE-TRICK" in aggie_field.value
