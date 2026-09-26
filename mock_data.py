"""Mock data generator for offline demos and automated test fixtures."""

from __future__ import annotations

from models import HeroStatsRecord, PlayerProfile
from analyzer import analyze_player

MOCK_OPPONENT_PROFILES: list[dict] = [
    {
        "account_id": 105829141,
        "personaname": "AggieHunter",
        "pp_score": 6850,
        "estimated_rank_number": 92,  # Phantom II
        "heroes": [
            {"hero_id": 2, "hero_name": "Seven", "matches": 110, "wins": 76},  # 69.1% WR
            {"hero_id": 13, "hero_name": "Haze", "matches": 22, "wins": 13},   # 59.1% WR
            {"hero_id": 7, "hero_name": "Wraith", "matches": 15, "wins": 8},   # 53.3% WR
            {"hero_id": 3, "hero_name": "Vindicta", "matches": 6, "wins": 3},  # 50.0% WR
        ],  # Total = 153 games. Seven is 110/153 = 71.9% -> ONE-TRICK!
    },
    {
        "account_id": 89410294,
        "personaname": "LoneStarCarry",
        "pp_score": 7420,
        "estimated_rank_number": 101,  # Ascendant I
        "heroes": [
            {"hero_id": 27, "hero_name": "Yamato", "matches": 85, "wins": 57},  # 67.1% WR
            {"hero_id": 1, "hero_name": "Infernus", "matches": 60, "wins": 38}, # 63.3% WR
            {"hero_id": 6, "hero_name": "Abrams", "matches": 40, "wins": 21},   # 52.5% WR
            {"hero_id": 50, "hero_name": "Pocket", "matches": 18, "wins": 11},  # 61.1% WR
        ],
    },
    {
        "account_id": 120489110,
        "personaname": "HookCityBebop",
        "pp_score": 5980,
        "estimated_rank_number": 84,  # Oracle IV
        "heroes": [
            {"hero_id": 15, "hero_name": "Bebop", "matches": 72, "wins": 46},   # 63.9% WR
            {"hero_id": 11, "hero_name": "Dynamo", "matches": 25, "wins": 14},  # 56.0% WR
            {"hero_id": 20, "hero_name": "Ivy", "matches": 12, "wins": 7},      # 58.3% WR
            {"hero_id": 12, "hero_name": "Kelvin", "matches": 8, "wins": 3},    # 37.5% WR
        ],
    },
    {
        "account_id": 145920391,
        "personaname": "SniperElite",
        "pp_score": 6200,
        "estimated_rank_number": 86,  # Oracle VI
        "heroes": [
            {"hero_id": 3, "hero_name": "Vindicta", "matches": 64, "wins": 41}, # 64.1% WR
            {"hero_id": 17, "hero_name": "Grey Talon", "matches": 38, "wins": 23}, # 60.5% WR
            {"hero_id": 2, "hero_name": "Seven", "matches": 20, "wins": 12},    # 60.0% WR
            {"hero_id": 7, "hero_name": "Wraith", "matches": 14, "wins": 8},    # 57.1% WR
        ],
    },
    {
        "account_id": 77489201,
        "personaname": "FrontlineTank",
        "pp_score": 5400,
        "estimated_rank_number": 75,  # Emissary V
        "heroes": [
            {"hero_id": 6, "hero_name": "Abrams", "matches": 90, "wins": 54},   # 60.0% WR
            {"hero_id": 18, "hero_name": "Mo & Krill", "matches": 45, "wins": 26}, # 57.8% WR
            {"hero_id": 25, "hero_name": "Warden", "matches": 30, "wins": 17},  # 56.7% WR
            {"hero_id": 12, "hero_name": "Kelvin", "matches": 15, "wins": 8},   # 53.3% WR
        ],
    },
    {
        "account_id": 99381023,
        "personaname": "FlexGod_TX",
        "pp_score": 6150,
        "estimated_rank_number": 85,  # Oracle V
        "heroes": [
            {"hero_id": 19, "hero_name": "Shiv", "matches": 35, "wins": 22},    # 62.9% WR
            {"hero_id": 31, "hero_name": "Lash", "matches": 30, "wins": 18},    # 60.0% WR
            {"hero_id": 27, "hero_name": "Yamato", "matches": 28, "wins": 17},  # 60.7% WR
            {"hero_id": 1, "hero_name": "Infernus", "matches": 25, "wins": 15}, # 60.0% WR
            {"hero_id": 2, "hero_name": "Seven", "matches": 10, "wins": 6},     # 60.0% WR
        ],
    },
]


def generate_mock_roster() -> list[PlayerProfile]:
    """Generate a realistic 6-player opponent scouting roster."""
    roster: list[PlayerProfile] = []
    for data in MOCK_OPPONENT_PROFILES:
        hero_records: list[HeroStatsRecord] = []
        for h in data["heroes"]:
            m = h["matches"]
            w = h["wins"]
            wr = w / m if m > 0 else 0.0
            k = h.get("kills", int(m * (8.5 if wr > 0.6 else 6.2)))
            d = h.get("deaths", int(m * (3.8 if wr > 0.6 else 5.4)))
            a = h.get("assists", int(m * (9.4 if wr > 0.6 else 7.0)))
            hero_records.append(
                HeroStatsRecord(
                    account_id=data["account_id"],
                    hero_id=h["hero_id"],
                    hero_name=h["hero_name"],
                    matches_played=m,
                    wins=w,
                    win_rate=wr,
                    kills=k,
                    deaths=d,
                    assists=a,
                )
            )

        profile = analyze_player(
            account_id=data["account_id"],
            personaname=data["personaname"],
            pp_score=data["pp_score"],
            estimated_rank_number=data["estimated_rank_number"],
            hero_records=hero_records,
        )
        roster.append(profile)

    return roster
