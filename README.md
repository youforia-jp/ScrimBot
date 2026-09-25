# Deadlock Collegiate Competitive Scouting & Draft Recommendation Tool

A production-grade, modular Python scouting utility and draft-recommendation engine engineered for collegiate Deadlock esports teams (e.g., Texas A&M White).

The tool ingests six opponent Steam32 account IDs or profile URLs, concurrently queries live player records via **Deadlock API** (`api.deadlock-api.com`) and skill ratings via **Statlocker** (`statlocker.gg`), computes mathematical ban-threat priorities, flags one-trick hazards, creates competitive Statlocker draft lobbies, and outputs an executive scouting report in rich terminal tables or Discord embeds.

---

## Key Features

1. **Flexible ID Parsing**:
   - Accepts raw Steam32 IDs (`105829141`).
   - Parses Statlocker URLs (`https://statlocker.gg/profile/105829141`).
   - Converts Steam64 profile URLs (`https://steamcommunity.com/profiles/76561198083722517`) using 64-to-32 bit conversion: $\text{Steam32} = \text{Steam64} - 76561197960265728$.
   - Handles SteamID3 strings (`[U:1:105829141]`) and third-party trackers (Tracklock, DeadlockTracker).

2. **Hybrid Asynchronous API Architecture**:
   - **Deadlock API** (`api.deadlock-api.com`): Asynchronously queries hero performance, matches played, and win rates for all 6 opponents concurrently using `httpx`.
   - **Statlocker** (`statlocker.gg`): Ingests `ppScore` and `estimatedRankNumber` via batch profile endpoint (`POST /api/public/profiles`).
   - **Graceful Fallbacks**: If Statlocker API key is missing or encounters HTTP 401/429/500, defaults safely to baseline PP score (`5000` / Oracle) without crashing.
   - Built-in static hero directory of 50+ Deadlock heroes with dynamic live asset refresh.

3. **Mathematical Target-Ban Scoring Engine**:
   - Ban Threat Score per hero per opponent:
     $$\text{Threat Score} = \sqrt{\text{Matches Played}} \times (\text{Win Rate} - 0.45) \times \left(1 + \frac{\text{ppScore}}{10000}\right) \times 10$$
   - **Minimum Filter**: Heroes with $< 5$ recorded games are filtered out.
   - **Cumulative Team Ban Priority**: Aggregates threat scores across all 6 opponent players to rank the Top 3 target bans.
   - **One-Trick Hazard Warning**: Flags any opponent whose most-played hero constitutes $\ge 55\%$ of their total recorded games.

4. **Statlocker Draft Lobby Generation**:
   - Generates a competitive public draft room on `statlocker.gg` with custom team names, competitive presets, and hybrid timers (`POST /api/public-draft/draft`).

5. **Dual Presentation Layer**:
   - **Terminal CLI**: Rich tables, status indicators, and tactical scouting advisories.
   - **Discord Cog (`discord_cog.py`)**: Ready-to-plug extension for team Discord scrim bots.

---

## Project Structure

```
ScrimBot/
├── .env.example            # Environment configuration template
├── .gitignore              # Git ignore rules
├── requirements.txt        # Production & testing dependencies
├── pytest.ini              # Pytest configuration
├── config.py               # Environment & threshold settings
├── id_parser.py            # Steam32 / Steam64 / URL extraction utility
├── models.py               # Pydantic data schemas & validation models
├── api_client.py           # Async clients for Statlocker & Deadlock API
├── analyzer.py             # Pure math scoring, one-trick detection, & rank conversions
├── mock_data.py            # Realistic collegiate scrim mock dataset
├── scout.py                # Pipeline orchestrator coordinating APIs & scoring
├── cli.py                  # Interactive CLI with Rich terminal panels
├── discord_cog.py          # Discord bot cog with slash & prefix commands
├── sample_opponents.txt    # Ready-to-run sample roster input file
└── tests/
    ├── test_id_parser.py   # Unit tests for ID extraction & arithmetic
    ├── test_analyzer.py    # Unit tests for threat math, filters, & one-tricks
    ├── test_api_client.py  # Unit tests for API clients & fallback resilience
    └── test_cli.py         # End-to-end tests for CLI & mock execution
```

---

## Setup & Installation

### 1. Requirements
- Python 3.11+ (Tested on Python 3.12)
- Virtual environment (`.venv`)

### 2. Environment Setup
```powershell
# Clone or navigate to the repository
cd ScrimBot

# Create and activate Python virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration (`.env`)
Copy `.env.example` to `.env`:
```powershell
copy .env.example .env
```
Edit `.env` to configure your settings:
```env
# Optional: Statlocker.gg API Key (falls back to 5000 PP / Oracle baseline if empty)
STATLOCKER_API_KEY=your_statlocker_key_here

# Collegiate Team Name
TEAM_NAME=Texas A&M White

# Request timeout in seconds
HTTP_TIMEOUT=10.0
```

---

## Usage Guide

### 1. Interactive Mode
Run without arguments to be prompted for 6 opponent URLs or Steam32 IDs:
```powershell
python cli.py
```

### 2. Command-Line Arguments
Pass 6 IDs or URLs directly:
```powershell
python cli.py 105829141 89410294 120489110 145920391 77489201 99381023
```
Or with Statlocker URLs:
```powershell
python cli.py https://statlocker.gg/profile/105829141 https://statlocker.gg/profile/89410294 ...
```

### 3. Roster File Input
Load from a text file (one URL or ID per line):
```powershell
python cli.py -f sample_opponents.txt
```

### 4. Create Statlocker Draft Lobby
Add `--create-draft` (`-d`) to generate a public draft room link:
```powershell
python cli.py -f sample_opponents.txt --create-draft
```

### 5. Offline Mock Demonstration Mode
Run with `--mock` (`-m`) to view realistic collegiate scouting data (including one-trick hazard detection and draft room link) without requiring live network calls or API keys:
```powershell
python cli.py --mock --create-draft
```

---

## Discord Bot Integration

To integrate the tool into an existing `discord.py` bot:

```python
import discord
from discord.ext import commands
from discord_cog import DeadlockScoutCog

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.add_cog(DeadlockScoutCog(bot))
    print(f"Logged in as {bot.user}")

bot.run("YOUR_DISCORD_BOT_TOKEN")
```

### Discord Commands:
- Prefix command: `!scout <id1> <id2> <id3> <id4> <id5> <id6> [create_draft=True]`
- Slash command: `/scout opponents: <ids or urls> create_draft: True`

---

## Running Automated Tests

Run the full pytest suite inside `.venv`:
```powershell
pytest -v tests/
```

Test coverage includes:
- Steam32 parsing & Steam64 arithmetic.
- Ban threat calculation against hand-verified formulas.
- Minimum 5-game filter & negative score handling.
- One-trick detection threshold ($\ge 55\%$) and flexible roster validation.
- Deadlock rank name conversions (including subtiers).
- Statlocker missing-key fallback and HTTP 401/429/500 resilience.
- End-to-end CLI execution and report rendering.
