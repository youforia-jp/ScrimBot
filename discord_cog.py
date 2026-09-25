"""Optional Discord Bot Cog for collegiate Deadlock scouting and draft recommendations.

To use:
    from discord_cog import DeadlockScoutCog
    await bot.add_cog(DeadlockScoutCog(bot))
"""

from __future__ import annotations

import logging
from typing import Optional

try:
    import discord
    from discord import app_commands
    from discord.ext import commands
    HAS_DISCORD = True
except ImportError:
    HAS_DISCORD = False
    # Minimal stubs so the file can be inspected without discord.py installed
    class commands:  # type: ignore
        Cog = object

from config import settings
from scout import run_scouting
from models import ExecutiveScoutingReport

logger = logging.getLogger(__name__)


class DeadlockScoutCog(commands.Cog):
    """Discord Cog for Deadlock scrim scouting and ban recommendations."""

    def __init__(self, bot: any) -> None:
        self.bot = bot

    def build_report_embeds(self, report: ExecutiveScoutingReport) -> list[any]:
        """Convert ExecutiveScoutingReport into Discord Embeds."""
        if not HAS_DISCORD:
            raise RuntimeError("discord.py is not installed in the environment.")

        # Main Embed: Target Bans
        embed = discord.Embed(
            title="🎯 Collegiate Deadlock Scouting Report",
            description=f"**Team:** {report.team_name}\n**Scouted at:** {report.created_at.strftime('%Y-%m-%d %H:%M UTC')}",
            color=discord.Color.red() if any(o.is_one_trick for o in report.opponents) else discord.Color.blue(),
        )

        # Target Bans Section
        ban_emojis = ["🥇", "🥈", "🥉"]
        ban_lines = []
        for idx, ban in enumerate(report.target_bans):
            emoji = ban_emojis[idx] if idx < len(ban_emojis) else f"#{idx+1}"
            threats_summary = ", ".join(ban.primary_threats[:2]) if ban.primary_threats else "Broad comfort"
            ban_lines.append(
                f"{emoji} **{ban.hero_name}** — Threat: `{ban.total_threat_score:.1f}`\n"
                f"   *Primary Hazards:* {threats_summary}"
            )
        embed.add_field(
            name="🚫 Priority Target Bans",
            value="\n".join(ban_lines) if ban_lines else "No high-threat heroes detected.",
            inline=False,
        )

        # Draft Room Link
        if report.draft_lobby and report.draft_lobby.success and report.draft_lobby.draft_url:
            embed.add_field(
                name="🎮 Statlocker Draft Room",
                value=f"[**Click to Enter Draft Lobby**]({report.draft_lobby.draft_url})",
                inline=False,
            )

        # Roster Breakdown Embed
        roster_embed = discord.Embed(
            title="👥 Opponent Roster & Comfort Picks",
            color=discord.Color.dark_grey(),
        )

        for opp in report.opponents:
            comfort_str = "None recorded"
            if opp.comfort_heroes:
                comfort_str = " | ".join(
                    f"**{h.hero_name}** ({h.win_rate*100:.0f}% WR, {h.matches_played}G)"
                    for h in opp.comfort_heroes
                )

            hazard_note = ""
            if opp.is_one_trick and opp.one_trick_hero and opp.one_trick_pct:
                hazard_note = f"\n⚠️ **ONE-TRICK:** {opp.one_trick_hero} ({opp.one_trick_pct*100:.1f}% of games)"

            roster_embed.add_field(
                name=f"{opp.display_name} ({opp.rank_name})",
                value=f"**PP:** {opp.pp_score:,}\n**Comforts:** {comfort_str}{hazard_note}",
                inline=True,
            )

        return [embed, roster_embed]

    if HAS_DISCORD:
        @commands.command(name="scout")
        async def prefix_scout(
            self,
            ctx: commands.Context,
            p1: str,
            p2: str,
            p3: str,
            p4: str,
            p5: str,
            p6: str,
            create_draft: bool = False,
        ) -> None:
            """Scout a 6-player opponent roster via prefix command: !scout id1 id2 id3 id4 id5 id6 [create_draft]"""
            inputs = [p1, p2, p3, p4, p5, p6]
            await ctx.send("🔍 *Scouting Deadlock opponents and calculating target bans...*")
            try:
                report = await run_scouting(
                    opponent_inputs=inputs,
                    team_name=settings.default_team_name,
                    create_draft=create_draft,
                )
                embeds = self.build_report_embeds(report)
                for emb in embeds:
                    await ctx.send(embed=emb)
            except Exception as exc:
                await ctx.send(f"❌ **Scouting error:** {exc}")

        @app_commands.command(name="scout", description="Scout 6 Deadlock opponents and calculate ban priorities.")
        @app_commands.describe(
            opponents="6 comma- or space-separated Steam32 IDs or Statlocker URLs",
            create_draft="Whether to create a public Statlocker draft room",
        )
        async def slash_scout(
            self,
            interaction: discord.Interaction,
            opponents: str,
            create_draft: bool = False,
        ) -> None:
            """Slash command for Deadlock scouting."""
            raw_inputs = [s.strip() for s in opponents.replace(",", " ").split() if s.strip()]
            if len(raw_inputs) != 6:
                await interaction.response.send_message(
                    f"⚠️ Please provide exactly 6 opponent IDs or URLs (received {len(raw_inputs)}).",
                    ephemeral=True,
                )
                return

            await interaction.response.defer()
            try:
                report = await run_scouting(
                    opponent_inputs=raw_inputs,
                    team_name=settings.default_team_name,
                    create_draft=create_draft,
                )
                embeds = self.build_report_embeds(report)
                await interaction.followup.send(embeds=embeds)
            except Exception as exc:
                await interaction.followup.send(f"❌ **Scouting error:** {exc}")


async def setup(bot: any) -> None:
    """Standard discord.py extension setup entrypoint."""
    if not HAS_DISCORD:
        logger.warning("discord.py is not installed. DeadlockScoutCog will not be loaded.")
        return
    await bot.add_cog(DeadlockScoutCog(bot))
