"""Scoring engine, target ban aggregation, rank conversion, and one-trick detection."""

from __future__ import annotations

import math
from typing import Sequence
from config import settings
from models import HeroStatsRecord, PlayerProfile, TeamBanTarget

# Deadlock Rank Tier Mappings
DEADLOCK_RANK_NAMES: dict[int, str] = {
    0: "Obscurus (Unranked)",
    1: "Initiate",
    2: "Seeker",
    3: "Acolyte",
    4: "Sentinel",
    5: "Mystic",
    6: "Ritualist",
    7: "Emissary",
    8: "Oracle",
    9: "Phantom",
    10: "Ascendant",
    11: "Eternus",
}

ROMAN_NUMERALS: dict[int, str] = {
    1: "I",
    2: "II",
    3: "III",
    4: "IV",
    5: "V",
    6: "VI",
}


def rank_number_to_name(rank_number: int, pp_score: int | None = None) -> str:
    """
    Convert an estimated rank number or PP score into a readable Deadlock tier name.
    
    Supports:
    - Base tier numbers (e.g., 8 -> "Oracle")
    - Composite tier-subtier codes (e.g., 83 -> "Oracle III")
    - Fallback estimation based on PP score
    """
    if rank_number in DEADLOCK_RANK_NAMES:
        return DEADLOCK_RANK_NAMES[rank_number]

    # Check for composite tier + subtier representation (e.g., 84 = tier 8, sub-tier 4)
    if rank_number >= 10:
        tier = rank_number // 10
        subtier = rank_number % 10
        if tier in DEADLOCK_RANK_NAMES:
            subtier_roman = ROMAN_NUMERALS.get(subtier, str(subtier))
            return f"{DEADLOCK_RANK_NAMES[tier]} {subtier_roman}"

    # PP-based estimation fallback if rank_number is unrecognized/zero
    if pp_score is not None and pp_score > 0:
        return estimate_rank_from_pp(pp_score)

    return "Oracle"


def estimate_rank_from_pp(pp: int) -> str:
    """Estimate a Deadlock rank tier from PP score."""
    if pp < 1500:
        return "Initiate"
    if pp < 2200:
        return "Seeker"
    if pp < 2900:
        return "Acolyte"
    if pp < 3600:
        return "Sentinel"
    if pp < 4300:
        return "Mystic"
    if pp < 5000:
        return "Ritualist"
    if pp < 5700:
        return "Emissary"
    if pp < 6400:
        return "Oracle"
    if pp < 7200:
        return "Phantom"
    if pp < 8000:
        return "Ascendant"
    return "Eternus"


def calculate_threat_score(
    matches_played: int,
    win_rate: float,
    pp_score: int,
    min_matches: int = settings.min_matches_played,
    clamp_negative: bool = True,
) -> float:
    """
    Calculate the Ban Threat Score for a hero played by a specific opponent.

    Formula:
        Threat Score = sqrt(Matches Played) * (Win Rate - 0.45) * (1 + ppScore / 10000) * 10

    Filters:
        - If matches_played < min_matches (default: 5), threat score is 0.0.
        - If clamp_negative is True, scores below 0.0 are clamped to 0.0.
    """
    if matches_played < min_matches:
        return 0.0

    skill_multiplier = 1.0 + (pp_score / 10000.0)
    score = math.sqrt(matches_played) * (win_rate - settings.win_rate_threat_baseline) * skill_multiplier * 10.0

    if clamp_negative:
        return max(0.0, score)
    return score


def analyze_player(
    account_id: int,
    personaname: str,
    pp_score: int,
    estimated_rank_number: int,
    hero_records: Sequence[HeroStatsRecord],
) -> PlayerProfile:
    """
    Analyze an individual player's hero pool, comfort picks, and one-trick status.
    """
    total_matches = sum(h.matches_played for h in hero_records)
    scored_heroes: list[HeroStatsRecord] = []

    for hero in hero_records:
        threat = calculate_threat_score(
            matches_played=hero.matches_played,
            win_rate=hero.win_rate,
            pp_score=pp_score,
            clamp_negative=True,
        )
        scored_hero = hero.model_copy(update={"threat_score": threat})
        scored_heroes.append(scored_hero)

    # Sort heroes by games and threat to identify comfort heroes
    scored_heroes.sort(key=lambda h: (h.threat_score, h.matches_played), reverse=True)

    # One-Trick Detection: Flag if most-played hero constitutes >= 55% of total recorded games
    is_one_trick = False
    one_trick_hero: str | None = None
    one_trick_pct: float | None = None

    if total_matches > 0 and scored_heroes:
        # Most played hero
        most_played = max(scored_heroes, key=lambda h: h.matches_played)
        ratio = most_played.matches_played / total_matches
        if ratio >= settings.one_trick_threshold and most_played.matches_played >= settings.min_matches_played:
            is_one_trick = True
            one_trick_hero = most_played.hero_name
            one_trick_pct = ratio

    # Top 2 comfort heroes (at least 1 match played)
    comfort_heroes = [h for h in scored_heroes if h.matches_played > 0][:2]

    rank_name = rank_number_to_name(estimated_rank_number, pp_score)

    return PlayerProfile(
        account_id=account_id,
        personaname=personaname,
        pp_score=pp_score,
        estimated_rank_number=estimated_rank_number,
        rank_name=rank_name,
        total_matches=total_matches,
        heroes=scored_heroes,
        is_one_trick=is_one_trick,
        one_trick_hero=one_trick_hero,
        one_trick_pct=one_trick_pct,
        comfort_heroes=comfort_heroes,
    )


def calculate_team_target_bans(
    roster: Sequence[PlayerProfile], top_n: int = 3
) -> list[TeamBanTarget]:
    """
    Aggregate hero threat scores across all 6 players on the opponent roster.
    
    Generates a cumulative "Team Ban Priority" top list, with primary hazard players annotated.
    """
    # Map hero_id -> aggregate stats
    hero_aggregates: dict[int, dict] = {}

    for player in roster:
        player_name = player.display_name
        for hero in player.heroes:
            if hero.matches_played < settings.min_matches_played:
                continue

            if hero.hero_id not in hero_aggregates:
                hero_aggregates[hero.hero_id] = {
                    "hero_id": hero.hero_id,
                    "hero_name": hero.hero_name,
                    "total_threat_score": 0.0,
                    "player_threats": [],
                    "total_matches": 0,
                    "total_wins": 0,
                }

            agg = hero_aggregates[hero.hero_id]
            agg["total_threat_score"] += hero.threat_score
            agg["total_matches"] += hero.matches_played
            agg["total_wins"] += hero.wins
            if hero.threat_score > 0.0:
                agg["player_threats"].append((player_name, hero.threat_score, hero.win_rate, hero.matches_played))

    # Sort heroes by total threat score descending
    sorted_heroes = sorted(
        hero_aggregates.values(), key=lambda x: x["total_threat_score"], reverse=True
    )

    results: list[TeamBanTarget] = []
    for item in sorted_heroes[:top_n]:
        # Format primary threats on roster sorted by individual threat
        sorted_threats = sorted(item["player_threats"], key=lambda pt: pt[1], reverse=True)
        primary_threats_formatted = [
            f"{name} ({wr * 100:.0f}% WR in {games}G | Threat: {th:.1f})"
            for name, th, wr, games in sorted_threats[:3]
        ]

        results.append(
            TeamBanTarget(
                hero_id=item["hero_id"],
                hero_name=item["hero_name"],
                total_threat_score=round(item["total_threat_score"], 2),
                primary_threats=primary_threats_formatted,
                total_matches=item["total_matches"],
                total_wins=item["total_wins"],
            )
        )

    return results
