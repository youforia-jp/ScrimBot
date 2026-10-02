"""Scoring engine, target ban aggregation, rank conversion, and one-trick detection."""

from __future__ import annotations

import math
from typing import Sequence
from config import settings
from models import HeroStatsRecord, PlayerProfile, RankedCharacterThreat, TeamBanTarget

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
    match_exponent: float = settings.match_weight_exponent,
    win_rate_baseline: float = settings.win_rate_threat_baseline,
) -> float:
    """
    Calculate the Ban Threat Score for a hero played by a specific opponent.

    Matches are weighted linearly (or via match_weight_exponent) so that high-volume
    comfort picks and signature mains carry substantially greater threat weight than
    low-sample flukes.

    Formula:
        Threat Score = (Matches Played ^ match_exponent) * (Win Rate - win_rate_baseline) * (1 + ppScore / 10000)

    Filters:
        - If matches_played < min_matches (default: 5), threat score is 0.0.
        - If clamp_negative is True, scores below 0.0 are clamped to 0.0.
    """
    if matches_played < min_matches:
        return 0.0

    skill_multiplier = 1.0 + (pp_score / 10000.0)
    match_factor = float(matches_played) ** match_exponent
    win_rate_factor = win_rate - win_rate_baseline
    score = match_factor * win_rate_factor * skill_multiplier

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


def calculate_ranked_characters(
    roster: Sequence[PlayerProfile],
) -> list[RankedCharacterThreat]:
    """
    Rank ALL characters played across the opponent roster by individual threat score.

    IMPORTANT: Threat scores are strictly NOT accumulated across players.
    Each character is represented by its primary opponent pilot with their individual
    threat score, win rate, match volume, and KDA statistics.
    Other pilots on the roster who also play that hero are listed with their own separate threat.
    """
    hero_pilots: dict[int, list[tuple[PlayerProfile, HeroStatsRecord]]] = {}

    for player in roster:
        for hero in player.heroes:
            if hero.matches_played == 0:
                continue
            if hero.hero_id not in hero_pilots:
                hero_pilots[hero.hero_id] = []
            hero_pilots[hero.hero_id].append((player, hero))

    ranked_list: list[RankedCharacterThreat] = []
    for hero_id, pilots in hero_pilots.items():
        # Sort pilots by individual threat score descending, then by matches played
        pilots.sort(key=lambda item: (item[1].threat_score, item[1].matches_played), reverse=True)
        primary_player, primary_hero = pilots[0]

        # Secondary pilots formatted with individual threat and stats (NOT summed)
        secondary_pilots_str = [
            f"{p.display_name} (Threat: {h.threat_score:.1f} | {h.win_rate*100:.0f}% WR in {h.matches_played}G | KDA: {h.kda_display})"
            for p, h in pilots[1:]
        ]

        ranked_list.append(
            RankedCharacterThreat(
                hero_id=hero_id,
                hero_name=primary_hero.hero_name,
                primary_player_name=primary_player.display_name,
                primary_account_id=primary_player.account_id,
                threat_score=round(primary_hero.threat_score, 1),
                matches_played=primary_hero.matches_played,
                wins=primary_hero.wins,
                win_rate=primary_hero.win_rate,
                kills=primary_hero.kills,
                deaths=primary_hero.deaths,
                assists=primary_hero.assists,
                kda_display=primary_hero.kda_display,
                secondary_pilots=secondary_pilots_str,
            )
        )

    # Sort ALL characters by individual threat score descending, then by matches
    ranked_list.sort(key=lambda x: (x.threat_score, x.matches_played), reverse=True)

    # Assign 1-indexed ranks
    for idx, item in enumerate(ranked_list, start=1):
        item.rank = idx

    return ranked_list


def calculate_team_target_bans(
    roster: Sequence[PlayerProfile], top_n: int = 3
) -> list[TeamBanTarget]:
    """
    Get top target bans based on individual peak threat scores (NOT accumulated across players).
    """
    ranked_chars = calculate_ranked_characters(roster)
    results: list[TeamBanTarget] = []

    for item in ranked_chars[:top_n]:
        primary_threats_formatted = [
            f"{item.primary_player_name} ({item.win_rate * 100:.0f}% WR in {item.matches_played}G | Threat: {item.threat_score:.1f} | KDA: {item.kda_display})"
        ]
        if item.secondary_pilots:
            primary_threats_formatted.extend(item.secondary_pilots[:2])

        results.append(
            TeamBanTarget(
                hero_id=item.hero_id,
                hero_name=item.hero_name,
                total_threat_score=item.threat_score,
                primary_threats=primary_threats_formatted,
                total_matches=item.matches_played,
                total_wins=item.wins,
            )
        )

    return results
