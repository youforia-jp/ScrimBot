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

    @staticmethod
    def get_embed_total_chars(embed: any) -> int:
        """Calculate total characters in a Discord Embed according to Discord API limits."""
        total = len(getattr(embed, "title", None) or "") + len(getattr(embed, "description", None) or "")
        author = getattr(embed, "author", None)
        if author and getattr(author, "name", None):
            total += len(author.name)
        footer = getattr(embed, "footer", None)
        if footer and getattr(footer, "text", None):
            total += len(footer.text)
        for field in getattr(embed, "fields", []):
            total += len(getattr(field, "name", None) or "") + len(getattr(field, "value", None) or "")
        return total

    @staticmethod
    async def _send_embeds_safely(
        send_func: any,
        embeds: list[any],
        max_chars_per_msg: int = 4800,
    ) -> None:
        """
        Send a list of embeds in batches such that no single Discord message
        exceeds Discord's 6000-character combined embed limit or 10-embed limit.
        """
        current_batch: list[any] = []
        current_batch_chars = 0

        for emb in embeds:
            emb_chars = DeadlockScoutCog.get_embed_total_chars(emb)
            # If batching this embed would exceed safe message budget or 10 embeds, dispatch
            if current_batch and (current_batch_chars + emb_chars > max_chars_per_msg or len(current_batch) >= 10):
                await send_func(embeds=current_batch)
                current_batch = [emb]
                current_batch_chars = emb_chars
            else:
                current_batch.append(emb)
                current_batch_chars += emb_chars

        if current_batch:
            await send_func(embeds=current_batch)

    def build_report_embeds(self, report: ExecutiveScoutingReport) -> list[any]:
        """Convert ExecutiveScoutingReport into Discord Embeds with strict per-embed and per-message size limits."""
        if not HAS_DISCORD:
            raise RuntimeError("discord.py is not installed in the environment.")

        # Main Overview Embed
        embed = discord.Embed(
            title="🎯 Collegiate Deadlock Scouting Report",
            description=(
                f"**Team:** {report.team_name}\n"
                f"**Scouted at:** {report.created_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
                f"**Window:** {report.sample_window}"
            ),
            color=discord.Color.red() if any(o.is_one_trick for o in report.opponents) else discord.Color.blue(),
        )

        embeds: list[discord.Embed] = [embed]

        # Draft Room Link
        if report.draft_lobby and report.draft_lobby.success and report.draft_lobby.draft_url:
            embed.add_field(
                name="🎮 Statlocker Draft Room",
                value=f"[**Click to Enter Draft Lobby**]({report.draft_lobby.draft_url})",
                inline=False,
            )

        # Ranked Character Threats Section (All characters, individual pilot scores)
        ranked_chars = report.ranked_characters
        if not ranked_chars:
            embed.add_field(
                name="📊 Ranked Character Threat List",
                value="No opponent hero matches recorded.",
                inline=False,
            )
        else:
            lines = []
            for item in ranked_chars:
                rank_badge = "🥇" if item.rank == 1 else "🥈" if item.rank == 2 else "🥉" if item.rank == 3 else f"`#{item.rank}`"
                line = (
                    f"{rank_badge} **{item.hero_name}** (`{item.threat_score:.1f}` Thr) — "
                    f"**{item.primary_player_name}** ({item.win_rate*100:.0f}% WR, {item.matches_played}G | KDA: `{item.kda_display}`)"
                )
                if item.secondary_pilots:
                    alt_info = item.secondary_pilots[0]
                    if len(alt_info) > 80:
                        alt_info = alt_info[:77] + "..."
                    line += f"\n   ↳ *Alt:* {alt_info}"
                lines.append(line)

            # Dynamically group lines into fields strictly <= 800 characters (Discord limit: 1024)
            field_chunks: list[str] = []
            current_chunk: list[str] = []
            current_len = 0

            for l in lines:
                l_len = len(l)
                if current_chunk and (current_len + l_len + 1 > 800):
                    field_chunks.append("\n".join(current_chunk))
                    current_chunk = [l]
                    current_len = l_len
                else:
                    current_chunk.append(l)
                    current_len += l_len + 1

            if current_chunk:
                field_chunks.append("\n".join(current_chunk))

            # Add fields across embeds (max 3800 chars or 10 fields per embed, Discord limit is 6000)
            for idx, chunk_text in enumerate(field_chunks):
                field_title = (
                    "📊 Ranked Character Threat List (Individual Pilot Scores)"
                    if idx == 0
                    else f"📊 Ranked Characters (Cont. Part {idx + 1})"
                )
                target_embed = embeds[-1]
                field_chars = len(field_title) + len(chunk_text)

                if (self.get_embed_total_chars(target_embed) + field_chars > 3800) or len(target_embed.fields) >= 10:
                    new_embed = discord.Embed(
                        title=f"📊 Ranked Character Threat List (Cont. Part {len(embeds) + 1})",
                        color=embed.color,
                    )
                    embeds.append(new_embed)
                    target_embed = new_embed

                target_embed.add_field(
                    name=field_title,
                    value=chunk_text[:1024],
                    inline=False,
                )

        # Roster Breakdown Embed (Clean dedicated embed)
        roster_embed = discord.Embed(
            title="👥 Opponent Roster & Comfort Picks",
            color=discord.Color.dark_grey(),
        )

        for opp in report.opponents:
            comfort_str = "None recorded"
            if opp.comfort_heroes:
                comfort_str = "\n".join(
                    f"• **{h.hero_name}**: {h.win_rate*100:.0f}% WR ({h.matches_played}G) | KDA: `{h.kda_display}`"
                    for h in opp.comfort_heroes[:2]
                )

            hazard_note = ""
            if opp.is_one_trick and opp.one_trick_hero and opp.one_trick_pct:
                hazard_note = f"\n⚠️ **ONE-TRICK:** {opp.one_trick_hero} ({opp.one_trick_pct*100:.1f}% of games)"

            field_val = f"**PP:** {opp.pp_score:,}\n{comfort_str}{hazard_note}"
            roster_embed.add_field(
                name=f"{opp.display_name} ({opp.rank_name})",
                value=field_val[:1024],
                inline=True,
            )

        embeds.append(roster_embed)
        return embeds

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
            recent_matches: int = 200,
        ) -> None:
            """Scout a 6-player opponent roster via prefix command: !scout id1 id2 id3 id4 id5 id6 [create_draft] [recent_matches]"""
            inputs = [p1, p2, p3, p4, p5, p6]
            await ctx.send("🔍 *Scouting Deadlock opponents and calculating target bans...*")
            try:
                report = await run_scouting(
                    opponent_inputs=inputs,
                    team_name=settings.default_team_name,
                    create_draft=create_draft,
                    max_recent_matches=recent_matches,
                )
                embeds = self.build_report_embeds(report)
                await self._send_embeds_safely(ctx.send, embeds)
            except Exception as exc:
                await ctx.send(f"❌ **Scouting error:** {exc}")

        @app_commands.command(name="scout", description="Scout 6 Deadlock opponents and calculate ban priorities.")
        @app_commands.describe(
            opponents="6 comma- or space-separated Steam32 IDs or Statlocker URLs",
            create_draft="Whether to create a public Statlocker draft room",
            recent_matches="Max recent games per player (default: 200, 0 for all-time)",
        )
        async def slash_scout(
            self,
            interaction: discord.Interaction,
            opponents: str,
            create_draft: bool = False,
            recent_matches: int = 200,
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
                    max_recent_matches=recent_matches,
                )
                embeds = self.build_report_embeds(report)
                await self._send_embeds_safely(interaction.followup.send, embeds)
            except Exception as exc:
                await interaction.followup.send(f"❌ **Scouting error:** {exc}")


async def setup(bot: any) -> None:
    """Standard discord.py extension setup entrypoint."""
    if not HAS_DISCORD:
        logger.warning("discord.py is not installed. DeadlockScoutCog will not be loaded.")
        return
    await bot.add_cog(DeadlockScoutCog(bot))
