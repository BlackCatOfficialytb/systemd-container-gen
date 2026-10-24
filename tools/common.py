#!/usr/bin/env python3
"""Shared rendering/build helpers for the local systemd-container tool."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIMES = ("auto", "docker", "podman")
DISTRO_REPOS = {
    "ubuntu": "library/ubuntu",
    "debian": "library/debian",
    "fedora": "library/fedora",
    "opensuse": "opensuse/leap",
}
TEST_SCRIPT = REPO_ROOT / "tests" / "test_container.sh"


def _load_renderer():
    """Return the digest renderer's tag map and base-image helper."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from scripts.check_and_render import TARGET_TAGS, base_image_for

    return TARGET_TAGS, base_image_for


def supported_tags(distro: str) -> Tuple[str, ...]:
    """Return the upstream tags supported by a rendered template."""
    tag_map, _ = _load_renderer()
    return tuple(tag_map[distro])


def distros() -> Tuple[str, ...]:
    """Return the distributions supported by local rendering."""
    return tuple(DISTRO_REPOS)


def default_target_image(distro: str) -> str:
    """Return a neutral local image name used to render the banner."""
    return f"local/{distro}-systemd"


def render(
    distro: str,
    upstream_tag: str,
    target_image: str | None = None,
) -> Tuple[Path, str, Tuple[str, ...]]:
    """Render one distro Dockerfile and return the Dockerfile, image ref, and tags."""
    if target_image is None:
        target_image = default_target_image(distro)
    target_image = target_image.strip()
    if not target_image:
        raise ValueError("target_image cannot be empty")

    tag_map, base_image_for = _load_renderer()
    if distro not in DISTRO_REPOS:
        supported_distro = ", ".join(sorted(DISTRO_REPOS))
        raise ValueError(f"unsupported distro '{distro}' ({supported_distro})")
    if distro not in tag_map:
        raise ValueError(f"renderer does not publish tags for '{distro}'")
    if upstream_tag not in tag_map[distro]:
        supported_tags_text = ", ".join(sorted(tag_map[distro]))
        raise ValueError(
            f"unsupported upstream tag '{upstream_tag}' for '{distro}' "
            f"({supported_tags_text})"
        )

    tags = tuple(tag_map[distro][upstream_tag])
    base_image = base_image_for(DISTRO_REPOS[distro])
    from scripts.check_and_render import render_dockerfile

    dockerfile = render_dockerfile(
        distro,
        upstream_tag,
        base_image,
        target_image,
        tags,
    )
    image_ref = f"{target_image}:{upstream_tag}"
    return dockerfile, image_ref, tags


def _active_runtime(runtime: str) -> str:
    """Resolve 'auto' to the first locally available builder."""
    if runtime == "docker":
        if shutil.which("docker") is None:
            raise RuntimeError("docker is not installed")
        return runtime
    if runtime == "podman":
        if shutil.which("podman") is None:
            raise RuntimeError("podman is not installed")
        return runtime
    if runtime == "auto":
        if shutil.which("docker") is not None:
            return "docker"
        if shutil.which("podman") is not None:
            return "podman"
        raise RuntimeError("neither docker nor podman is installed")
    raise ValueError(f"unsupported runtime '{runtime}'")


def build_image(
    dockerfile: Path,
    image_ref: str,
    runtime: str = "auto",
    pull: bool = True,
) -> None:
    """Build a locally rendered Dockerfile with Docker or Podman."""
    active_runtime = _active_runtime(runtime)
    base_command = [active_runtime, "build"]
    if pull:
        base_command.append("--pull")
    if active_runtime == "docker":
        # The newer Docker engine exposes a BuildKit-aware buildx variant. Use it
        # when available, otherwise fall back to the classic builder.
        if shutil.which("docker-buildx") is not None or subprocess.run(
            ["docker", "buildx", "version"], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0:
            base_command = ["docker", "buildx", "build"]
            if pull:
                base_command.append("--pull")
            base_command.append("--load")
    base_command.extend(
        [
            "--file",
            str(dockerfile),
            "--tag",
            image_ref,
            str(REPO_ROOT),
        ]
    )
    subprocess.run(base_command, check=True, cwd=str(REPO_ROOT))


def run_test(image_ref: str) -> None:
    """Run the repo's privileged Docker systemd boot test."""
    if shutil.which("docker") is None:
        raise RuntimeError("docker is required by tests/test_container.sh")
    subprocess.run(
        ["bash", str(TEST_SCRIPT), image_ref],
        check=True,
        cwd=str(REPO_ROOT),
    )
