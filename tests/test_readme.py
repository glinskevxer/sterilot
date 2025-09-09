"""The README is checked against the command line it describes.

Documentation goes stale silently. A command renamed in a hurry leaves the
README telling somebody to run something that no longer exists, and nobody
finds out until a new starter follows it. So the examples are parsed and the
commands in them are looked up.
"""

from __future__ import annotations

import re
from itertools import pairwise
from pathlib import Path

import click
import pytest

from sterilot.assets.lifecycle import Stage, may_move
from sterilot.cli.main import main

README = Path(__file__).resolve().parent.parent / "README.md"
INVOCATION = re.compile(r"^\s*sterilot\s+(?P<rest>[^\\\n]*)")


def blocks() -> list[str]:
    text = README.read_text(encoding="utf-8")
    return re.findall(r"```\n(.*?)```", text, flags=re.DOTALL)


def invocations() -> list[list[str]]:
    found: list[list[str]] = []
    for block in blocks():
        for line in block.splitlines():
            match = INVOCATION.match(line)
            if match is None:
                continue
            words = [word for word in match.group("rest").split() if not word.startswith("-")]
            if words:
                found.append(words)
    return found


def resolve(words: list[str]) -> click.Command | None:
    command: click.Command | None = main
    for word in words:
        if not isinstance(command, click.Group):
            return None
        command = command.commands.get(word)
        if command is None:
            return None
        if not isinstance(command, click.Group):
            return command
    return command


def test_the_readme_has_examples_in_it() -> None:
    assert len(invocations()) >= 5


@pytest.mark.parametrize("words", invocations(), ids=lambda words: " ".join(words))
def test_every_command_the_readme_shows_exists(words: list[str]) -> None:
    assert resolve(words) is not None, " ".join(words)


def test_the_readme_names_every_exit_status() -> None:
    text = README.read_text(encoding="utf-8")
    for status in (0, 2, 3, 4, 5, 6, 7):
        assert f"| {status} |" in text


def test_a_command_that_does_not_exist_would_be_caught() -> None:
    assert resolve(["catalog", "invent"]) is None
    assert resolve(["nonsense"]) is None


def test_the_readme_names_the_environment_variables() -> None:
    text = README.read_text(encoding="utf-8")
    assert "STERILOT_DB" in text
    assert "STERILOT_BADGE" in text


def loop_stages() -> list[str]:
    block = next(item for item in blocks() if "soiled" in item)
    return [word.strip() for word in block.replace("\n", " ").split("->") if word.strip()]


def test_the_readme_describes_the_loop_in_the_right_order() -> None:
    assert loop_stages() == [
        "soiled",
        "decontamination",
        "clean",
        "assembled",
        "sterilizing",
        "cooling",
        "sterile",
        "issued",
        "in use",
        "soiled",
    ]


def test_every_stage_the_readme_names_is_a_real_stage() -> None:
    for word in loop_stages():
        assert Stage.named(word) in Stage


def test_the_loop_the_readme_draws_is_a_legal_run_of_moves() -> None:
    stages = [Stage.named(word) for word in loop_stages()]
    for current, target in pairwise(stages):
        assert may_move(current, target), f"{current} to {target}"
