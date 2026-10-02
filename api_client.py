"""Asynchronous API clients for Statlocker.gg and Deadlock API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Sequence
import httpx

from config import settings
from models import DraftLobbyResponse, HeroStatsRecord, PlayerSearchResult

logger = logging.getLogger(__name__)

# Complete fallback hero directory for Deadlock
STATIC_HERO_NAMES: dict[int, str] = {
    1: "Infernus",
    2: "Seven",
    3: "Vindicta",
    4: "Lady Geist",
    6: "Abrams",
    7: "Wraith",
    8: "McGinnis",
    10: "Paradox",
    11: "Dynamo",
    12: "Kelvin",
    13: "Haze",
    14: "Holliday",
    15: "Bebop",
    16: "Calico",
    17: "Grey Talon",
    18: "Mo & Krill",
    19: "Shiv",
    20: "Ivy",
    21: "Kali",
    25: "Warden",
    27: "Yamato",
    31: "Lash",
    35: "Viscous",
    38: "Gunslinger",
    39: "The Boss",
    47: "Tokamak",
    48: "Wrecker",
    49: "Rutger",
    50: "Pocket",
    51: "Thumper",
    52: "Mirage",
    53: "Fathom",
    54: "Cadence",
    56: "Bomber",
    57: "Shield Guy",
    58: "Vyper",
    59: "Vandal",
    60: "Sinclair",
    61: "Trapper",
    62: "Raven",
    63: "Mina",
    64: "Drifter",
    65: "Venator",
    66: "Victor",
    67: "Paige",
    68: "Boho",
    69: "The Doorman",
    70: "Skyrunner",
    71: "Swan",
    72: "Billy",
    74: "Graf",
    75: "Fortuna",
    76: "Graves",
    77: "Apollo",
    79: "Rem",
    80: "Silver",
    81: "Celeste",
}


class StatlockerClient:
    """Client for querying skill ratings and creating draft lobbies via Statlocker.gg."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = settings.http_timeout,
    ) -> None:
        self.api_key = api_key or settings.statlocker_api_key
        self.timeout = timeout
        self.connected: bool = False

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Deadlock-Collegiate-Scout/1.0",
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def fetch_profiles(
        self, account_ids: Sequence[int]
    ) -> dict[int, dict[str, Any]]:
        """
        Fetch skill ratings (ppScore, estimatedRankNumber) for a list of Steam32 account IDs.

        Fallback:
            If API key is missing or request fails (401/429/500/timeout), returns
            a default PP score (5000 / Oracle baseline) without raising exceptions.
        """
        results: dict[int, dict[str, Any]] = {}
        fallback_data = {
            acc_id: {
                "ppScore": settings.default_pp_score,
                "estimatedRankNumber": settings.default_rank_number,
            }
            for acc_id in account_ids
        }

        if not self.api_key:
            logger.info("Statlocker API key not configured; using default PP=5000 (Oracle).")
            self.connected = False
            return fallback_data

        payload = list(account_ids)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    settings.statlocker_profiles_endpoint,
                    json=payload,
                    headers=self._get_headers(),
                )

                if response.status_code == 200:
                    data = response.json()
                    self.connected = True
                    # Data can be a list of player dicts or a mapping
                    if isinstance(data, list):
                        for item in data:
                            acc_id = item.get("accountId") or item.get("account_id") or item.get("id")
                            if acc_id is not None:
                                results[int(acc_id)] = {
                                    "ppScore": item.get("ppScore", item.get("pp_score", settings.default_pp_score)),
                                    "estimatedRankNumber": item.get(
                                        "estimatedRankNumber",
                                        item.get("estimated_rank_number", settings.default_rank_number),
                                    ),
                                }
                    elif isinstance(data, dict):
                        for key, item in data.items():
                            try:
                                acc_id = int(key)
                                results[acc_id] = {
                                    "ppScore": item.get("ppScore", item.get("pp_score", settings.default_pp_score)),
                                    "estimatedRankNumber": item.get(
                                        "estimatedRankNumber",
                                        item.get("estimated_rank_number", settings.default_rank_number),
                                    ),
                                }
                            except (ValueError, TypeError):
                                pass

                    # Fill any missing accounts with default fallback
                    for acc_id in account_ids:
                        if acc_id not in results:
                            results[acc_id] = fallback_data[acc_id]

                    return results

                logger.warning(
                    "Statlocker API returned HTTP %s: %s. Falling back to default baseline.",
                    response.status_code,
                    response.text[:200],
                )
                self.connected = False
                return fallback_data

        except Exception as exc:
            logger.warning(
                "Failed to reach Statlocker API (%s). Falling back gracefully to default PP.",
                exc,
            )
            self.connected = False
            return fallback_data

    async def create_draft_lobby(
        self,
        opponent_ids: Sequence[int],
        team_name: str = settings.default_team_name,
        draft_name: str = "Collegiate Scrim",
        timer_type: str = "HYBRID",
        preset: str = "COMPETITIVE",
    ) -> DraftLobbyResponse:
        """
        Create a public competitive draft room on Statlocker.gg.
        """
        if not self.api_key:
            return DraftLobbyResponse(
                success=False,
                message="Statlocker API key not configured; skipping draft lobby creation.",
            )

        payload = {
            "team1": {"name": team_name},
            "team2": {"name": "Opponents", "accountIds": list(opponent_ids)},
            "draftSettings": {
                "draftName": draft_name,
                "timerType": timer_type,
                "preset": preset,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    settings.statlocker_draft_endpoint,
                    json=payload,
                    headers=self._get_headers(),
                )

                if response.status_code in (200, 201):
                    data = response.json()
                    draft_url = (
                        data.get("draftUrl")
                        or data.get("draft_url")
                        or data.get("url")
                    )
                    draft_id = str(data.get("draftId") or data.get("id") or "")

                    if not draft_url and draft_id:
                        draft_url = f"https://statlocker.gg/draft/{draft_id}"

                    return DraftLobbyResponse(
                        draft_id=draft_id,
                        draft_url=draft_url,
                        success=True,
                        message="Draft lobby generated successfully.",
                    )

                return DraftLobbyResponse(
                    success=False,
                    message=f"Draft creation failed with HTTP {response.status_code}: {response.text[:150]}",
                )
        except Exception as exc:
            logger.warning("Error creating Statlocker draft lobby: %s", exc)
            return DraftLobbyResponse(
                success=False,
                message=f"Network error creating draft: {exc}",
            )


class DeadlockClient:
    """Client for querying player stats and hero records from Deadlock API."""

    def __init__(self, timeout: float = settings.http_timeout) -> None:
        self.timeout = timeout
        self.hero_names: dict[int, str] = dict(STATIC_HERO_NAMES)
        self.connected: bool = True

    def _get_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": "Deadlock-Collegiate-Scout/1.0",
        }

    async def fetch_hero_assets(self) -> dict[int, str]:
        """Fetch dynamic hero ID to hero name mappings from Deadlock API."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    settings.deadlock_heroes_endpoint, headers=self._get_headers()
                )
                if response.status_code == 200:
                    data = response.json()
                    for item in data:
                        h_id = item.get("id")
                        h_name = item.get("name")
                        if h_id is not None and h_name:
                            self.hero_names[int(h_id)] = str(h_name)
        except Exception as exc:
            logger.debug("Using fallback static hero assets: %s", exc)
        return self.hero_names

    async def fetch_player_hero_stats(
        self,
        client: httpx.AsyncClient,
        account_id: int,
        max_matches: int | None = settings.max_recent_matches,
    ) -> list[HeroStatsRecord]:
        """
        Fetch hero statistics for a single player.

        If max_matches is provided and > 0, queries recent match history
        (/v1/players/{account_id}/match-history), takes the most recent
        `max_matches` (default 200), and computes recent hero performance, win rates,
        and KDA stats.

        Falls back gracefully to cumulative /v1/players/hero-stats if match-history
        is unavailable, empty, or returns an error.
        """
        if max_matches and max_matches > 0:
            history_url = f"{settings.deadlock_base_url}/v1/players/{account_id}/match-history"
            try:
                response = await client.get(history_url, headers=self._get_headers())
                if response.status_code == 200:
                    matches = response.json()
                    # Check if response contains individual match history records
                    if (
                        isinstance(matches, list)
                        and len(matches) > 0
                        and any(k in matches[0] for k in ("match_id", "match_result", "start_time"))
                    ):
                        recent_matches = matches[:max_matches]
                        hero_data: dict[int, dict[str, int]] = {}
                        for m in recent_matches:
                            h_id = m.get("hero_id")
                            if h_id is None:
                                continue
                            hero_id = int(h_id)
                            if hero_id not in hero_data:
                                hero_data[hero_id] = {
                                    "matches": 0,
                                    "wins": 0,
                                    "kills": 0,
                                    "deaths": 0,
                                    "assists": 0,
                                }
                            p_team = m.get("player_team")
                            m_result = m.get("match_result")
                            is_win = (p_team is not None and p_team == m_result) or (
                                m.get("player_match_outcome") == 1
                            )
                            hero_data[hero_id]["matches"] += 1
                            if is_win:
                                hero_data[hero_id]["wins"] += 1
                            hero_data[hero_id]["kills"] += int(m.get("player_kills") or 0)
                            hero_data[hero_id]["deaths"] += int(m.get("player_deaths") or 0)
                            hero_data[hero_id]["assists"] += int(m.get("player_assists") or 0)

                        records: list[HeroStatsRecord] = []
                        for hero_id, data in hero_data.items():
                            g = data["matches"]
                            w = data["wins"]
                            wr = (w / g) if g > 0 else 0.0
                            hero_name = self.hero_names.get(hero_id, f"Hero #{hero_id}")
                            records.append(
                                HeroStatsRecord(
                                    account_id=account_id,
                                    hero_id=hero_id,
                                    hero_name=hero_name,
                                    matches_played=g,
                                    wins=w,
                                    win_rate=wr,
                                    kills=data["kills"],
                                    deaths=data["deaths"],
                                    assists=data["assists"],
                                )
                            )
                        return records
            except Exception as exc:
                logger.debug(
                    "Match-history query failed for account %s (%s). Falling back to cumulative hero stats.",
                    account_id,
                    exc,
                )

        # Fallback or cumulative mode: Query standard hero-stats endpoint
        url = f"{settings.deadlock_hero_stats_endpoint}?account_ids={account_id}"
        try:
            response = await client.get(url, headers=self._get_headers())
            if response.status_code == 200:
                data = response.json()
                records: list[HeroStatsRecord] = []
                for entry in data:
                    h_id = entry.get("hero_id")
                    if h_id is None:
                        continue
                    hero_id = int(h_id)
                    matches = int(entry.get("matches_played", 0))
                    wins = int(entry.get("wins", 0))
                    win_rate = (wins / matches) if matches > 0 else 0.0
                    hero_name = self.hero_names.get(hero_id, f"Hero #{hero_id}")
                    kills = int(entry.get("kills", 0))
                    deaths = int(entry.get("deaths", 0))
                    assists = int(entry.get("assists", 0))

                    records.append(
                        HeroStatsRecord(
                            account_id=account_id,
                            hero_id=hero_id,
                            hero_name=hero_name,
                            matches_played=matches,
                            wins=wins,
                            win_rate=win_rate,
                            kills=kills,
                            deaths=deaths,
                            assists=assists,
                        )
                    )
                return records

            if response.status_code == 404:
                # Player has private or unrecorded matches
                return []

            logger.warning(
                "Deadlock API hero-stats query for player %s returned %s",
                account_id,
                response.status_code,
            )
            return []
        except Exception as exc:
            logger.warning("Network error querying hero stats for player %s: %s", account_id, exc)
            return []

    async def fetch_steam_profiles(
        self, account_ids: Sequence[int]
    ) -> dict[int, str]:
        """Fetch Steam persona names for account IDs."""
        names: dict[int, str] = {}
        ids_param = ",".join(str(i) for i in account_ids)
        url = f"{settings.deadlock_steam_endpoint}?account_ids={ids_param}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_headers())
                if response.status_code == 200:
                    data = response.json()
                    for item in data:
                        acc_id = item.get("account_id")
                        persona = item.get("personaname")
                        if acc_id and persona:
                            names[int(acc_id)] = persona
        except Exception as exc:
            logger.debug("Failed to fetch steam profile names: %s", exc)

        return names

    async def fetch_all_players_hero_stats(
        self,
        account_ids: Sequence[int],
        max_matches: int | None = settings.max_recent_matches,
    ) -> dict[int, list[HeroStatsRecord]]:
        """
        Fetch hero statistics for all players concurrently.
        """
        # First ensure hero assets are fresh
        await self.fetch_hero_assets()

        results: dict[int, list[HeroStatsRecord]] = {}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            tasks = [
                self.fetch_player_hero_stats(client, acc_id, max_matches=max_matches)
                for acc_id in account_ids
            ]
            stats_list = await asyncio.gather(*tasks, return_exceptions=True)

            for acc_id, res in zip(account_ids, stats_list):
                if isinstance(res, Exception):
                    logger.warning("Hero stats task failed for %s: %s", acc_id, res)
                    results[acc_id] = []
                else:
                    results[acc_id] = res

        return results

    async def search_player_by_username(
        self,
        username: str,
        client: httpx.AsyncClient | None = None,
        min_matches: int = 5,
    ) -> PlayerSearchResult:
        """
        Search for a Deadlock player by Steam personaname using Deadlock API.
        Resolves to their Steam32 / Statlocker account ID.
        """
        cleaned_name = username.strip().strip("'\"")
        if not cleaned_name:
            return PlayerSearchResult(
                search_query=username,
                success=False,
                message="Empty username provided.",
            )

        params: dict[str, Any] = {
            "search_query": cleaned_name,
            "limit": 10,
            "min_matches_played_last_30d": min_matches,
        }

        async def _do_query(c: httpx.AsyncClient, p: dict[str, Any]) -> list[dict[str, Any]]:
            resp = await c.get(
                settings.deadlock_steam_search_endpoint,
                params=p,
                headers=self._get_headers(),
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
            return []

        try:
            results: list[dict[str, Any]] = []
            if client:
                results = await _do_query(client, params)
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as c:
                    results = await _do_query(c, params)

            # If no matches found with min_matches > 0, retry once with min_matches=0
            if not results and min_matches > 0:
                retry_params = dict(params, min_matches_played_last_30d=0)
                if client:
                    results = await _do_query(client, retry_params)
                else:
                    async with httpx.AsyncClient(timeout=self.timeout) as c:
                        results = await _do_query(c, retry_params)

            if not results:
                return PlayerSearchResult(
                    search_query=username,
                    success=False,
                    message=f"No Deadlock player found matching username '{username}'.",
                )

            # Look for exact case-insensitive match first
            exact_matches = [
                p
                for p in results
                if str(p.get("personaname", "")).strip().lower() == cleaned_name.lower()
            ]
            if exact_matches:
                # Prefer the one with highest recent match volume
                chosen = max(exact_matches, key=lambda x: int(x.get("matches_played_last_30d") or 0))
            else:
                chosen = results[0]

            acc_id = int(chosen["account_id"])
            persona = str(chosen.get("personaname") or cleaned_name)
            profile_url = chosen.get("profileurl")
            statlocker_url = f"https://statlocker.gg/profile/{acc_id}"
            m30 = chosen.get("matches_played_last_30d")

            return PlayerSearchResult(
                search_query=username,
                account_id=acc_id,
                personaname=persona,
                profile_url=profile_url,
                statlocker_url=statlocker_url,
                matches_played_last_30d=m30,
                success=True,
                message=f"Resolved '{username}' to Statlocker ID {acc_id} ({persona}).",
            )
        except Exception as exc:
            logger.warning("Error searching player by username '%s': %s", username, exc)
            return PlayerSearchResult(
                search_query=username,
                success=False,
                message=f"Search failed due to network error: {exc}",
            )

    async def resolve_usernames_to_ids(
        self,
        usernames: Sequence[str],
    ) -> list[PlayerSearchResult]:
        """
        Concurrently resolve a list of player usernames to their Statlocker / Steam32 IDs.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            tasks = [self.search_player_by_username(name, client=client) for name in usernames]
            return await asyncio.gather(*tasks)
