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


def test_cli_parse_args_less_than_and_more_than_six() -> None:
    # 2 inputs (< 6)
    args_less = parse_args(["105829141", "89410294"])
    assert len(args_less.inputs) == 2

    # 8 inputs (> 6)
    eight_inputs = [f"10582914{i}" for i in range(8)]
    args_more = parse_args(eight_inputs)
    assert len(args_more.inputs) == 8

    # Usernames flag with 1 username (< 6)
    args_u_less = parse_args(["-u", "GreenGobbler"])
    assert len(args_u_less.usernames) == 1

    # Usernames flag with 9 usernames (> 6)
    nine_names = [f"Player_{i}" for i in range(9)]
    args_u_more = parse_args(["-u"] + nine_names)
    assert len(args_u_more.usernames) == 9


@pytest.mark.asyncio
async def test_cli_execution_with_variable_counts() -> None:
    with patch("cli.run_scouting") as mock_run:
        mock_report = ExecutiveScoutingReport(
            team_name="Texas A&M",
            opponents=[],
            ranked_characters=[],
            target_bans=[],
        )
        mock_run.return_value = mock_report

        # 3 inputs (< 6)
        args_3 = parse_args(["105829141", "89410294", "120489110"])
        exit_code_3 = await async_main(args_3)
        assert exit_code_3 == 0
        assert mock_run.call_args.kwargs["opponent_inputs"] == ["105829141", "89410294", "120489110"]

        # 7 inputs (> 6)
        inputs_7 = ["105829141", "89410294", "120489110", "138808374", "165672503", "122758709", "194996755"]
        args_7 = parse_args(inputs_7)
        exit_code_7 = await async_main(args_7)
        assert exit_code_7 == 0
        assert mock_run.call_args.kwargs["opponent_inputs"] == inputs_7

