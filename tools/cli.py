#!/usr/bin/env python3
"""CLI for rendering and building systemd container images at home."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Render and build one local systemd container image using "
            "Docker or Podman."
        )
    )
    parser.add_argument(
        "--distro",
        choices=distros(),
        default="ubuntu",
        help="distribution to build (default: ubuntu)",
    )
    parser.add_argument(
        "--tag",
        help="upstream tag to build; defaults to the first tag of the distro",
    )
    parser.add_argument(
        "--target-image",
        help=(
            "image name used for the local build and rendered banner; "
            "defaults to local/<distro>-systemd"
        ),
    )
    parser.add_argument(
        "--runtime",
        choices=("auto", "docker", "podman"),
        default="auto",
        help="container runtime used for the build (default: auto)",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="only render the Dockerfile; do not build or test",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="after a successful build, run the repo's systemd boot test",
    )
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()

    if args.tag is None:
        args.tag = supported_tags(args.distro)[0]
    if args.target_image is None:
        args.target_image = default_target_image(args.distro)

    try:
        dockerfile, image_ref, tags = render(
            args.distro,
            args.tag,
            args.target_image,
        )
    except Exception as exc:
        print(f"error: failed to render image: {exc}", file=sys.stderr)
        return 1

    tag_line = ",".join(tags)
    print(f"Rendered {args.distro}:{args.tag} with tags {tag_line}")
    print(f"Image reference: {image_ref}")
    print(f"Dockerfile: {dockerfile}")

    if args.skip_build:
        print("Skipped build.")
        return 0

    try:
        build_image(dockerfile, image_ref, runtime=args.runtime)
    except Exception as exc:
        print(f"error: build failed: {exc}", file=sys.stderr)
        return 1

    if args.test:
        try:
            run_test(image_ref)
        except Exception as exc:
            print(f"error: integration test failed: {exc}", file=sys.stderr)
            return 1

    print(f"Built {image_ref}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
