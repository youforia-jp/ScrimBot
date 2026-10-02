"""Steam32 and profile URL extraction utility."""

from __future__ import annotations

import re
from typing import Sequence

STEAM64_BASE = 76561197960265728
MAX_STEAM32 = (1 << 32) - 1

# Precompiled regex patterns for common profile URL structures
STATLOCKER_REGEX = re.compile(r"statlocker\.gg/profile/(\d+)", re.IGNORECASE)
STEAM_PROFILES_REGEX = re.compile(r"steamcommunity\.com/profiles/(\d+)", re.IGNORECASE)
STEAM_ID3_REGEX = re.compile(r"\[?U:1:(\d+)\]?", re.IGNORECASE)
TRACKER_REGEX = re.compile(r"(?:tracklock\.gg|deadlocktracker\.gg)/players?/(\d+)", re.IGNORECASE)
GENERIC_DIGITS_REGEX = re.compile(r"(\d+)")


def steam64_to_steam32(steam64: int) -> int:
    """Convert a 64-bit Steam ID to a 32-bit Account ID."""
    steam32 = steam64 - STEAM64_BASE
    if not (1 <= steam32 <= MAX_STEAM32):
        raise ValueError(f"Resulting Steam32 ID {steam32} from Steam64 {steam64} is out of bounds.")
    return steam32


def parse_single_id(input_str: str) -> int:
    """
    Extract a Steam32 account ID from a raw string, URL, or Steam identifier.

    Supported formats:
    - Raw Steam32 ID: "123456789"
    - Raw Steam64 ID: "76561198083722517"
    - Statlocker Profile URL: "https://statlocker.gg/profile/123456789"
    - Steam Community Profile URL: "https://steamcommunity.com/profiles/76561198083722517"
    - SteamID3 format: "[U:1:123456789]" or "U:1:123456789"
    - Tracklock / DeadlockTracker URLs: "https://tracklock.gg/players/123456789"

    Raises:
        ValueError: If no valid Steam32 ID can be extracted.
    """
    cleaned = input_str.strip().strip("'\"")
    if not cleaned:
        raise ValueError("Empty input string provided.")

    # 1. Statlocker URL pattern
    match = STATLOCKER_REGEX.search(cleaned)
    if match:
        return _validate_steam32(int(match.group(1)))

    # 2. Steam Community Profiles URL pattern (Steam64)
    match = STEAM_PROFILES_REGEX.search(cleaned)
    if match:
        steam64 = int(match.group(1))
        return steam64_to_steam32(steam64)

    # 3. SteamID3 pattern
    match = STEAM_ID3_REGEX.search(cleaned)
    if match:
        return _validate_steam32(int(match.group(1)))

    # 4. Tracklock / DeadlockTracker pattern
    match = TRACKER_REGEX.search(cleaned)
    if match:
        return _validate_steam32(int(match.group(1)))

    # 5. Raw number or trailing path number
    # If the input has digits, let's extract the longest continuous digit sequence
    digits = GENERIC_DIGITS_REGEX.findall(cleaned)
    if digits:
        # Choose the most plausible ID (often the last sequence in URLs or the only sequence)
        val = int(digits[-1])
        if val > STEAM64_BASE:
            return steam64_to_steam32(val)
        return _validate_steam32(val)

    raise ValueError(f"Could not parse a valid Steam32 Account ID from input: '{input_str}'")


def _validate_steam32(val: int) -> int:
    """Validate that val falls into the positive 32-bit integer range."""
    if not (1 <= val <= MAX_STEAM32):
        raise ValueError(f"Value {val} is not a valid Steam32 Account ID.")
    return val


def parse_opponent_roster(inputs: Sequence[str]) -> list[int]:
    """
    Parse a collection of opponent links or IDs into unique Steam32 account IDs.

    Args:
        inputs: List or sequence of input strings.

    Returns:
        List of parsed integer Steam32 IDs.

    Raises:
        ValueError: If any input fails to parse.
    """
    parsed_ids: list[int] = []
    for idx, item in enumerate(inputs, start=1):
        item_str = item.strip()
        if not item_str:
            continue
        try:
            account_id = parse_single_id(item_str)
            parsed_ids.append(account_id)
        except ValueError as exc:
            raise ValueError(f"Player #{idx} ('{item_str}'): {exc}") from exc

    return parsed_ids


def is_direct_id_or_url(input_str: str) -> bool:
    """
    Check if input_str is an explicit Steam ID or supported profile URL
    (as opposed to a raw player username).
    """
    cleaned = input_str.strip().strip("'\"")
    if not cleaned:
        return False
    if STATLOCKER_REGEX.search(cleaned):
        return True
    if STEAM_PROFILES_REGEX.search(cleaned):
        return True
    if STEAM_ID3_REGEX.search(cleaned):
        return True
    if TRACKER_REGEX.search(cleaned):
        return True
    if cleaned.isdigit() and len(cleaned) >= 6:
        return True
    return False
