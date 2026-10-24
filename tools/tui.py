#!/usr/bin/env python3
"""TUI for rendering and building systemd container images at home."""

from __future__ import annotations

import curses
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.common import (
    build_image,
    default_target_image,
    distros,
    render,
    run_test,
    supported_tags,
)

YES = ("yes", "no")


def _show_error(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)


def _select_option(
    stdscr: curses.window,
    title: str,
    options: Sequence[str],
) -> str:
    """Select one option from a curses list."""
    if not options:
        raise RuntimeError("no options to select")

    selected_index = 0
    while True:
        stdscr.clear()
        stdscr.addstr(0, 0, title, curses.A_BOLD)
        stdscr.addstr(1, 0, "Use arrow up/down, Enter to choose, q to cancel.")
        for index, option in enumerate(options):
            prefix = "*" if index == selected_index else " "
            stdscr.addstr(2 + index, 0, f"{prefix} {option}")
        stdscr.refresh()
        key = stdscr.getch()
        if key in (ord("q"), ord("Q"), 27):
            raise KeyboardInterrupt
        if key == curses.KEY_UP:
            selected_index = max(0, selected_index - 1)
        elif key == curses.KEY_DOWN:
            selected_index = min(len(options) - 1, selected_index + 1)
        elif key in (curses.KEY_ENTER, 10, 13):
            return options[selected_index]
        elif key in (ord("h"), ord("H"), curses.KEY_LEFT):
            selected_index = max(0, selected_index - 1)
        elif key in (ord("l"), ord("L"), curses.KEY_RIGHT):
            selected_index = min(len(options) - 1, selected_index + 1)


def run() -> int:
    """Run a simple interactive curses menu."""
    try:
        config: dict[str, object] = curses.wrapper(_builder)
    except ModuleNotFoundError:
        _show_error("curses is not available in this environment")
        return 2
    except KeyboardInterrupt:
        return 0

    if config is None:
        return 0

    distro = str(config["distro"])
    tag = str(config["tag"])
    target_image = str(config["target_image"])
    runtime = str(config["runtime"])
    skip_build = bool(config["skip_build"])
    test = bool(config["test"])

    try:
        dockerfile, image_ref, tags = render(distro, tag, target_image)
    except Exception as exc:
        _show_error(f"failed to render image: {exc}")
        return 1

    tag_line = ",".join(tags)
    print(f"Rendered {distro}:{tag} with tags {tag_line}")
    print(f"Image reference: {image_ref}")
    print(f"Dockerfile: {dockerfile}")

    if skip_build:
        print("Skipped build.")
        return 0

    try:
        build_image(dockerfile, image_ref, runtime=runtime)
    except Exception as exc:
        _show_error(f"build failed: {exc}")
        return 1

    if test:
        try:
            run_test(image_ref)
        except Exception as exc:
            _show_error(f"test failed: {exc}")
            return 1

    print(f"Built {image_ref}")
    return 0


def _builder(stdscr: curses.window) -> dict[str, object]:
    """Prompt the user with curses menus and return the selection."""
    all_distros = list(distros())
    assert all_distros

    distro = _select_option(stdscr, "Distro", all_distros)
    tag_list = list(supported_tags(distro))
    if not tag_list:
        raise RuntimeError(f"no tags supported for distro '{distro}'")
    tag = _select_option(stdscr, "Upstream tag", tag_list)

    target_choices = [
        "default",
        f"quanvm0501alt1/{distro}-systemd",
    ]
    target_image_choice = _select_option(
        stdscr,
        "Target image",
        target_choices,
    )
    target_image = (
        default_target_image(distro)
        if target_image_choice == "default"
        else target_image_choice
    )

    runtime = _select_option(
        stdscr,
        "Runtime",
        ("auto", "docker", "podman"),
    )

    skip_build = _select_option(stdscr, "Skip build", YES) == "yes"
    if skip_build:
        test = False
    else:
        test = _select_option(stdscr, "Run integration test", YES) == "yes"

    return {
        "distro": distro,
        "tag": tag,
        "target_image": target_image,
        "runtime": runtime,
        "skip_build": skip_build,
        "test": test,
    }


if __name__ == "__main__":
    sys.exit(run())
