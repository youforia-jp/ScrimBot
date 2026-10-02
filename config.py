"""Configuration settings and environment variable handling for Deadlock ScrimBot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Automatically load .env if present
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment or defaults."""

    # API Keys & Auth
    statlocker_api_key: str | None = os.getenv("STATLOCKER_API_KEY", "").strip() or None
    discord_bot_token: str | None = os.getenv("DISCORD_BOT_TOKEN", "").strip() or None

    # Collegiate Defaults
    default_team_name: str = os.getenv("TEAM_NAME", "Texas A&M White")
    default_pp_score: int = int(os.getenv("DEFAULT_PP_SCORE", "5000"))
    default_rank_number: int = int(os.getenv("DEFAULT_RANK_NUMBER", "8"))  # 8 = Oracle

    # Deadlock API Endpoints
    deadlock_base_url: str = os.getenv("DEADLOCK_API_BASE_URL", "https://api.deadlock-api.com")
    deadlock_hero_stats_endpoint: str = os.getenv(
        "DEADLOCK_HERO_STATS_ENDPOINT", "https://api.deadlock-api.com/v1/players/hero-stats"
    )
    deadlock_heroes_endpoint: str = os.getenv(
        "DEADLOCK_HEROES_ENDPOINT", "https://api.deadlock-api.com/v1/assets/heroes"
    )
    deadlock_steam_endpoint: str = os.getenv(
        "DEADLOCK_STEAM_ENDPOINT", "https://api.deadlock-api.com/v1/players/steam"
    )
    deadlock_steam_search_endpoint: str = os.getenv(
        "DEADLOCK_STEAM_SEARCH_ENDPOINT", "https://api.deadlock-api.com/v1/players/steam-search"
    )

    # Statlocker Endpoints
    statlocker_base_url: str = os.getenv("STATLOCKER_BASE_URL", "https://statlocker.gg")
    statlocker_profiles_endpoint: str = os.getenv(
        "STATLOCKER_PROFILES_ENDPOINT", "https://statlocker.gg/api/public/profiles"
    )
    statlocker_draft_endpoint: str = os.getenv(
        "STATLOCKER_DRAFT_ENDPOINT", "https://statlocker.gg/api/public-draft/draft"
    )

    # Network
    http_timeout: float = float(os.getenv("HTTP_TIMEOUT", "10.0"))

    # Scoring & Thresholds
    min_matches_played: int = int(os.getenv("MIN_MATCHES_PLAYED", "5"))
    one_trick_threshold: float = float(os.getenv("ONE_TRICK_THRESHOLD", "0.55"))  # 55% of total games
    win_rate_threat_baseline: float = float(os.getenv("WIN_RATE_THREAT_BASELINE", "0.30"))
    match_weight_exponent: float = float(os.getenv("MATCH_WEIGHT_EXPONENT", "1.0"))
    max_recent_matches: int = int(os.getenv("MAX_RECENT_MATCHES", "200"))


settings = Settings()
