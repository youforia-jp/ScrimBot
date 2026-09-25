"""End-to-end unit tests for CLI argument parsing and mock report rendering."""

from unittest.mock import patch
import pytest

from cli import async_main, parse_args
from models import ExecutiveScoutingReport
from scout import run_scouting


def test_cli_parse_args_mock_flag() -> None:
    args = parse_args(["--mock", "--create-draft", "--team", "Texas A&M White"])
    assert args.mock is True
    assert args.create_draft is True
    assert args.team == "Texas A&M White"


def test_cli_parse_args_positional() -> None:
    args = parse_args(["105829141", "89410294", "120489110"])
    assert len(args.inputs) == 3
    assert args.inputs[0] == "105829141"


@pytest.mark.asyncio
async def test_cli_mock_execution() -> None:
    args = parse_args(["--mock", "--create-draft"])
    exit_code = await async_main(args)
    assert exit_code == 0


@pytest.mark.asyncio
async def test_scout_orchestrator_mock_mode() -> None:
    report: ExecutiveScoutingReport = await run_scouting(
        opponent_inputs=[],
        team_name="Texas A&M White",
        create_draft=True,
        mock_mode=True,
    )
    assert report.team_name == "Texas A&M White"
    assert len(report.opponents) == 6
    assert len(report.target_bans) == 3
    assert report.draft_lobby is not None
    assert report.draft_lobby.success is True
    # Ensure one-trick detection identified Seven on AggieHunter
    seven_ot = next((o for o in report.opponents if o.personaname == "AggieHunter"), None)
    assert seven_ot is not None
    assert seven_ot.is_one_trick is True
    assert seven_ot.one_trick_hero == "Seven"
