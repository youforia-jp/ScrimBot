"""Standalone entrypoint for running the Deadlock ScrimBot on Discord.

Usage:
    1. Set DISCORD_BOT_TOKEN in .env
    2. Run: python bot.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import discord
from discord.ext import commands

from config import settings
from discord_cog import DeadlockScoutCog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ScrimBotDiscord")


class DeadlockScoutBot(commands.Bot):
    """Discord Bot configured with Deadlock scouting capabilities."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        # Only request message_content if explicitly enabled via environment
        self.message_content_enabled = os.getenv("ENABLE_MESSAGE_CONTENT", "false").lower() in ("true", "1", "yes")
        if self.message_content_enabled:
            intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=commands.DefaultHelpCommand(),
        )

    async def setup_hook(self) -> None:
        """Register cogs and schedule slash command sync."""
        await self.add_cog(DeadlockScoutCog(self))
        logger.info("Loaded DeadlockScoutCog.")
        # Sync in background task so gateway connection connects immediately
        asyncio.create_task(self._sync_tree())

    async def _sync_tree(self) -> None:
        try:
            synced = await self.tree.sync()
            logger.info("Synced %d slash command(s) with Discord.", len(synced))
        except Exception as exc:
            logger.warning("Slash command sync notice: %s", exc)

    async def on_ready(self) -> None:
        if self.user:
            logger.info("Logged in as %s (ID: %s)", self.user.name, self.user.id)
            logger.info("Active in %d guild(s).", len(self.guilds))
            print("\n" + "=" * 60, flush=True)
            print(f" Deadlock ScrimBot is ONLINE as @{self.user.name}", flush=True)
            print(f" Connected to {len(self.guilds)} Discord server(s)", flush=True)
            print(" Commands available in your server:", flush=True)
            print("   - Slash Command:  /scout opponents: <ids or urls>", flush=True)
            if self.message_content_enabled:
                print("   - Prefix Command: !scout <p1> <p2> <p3> <p4> <p5> <p6>", flush=True)
            else:
                print("   - Tip: Slash command (/scout) is active immediately!", flush=True)
                print("     To also use '!scout', enable 'Message Content Intent' in", flush=True)
                print("     Discord Developer Portal and add ENABLE_MESSAGE_CONTENT=true to .env.", flush=True)
            print("=" * 60 + "\n", flush=True)


def main() -> None:
    token = settings.discord_bot_token
    if not token:
        print("\n[ERROR] DISCORD_BOT_TOKEN is not set.")
        print("To run the bot on Discord:")
        print("  1. Create a Bot at https://discord.com/developers/applications")
        print("  2. Copy the Bot Token from the 'Bot' tab.")
        print("  3. Add it to your .env file:")
        print("         DISCORD_BOT_TOKEN=your_token_here")
        print("  4. Re-run: python bot.py\n")
        sys.exit(1)

    bot = DeadlockScoutBot()
    try:
        bot.run(token)
    except discord.errors.PrivilegedIntentsRequired:
        print("\n[ERROR] Privileged Message Content Intent is not enabled in Discord Developer Portal.")
        print("To fix:")
        print("  1. Visit https://discord.com/developers/applications")
        print("  2. Select your application -> 'Bot' tab.")
        print("  3. Scroll down and enable 'Message Content Intent'.\n")
        sys.exit(1)
    except discord.errors.LoginFailure:
        print("\n[ERROR] Failed to log in: The provided DISCORD_BOT_TOKEN is invalid.")
        sys.exit(1)


if __name__ == "__main__":
    main()
