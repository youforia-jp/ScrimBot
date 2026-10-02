"""Interactive CLI utility for collegiate Deadlock scouting and draft recommendations."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Sequence

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt

from config import settings
from id_parser import parse_opponent_roster
from models import ExecutiveScoutingReport
from scout import run_scouting

# Reconfigure stdout/stderr to UTF-8 on Windows to prevent UnicodeEncodeError in legacy consoles
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

console = Console(legacy_windows=False)


def render_report(report: ExecutiveScoutingReport) -> None:
    """Render the full executive scouting report to terminal using rich formatting."""
    console.print()

    # 1. Header Banner
    statlocker_badge = (
        "[bold green][+ LIVE STATLOCKER][/bold green]"
        if report.statlocker_connected
        else "[bold yellow][- BASELINE PP: 5000 (Oracle)][/bold yellow]"
    )
    deadlock_badge = (
        "[bold green][+ DEADLOCK API ONLINE][/bold green]"
        if report.deadlock_connected
        else "[bold red][- DEADLOCK API OFFLINE][/bold red]"
    )

    header_text = Text()
    header_text.append("COLLEGIATE DEADLOCK COMPETITIVE SCOUTING REPORT\n", style="bold cyan")
    header_text.append(
        f"Team: {report.team_name}   |   Timestamp: {report.created_at.strftime('%Y-%m-%d %H:%M:%S')}   |   Window: {report.sample_window}\n",
        style="dim",
    )
    header_text.append(f"APIs: {statlocker_badge}   {deadlock_badge}")

    console.print(Panel(header_text, border_style="cyan", box=box.ROUNDED, expand=False))

    # 1.5 Resolved Usernames Table (if usernames were searched)
    if report.resolved_players and any(
        r.search_query != str(r.account_id) for r in report.resolved_players if r.account_id
    ):
        resolve_table = Table(
            title="[OPPONENT RESOLUTION] STATLOCKER PROFILES RESOLVED FROM USERNAMES",
            title_style="bold green",
            header_style="bold cyan",
            box=box.SIMPLE_HEAVY,
            expand=False,
        )
        resolve_table.add_column("Input Username", style="bold white")
        resolve_table.add_column("Matched Persona", style="bold yellow")
        resolve_table.add_column("Steam32 ID", style="bold cyan")
        resolve_table.add_column("Statlocker Profile", style="blue")
        resolve_table.add_column("Recent Games (30d)", style="green", justify="right")

        for r in report.resolved_players:
            if r.success and r.account_id:
                m30_str = f"{r.matches_played_last_30d}G" if r.matches_played_last_30d is not None else "-"
                resolve_table.add_row(
                    r.search_query,
                    r.personaname or "-",
                    str(r.account_id),
                    r.statlocker_url or f"https://statlocker.gg/profile/{r.account_id}",
                    m30_str,
                )
        console.print(resolve_table)
        console.print()

    # 2. All Ranked Characters (Un-accumulated Threat)
    ranked_table = Table(
        title="[ALL HEROES] RANKED CHARACTER THREAT LIST (INDIVIDUAL PILOT SCORES)",
        title_style="bold red",
        header_style="bold magenta",
        box=box.HEAVY_EDGE,
        expand=True,
    )
    ranked_table.add_column("Rank", style="bold yellow", width=10, justify="center")
    ranked_table.add_column("Character", style="bold white", width=14)
    ranked_table.add_column("Threat", style="bold cyan", width=10, justify="right")
    ranked_table.add_column("Primary Pilot", style="bold green", width=18)
    ranked_table.add_column("Record", style="white", width=16)
    ranked_table.add_column("Pilot KDA", style="bold yellow", width=22)
    ranked_table.add_column("Secondary Pilots (Un-accumulated)", style="dim white")

    characters_to_show = report.ranked_characters
    if not characters_to_show:
        ranked_table.add_row("-", "No Heroes Recorded", "0.0", "-", "-", "-", "Opponents have no recorded matches")
    else:
        for item in characters_to_show:
            if item.rank == 1:
                rank_label = "[bold red]#1 BAN[/bold red]"
            elif item.rank == 2:
                rank_label = "[bold yellow]#2 BAN[/bold yellow]"
            elif item.rank == 3:
                rank_label = "[bold green]#3 BAN[/bold green]"
            else:
                rank_label = f"#{item.rank}"

            secondary_str = "\n".join(item.secondary_pilots) if item.secondary_pilots else "-"
            record_str = f"{item.win_rate*100:.0f}% WR ({item.matches_played}G)"

            ranked_table.add_row(
                rank_label,
                f"[bold white on red] {item.hero_name} [/bold white on red]" if item.threat_score >= 30.0 else item.hero_name,
                f"[bold]{item.threat_score:.1f}[/bold]",
                item.primary_player_name,
                record_str,
                item.kda_display,
                secondary_str,
            )

    console.print(ranked_table)
    console.print()

    # 3. Opponent Breakdown Table
    opp_table = Table(
        title="[OPPONENT ROSTER] BREAKDOWN & COMFORT PICKS",
        title_style="bold blue",
        header_style="bold cyan",
        box=box.ROUNDED,
        expand=True,
    )
    opp_table.add_column("Player Name (Steam32)", style="bold white", width=22)
    opp_table.add_column("Skill Tier & PP", style="bold yellow", width=20)
    opp_table.add_column("Primary Comfort Pick", style="white", width=26)
    opp_table.add_column("Secondary Comfort Pick", style="dim white", width=26)
    opp_table.add_column("Hazard / One-Trick Alerts", style="bold red", width=28)

    for opp in report.opponents:
        # Player identifier
        name_display = f"{opp.display_name}\n[dim]ID: {opp.account_id}[/dim]"
        # Tier & PP
        tier_display = f"{opp.rank_name}\n[dim]{opp.pp_score:,} PP[/dim]"

        # Comfort picks
        comfort_1 = "-"
        if len(opp.comfort_heroes) > 0:
            h1 = opp.comfort_heroes[0]
            comfort_1 = f"[bold green]{h1.hero_name}[/bold green]\n{h1.win_rate*100:.0f}% WR ({h1.matches_played}G | {h1.threat_score:.1f} Thr)"

        comfort_2 = "-"
        if len(opp.comfort_heroes) > 1:
            h2 = opp.comfort_heroes[1]
            comfort_2 = f"[cyan]{h2.hero_name}[/cyan]\n{h2.win_rate*100:.0f}% WR ({h2.matches_played}G | {h2.threat_score:.1f} Thr)"

        # One-trick warning
        if opp.is_one_trick and opp.one_trick_hero and opp.one_trick_pct:
            hazard = (
                f"[bold white on red] [!] ONE-TRICK ALERT [/bold white on red]\n"
                f"[red]* {opp.one_trick_hero} ({opp.one_trick_pct*100:.1f}% of {opp.total_matches}G)[/red]"
            )
        else:
            hazard = f"[dim green]Flexible ({opp.total_matches} Total Games)[/dim green]"

        opp_table.add_row(name_display, tier_display, comfort_1, comfort_2, hazard)

    console.print(opp_table)
    console.print()

    # 4. Draft Room Link
    if report.draft_lobby:
        if report.draft_lobby.success and report.draft_lobby.draft_url:
            draft_text = Text()
            draft_text.append("[DRAFT ROOM] STATLOCKER LOBBY ACTIVE\n", style="bold green")
            draft_text.append(f"Room Link: {report.draft_lobby.draft_url}\n", style="bold underline white")
            draft_text.append("Share this URL with captains to initiate the competitive draft lobby.", style="dim")
            console.print(Panel(draft_text, border_style="green", box=box.DOUBLE))
        else:
            draft_text = Text()
            draft_text.append("Draft Room Note: ", style="bold yellow")
            draft_text.append(report.draft_lobby.message, style="white")
            console.print(Panel(draft_text, border_style="yellow", box=box.ROUNDED))
        console.print()

    # 5. Tactical Advisory
    advisory_items = []
    one_trick_opponents = [o for o in report.opponents if o.is_one_trick and o.one_trick_hero]
    if one_trick_opponents:
        for oto in one_trick_opponents:
            advisory_items.append(
                f"[bold red]CRITICAL:[/bold red] Opponent [bold]{oto.display_name}[/bold] is heavily reliant on "
                f"[bold red]{oto.one_trick_hero}[/bold red] ({oto.one_trick_pct*100:.1f}% of matches). "
                f"Denying this pick forces them into unfamiliar pool."
            )
    if report.target_bans:
        top_ban = report.target_bans[0]
        advisory_items.append(
            f"[bold cyan]PRIORITY BAN:[/bold cyan] Deny [bold white]{top_ban.hero_name}[/bold white] "
            f"(Cumulative Threat: {top_ban.total_threat_score:.1f}) in the first ban phase."
        )

    if advisory_items:
        advisory_panel = Panel(
            "\n".join(advisory_items),
            title="[bold magenta][TACTICAL ADVISORY] SCOUTING NOTES[/bold magenta]",
            border_style="magenta",
            box=box.ROUNDED,
        )
        console.print(advisory_panel)
        console.print()


def prompt_for_inputs() -> list[str]:
    """Interactively prompt user for 6 opponent profile URLs or Steam32 IDs."""
    console.print(
        Panel(
            "[bold cyan]Deadlock Collegiate Scrim Scouting Assistant[/bold cyan]\n"
            "Please provide 6 opponent Steam32 Account IDs or Profile URLs\n"
            "(e.g., https://statlocker.gg/profile/123456789 or steamcommunity profile URLs).",
            box=box.ROUNDED,
        )
    )

    inputs: list[str] = []
    for i in range(1, 7):
        while True:
            val = Prompt.ask(f"[bold green]Opponent #{i}[/bold green]").strip()
            if not val:
                console.print("[red]Input cannot be empty. Please enter an ID or URL.[/red]")
                continue
            inputs.append(val)
            break

    return inputs


def parse_args(args: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Competitive Scouting & Draft Tool for Collegiate Deadlock Esports."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Opponent Steam32 IDs or profile URLs (up to 6).",
    )
    parser.add_argument(
        "-o", "--opponents",
        nargs="+",
        help="List of opponent Steam32 IDs or URLs.",
    )
    parser.add_argument(
        "-f", "--file",
        help="Path to file containing opponent IDs/URLs (one per line).",
    )
    parser.add_argument(
        "-t", "--team",
        default=settings.default_team_name,
        help=f"Collegiate team name (default: '{settings.default_team_name}').",
    )
    parser.add_argument(
        "-d", "--create-draft",
        action="store_true",
        help="Create a public draft lobby on Statlocker.gg and output link.",
    )
    parser.add_argument(
        "-r", "--recent-matches",
        type=int,
        default=settings.max_recent_matches,
        help=f"Max recent matches per player to analyze (default: {settings.max_recent_matches}, 0 for all-time).",
    )
    parser.add_argument(
        "-u", "--usernames",
        nargs="+",
        help="Opponent Steam usernames to automatically resolve to Statlocker IDs and scout.",
    )
    parser.add_argument(
        "-m", "--mock",
        action="store_true",
        help="Run in mock mode using realistic collegiate scrim opponent data (offline demo).",
    )

    return parser.parse_args(args)


async def async_main(args: argparse.Namespace) -> int:
    # 1. Collect inputs
    raw_inputs: list[str] = []

    if args.mock:
        console.print("[dim italic]Running in offline mock mode with collegiate sample data...[/dim italic]")
        report = await run_scouting(
            opponent_inputs=[],
            team_name=args.team,
            create_draft=args.create_draft,
            mock_mode=True,
            max_recent_matches=args.recent_matches,
        )
        render_report(report)
        return 0

    if getattr(args, "usernames", None):
        raw_inputs = args.usernames
    elif args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                raw_inputs = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        except Exception as exc:
            console.print(f"[bold red]Error reading file {args.file}:[/bold red] {exc}")
            return 1
    elif args.opponents:
        raw_inputs = args.opponents
    elif args.inputs:
        raw_inputs = args.inputs

    # If no inputs provided, prompt interactively
    if not raw_inputs:
        raw_inputs = prompt_for_inputs()

    # Validate that we have at least 1 and warn if not 6
    if len(raw_inputs) != 6:
        console.print(
            f"[bold yellow]Notice:[/bold yellow] Received {len(raw_inputs)} opponent inputs. Standard Deadlock team roster is 6 players."
        )

    with console.status("[bold green]Resolving opponents and scouting target bans...[/bold green]", spinner="dots"):
        try:
            report = await run_scouting(
                opponent_inputs=raw_inputs,
                team_name=args.team,
                create_draft=args.create_draft,
                mock_mode=False,
                max_recent_matches=args.recent_matches,
            )
        except Exception as exc:
            console.print(f"[bold red]Scouting Pipeline Error:[/bold red] {exc}")
            return 1

    render_report(report)
    return 0


def main() -> None:
    args = parse_args()
    exit_code = asyncio.run(async_main(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
