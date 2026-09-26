"""Unit tests for the Target Ban scoring engine, one-trick detection, and rank mapping."""

import math
import pytest
from analyzer import (
    analyze_player,
    calculate_ranked_characters,
    calculate_team_target_bans,
    calculate_threat_score,
    rank_number_to_name,
)
from models import HeroStatsRecord, PlayerProfile


def test_threat_score_exact_calculation() -> None:
    # Matches = 100, WR = 0.65, PP = 6000
    # sqrt(100) = 10
    # 0.65 - 0.45 = 0.20
    # 1 + 6000 / 10000 = 1.6
    # 10 * 0.20 * 1.6 * 10 = 32.0
    score = calculate_threat_score(matches_played=100, win_rate=0.65, pp_score=6000)
    assert pytest.approx(score, rel=1e-4) == 32.0


def test_threat_score_min_matches_filter() -> None:
    # 4 matches is below default threshold of 5
    score = calculate_threat_score(matches_played=4, win_rate=1.0, pp_score=7000)
    assert score == 0.0

    # 5 matches is allowed
    score_5 = calculate_threat_score(matches_played=5, win_rate=0.60, pp_score=5000)
    assert score_5 > 0.0


def test_threat_score_clamping() -> None:
    # WR below baseline 0.45
    score_clamped = calculate_threat_score(matches_played=20, win_rate=0.40, pp_score=5000, clamp_negative=True)
    assert score_clamped == 0.0

    score_unclamped = calculate_threat_score(matches_played=20, win_rate=0.40, pp_score=5000, clamp_negative=False)
    assert score_unclamped < 0.0


def test_one_trick_detection_positive() -> None:
    # Player with 110 games on Seven out of 150 total games (73.3% >= 55%)
    records = [
        HeroStatsRecord(account_id=1, hero_id=2, hero_name="Seven", matches_played=110, wins=75, win_rate=75/110),
        HeroStatsRecord(account_id=1, hero_id=13, hero_name="Haze", matches_played=25, wins=15, win_rate=15/25),
        HeroStatsRecord(account_id=1, hero_id=7, hero_name="Wraith", matches_played=15, wins=8, win_rate=8/15),
    ]
    profile = analyze_player(
        account_id=1,
        personaname="AggieHunter",
        pp_score=6500,
        estimated_rank_number=9,
        hero_records=records,
    )
    assert profile.is_one_trick is True
    assert profile.one_trick_hero == "Seven"
    assert profile.one_trick_pct is not None
    assert pytest.approx(profile.one_trick_pct, rel=1e-3) == 110 / 150


def test_one_trick_detection_negative_flexible() -> None:
    # Player with evenly distributed hero pool (highest is 30/100 = 30% < 55%)
    records = [
        HeroStatsRecord(account_id=2, hero_id=1, hero_name="Infernus", matches_played=30, wins=18, win_rate=0.6),
        HeroStatsRecord(account_id=2, hero_id=27, hero_name="Yamato", matches_played=25, wins=16, win_rate=0.64),
        HeroStatsRecord(account_id=2, hero_id=6, hero_name="Abrams", matches_played=25, wins=15, win_rate=0.6),
        HeroStatsRecord(account_id=2, hero_id=19, hero_name="Shiv", matches_played=20, wins=12, win_rate=0.6),
    ]
    profile = analyze_player(
        account_id=2,
        personaname="FlexGod",
        pp_score=7200,
        estimated_rank_number=10,
        hero_records=records,
    )
    assert profile.is_one_trick is False
    assert profile.one_trick_hero is None


def test_rank_conversion() -> None:
    assert rank_number_to_name(8) == "Oracle"
    assert rank_number_to_name(9) == "Phantom"
    assert rank_number_to_name(83) == "Oracle III"
    assert rank_number_to_name(102) == "Ascendant II"
    assert rank_number_to_name(111) == "Eternus I"


def test_team_target_ban_aggregation() -> None:
    # Player 1 has Seven (threat 25.0) and Haze (threat 10.0)
    p1 = PlayerProfile(
        account_id=101,
        personaname="P1",
        pp_score=6000,
        heroes=[
            HeroStatsRecord(account_id=101, hero_id=2, hero_name="Seven", matches_played=50, wins=35, win_rate=0.7, threat_score=25.0),
            HeroStatsRecord(account_id=101, hero_id=13, hero_name="Haze", matches_played=20, wins=13, win_rate=0.65, threat_score=10.0),
        ],
    )
    # Player 2 also plays Seven (threat 15.0) and Yamato (threat 30.0)
    p2 = PlayerProfile(
        account_id=102,
        personaname="P2",
        pp_score=6000,
        heroes=[
            HeroStatsRecord(account_id=102, hero_id=2, hero_name="Seven", matches_played=30, wins=20, win_rate=0.66, threat_score=15.0),
            HeroStatsRecord(account_id=102, hero_id=27, hero_name="Yamato", matches_played=60, wins=42, win_rate=0.7, threat_score=30.0),
        ],
    )
    # Player 3 plays Vindicta (threat 18.0)
    p3 = PlayerProfile(
        account_id=103,
        personaname="P3",
        pp_score=6000,
        heroes=[
            HeroStatsRecord(account_id=103, hero_id=3, hero_name="Vindicta", matches_played=35, wins=23, win_rate=0.65, threat_score=18.0),
        ],
    )

    bans = calculate_team_target_bans([p1, p2, p3], top_n=3)
    assert len(bans) == 3

    # Threat scores are NOT accumulated across players:
    # Yamato peak individual threat = 30.0 (P2)
    # Seven peak individual threat = 25.0 (P1)
    # Vindicta peak individual threat = 18.0 (P3)
    assert bans[0].hero_name == "Yamato"
    assert bans[0].total_threat_score == 30.0
    assert bans[1].hero_name == "Seven"
    assert bans[1].total_threat_score == 25.0
    assert bans[2].hero_name == "Vindicta"
    assert bans[2].total_threat_score == 18.0


def test_calculate_all_ranked_characters() -> None:
    p1 = PlayerProfile(
        account_id=101,
        personaname="P1",
        pp_score=6000,
        heroes=[
            HeroStatsRecord(account_id=101, hero_id=2, hero_name="Seven", matches_played=50, wins=35, win_rate=0.7, threat_score=25.0, kills=450, deaths=200, assists=500),
            HeroStatsRecord(account_id=101, hero_id=13, hero_name="Haze", matches_played=20, wins=13, win_rate=0.65, threat_score=10.0, kills=160, deaths=80, assists=180),
        ],
    )
    p2 = PlayerProfile(
        account_id=102,
        personaname="P2",
        pp_score=6000,
        heroes=[
            HeroStatsRecord(account_id=102, hero_id=27, hero_name="Yamato", matches_played=60, wins=42, win_rate=0.7, threat_score=30.0, kills=600, deaths=240, assists=480),
            HeroStatsRecord(account_id=102, hero_id=1, hero_name="Infernus", matches_played=15, wins=9, win_rate=0.6, threat_score=8.0, kills=120, deaths=75, assists=150),
        ],
    )

    ranked_all = calculate_ranked_characters([p1, p2])
    # ALL 4 heroes played across the roster must be present and ranked:
    assert len(ranked_all) == 4
    assert ranked_all[0].hero_name == "Yamato"
    assert ranked_all[0].threat_score == 30.0
    assert ranked_all[0].rank == 1
    assert "4.50" in ranked_all[0].kda_display  # (600+480)/240 = 4.5

    assert ranked_all[1].hero_name == "Seven"
    assert ranked_all[1].threat_score == 25.0
    assert ranked_all[1].rank == 2

    assert ranked_all[2].hero_name == "Haze"
    assert ranked_all[2].threat_score == 10.0
    assert ranked_all[2].rank == 3

    assert ranked_all[3].hero_name == "Infernus"
    assert ranked_all[3].threat_score == 8.0
    assert ranked_all[3].rank == 4
