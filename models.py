"""Pydantic and dataclass models for Deadlock ScrimBot."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field, computed_field


class HeroStatsRecord(BaseModel):
    """Stats for a single hero played by a specific player."""

    account_id: int
    hero_id: int
    hero_name: str = "Unknown"
    matches_played: int = 0
    wins: int = 0
    win_rate: float = 0.0
    threat_score: float = 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def losses(self) -> int:
        return max(0, self.matches_played - self.wins)


class PlayerProfile(BaseModel):
    """Complete scouting profile for an opponent player."""

    account_id: int
    personaname: str = ""
    pp_score: int = 5000
    estimated_rank_number: int = 8
    rank_name: str = "Oracle"
    total_matches: int = 0
    heroes: list[HeroStatsRecord] = Field(default_factory=list)
    is_one_trick: bool = False
    one_trick_hero: str | None = None
    one_trick_pct: float | None = None
    comfort_heroes: list[HeroStatsRecord] = Field(default_factory=list)

    @property
    def display_name(self) -> str:
        """Formatted display name falling back to Account ID."""
        return self.personaname if self.personaname else f"Player {self.account_id}"


class TeamBanTarget(BaseModel):
    """A target-ban priority hero aggregated across opponent roster."""

    hero_id: int
    hero_name: str
    total_threat_score: float
    primary_threats: list[str] = Field(default_factory=list)  # e.g., ["JohnDoe (Threat 14.2)", "Sniper (Threat 9.1)"]
    total_matches: int = 0
    total_wins: int = 0

    @property
    def aggregate_win_rate(self) -> float:
        if self.total_matches == 0:
            return 0.0
        return self.total_wins / self.total_matches


class DraftLobbyResponse(BaseModel):
    """Response from Statlocker draft lobby creation."""

    draft_id: str | None = None
    draft_url: str | None = None
    success: bool = False
    message: str = ""


class ExecutiveScoutingReport(BaseModel):
    """Full executive scouting report ready for terminal rendering or Discord embed."""

    team_name: str
    created_at: datetime = Field(default_factory=datetime.now)
    opponents: list[PlayerProfile] = Field(default_factory=list)
    target_bans: list[TeamBanTarget] = Field(default_factory=list)
    draft_lobby: DraftLobbyResponse | None = None
    statlocker_connected: bool = False
    deadlock_connected: bool = True
