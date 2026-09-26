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


@pytest.mark.skipif(not HAS_DISCORD, reason="discord.py is required for this test")
def test_discord_embed_field_length_strict_under_1024() -> None:
    """Verify that every field value is strictly <= 1024 chars even with a massive hero pool."""
    from models import RankedCharacterThreat

    # Simulate 50 heroes played by opponents
    huge_hero_list = []
    for i in range(1, 51):
        huge_hero_list.append(
            RankedCharacterThreat(
                rank=i,
                hero_id=i,
                hero_name=f"HeroNumber{i}",
                primary_player_name=f"VeryLongOpponentPlayerName_{i}",
                primary_account_id=100000 + i,
                threat_score=float(100 - i),
                matches_played=50 + i,
                wins=30 + i,
                win_rate=0.65,
                kills=350,
                deaths=150,
                assists=400,
                kda_display="7.0/3.0/8.0 (5.00)",
                secondary_pilots=[
                    f"AltPlayerAlpha_{i} (Threat: 15.0 | 55% WR in 20G | KDA: 5.0/4.0/6.0)",
                    f"AltPlayerBeta_{i} (Threat: 8.0 | 50% WR in 12G | KDA: 4.0/5.0/5.0)",
                ],
            )
        )

    roster = generate_mock_roster()
    report = ExecutiveScoutingReport(
        team_name="Texas A&M White",
        opponents=roster,
        ranked_characters=huge_hero_list,
        target_bans=[],
    )

    cog = DeadlockScoutCog(bot=None)
    embeds = cog.build_report_embeds(report)

    # Check Discord API invariants for all embeds
    for e_idx, embed in enumerate(embeds):
        assert len(embed.fields) <= 25, f"Embed #{e_idx} has {len(embed.fields)} fields (limit 25)"
        assert cog.get_embed_total_chars(embed) <= 6000, f"Embed #{e_idx} total size exceeds 6000 chars!"
        for f_idx, field in enumerate(embed.fields):
            assert len(field.name) <= 256, f"Field #{f_idx} in Embed #{e_idx} name > 256 chars"
            assert len(field.value) <= 1024, f"Field #{f_idx} ('{field.name}') in Embed #{e_idx} value length {len(field.value)} > 1024 chars!"
            assert len(field.value) > 0, "Field value cannot be empty"


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_DISCORD, reason="discord.py is required for this test")
async def test_discord_embed_message_batching_strict_under_6000() -> None:
    """Verify that _send_embeds_safely batches messages strictly under Discord's 6000-char message limit."""
    from unittest.mock import AsyncMock
    from models import RankedCharacterThreat

    # Simulate 60 heroes to generate a very large multi-embed report
    large_hero_list = []
    for i in range(1, 61):
        large_hero_list.append(
            RankedCharacterThreat(
                rank=i,
                hero_id=i,
                hero_name=f"HeroAlphaBeta_{i}",
                primary_player_name=f"CollegiateOpponent_{i}",
                primary_account_id=200000 + i,
                threat_score=float(120 - i),
                matches_played=40 + i,
                wins=25 + i,
                win_rate=0.62,
                kills=280,
                deaths=120,
                assists=310,
                kda_display="7.0/3.0/7.8 (4.92)",
                secondary_pilots=[
                    f"BackupPilot_{i} (Threat: 14.5 | 52% WR in 25G | KDA: 4.5/4.0/6.0)"
                ],
            )
        )

    roster = generate_mock_roster()
    report = ExecutiveScoutingReport(
        team_name="Texas A&M White",
        opponents=roster,
        ranked_characters=large_hero_list,
        target_bans=[],
    )

    cog = DeadlockScoutCog(bot=None)
    embeds = cog.build_report_embeds(report)

    # 1. Every single individual embed must strictly be <= 6000 characters
    for idx, emb in enumerate(embeds):
        total_chars = cog.get_embed_total_chars(emb)
        assert total_chars <= 6000, f"Embed #{idx} has {total_chars} chars (limit 6000)"

    # 2. Test batch sending
    mock_send = AsyncMock()
    await cog._send_embeds_safely(mock_send, embeds)

    assert mock_send.call_count >= 1

    dispatched_embeds = []
    for call in mock_send.call_args_list:
        call_embeds = call.kwargs.get("embeds", [])
        assert len(call_embeds) <= 10, f"Message contained {len(call_embeds)} embeds (limit 10)"
        msg_total_chars = sum(cog.get_embed_total_chars(e) for e in call_embeds)
        assert msg_total_chars <= 6000, f"Message total embed size {msg_total_chars} exceeds 6000!"
        dispatched_embeds.extend(call_embeds)

    assert len(dispatched_embeds) == len(embeds)
