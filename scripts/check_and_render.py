#!/usr/bin/env python3
"""Check one upstream image digest and render its systemd Dockerfile.

The orchestrator is deliberately dependency-free: it uses only the Python
standard library so it can run on a stock GitHub Actions runner. Digest state is
kept per distribution and upstream tag, which allows every matrix entry to cache
and rebuild independently.

Usage:
    python3 scripts/check_and_render.py \
        --distro ubuntu \
        --upstream-repo library/ubuntu \
        --upstream-tag resolute \
        --target-image quanvm0501alt1/ubuntu-systemd \
        --output-env /tmp/render.env \
        [--force]

The output file is a GitHub Actions KEY=value command file. Pass
$GITHUB_OUTPUT in the workflow to expose should_build and target_tags as step
outputs, or use a local file when running the renderer by hand.
"""

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
HTTP_TIMEOUT_SECONDS = 30
USER_AGENT = "systemd-container-gen/1.0"

# Upstream tag -> Docker tags published for that build. Keeping this mapping in
# the orchestrator ensures every matrix entry renders and tags consistently.
TARGET_TAGS = {
    "ubuntu": {
        "resolute": ("resolute", "26.04", "latest"),
        "noble": ("noble", "24.04"),
        "jammy": ("jammy", "22.04"),
        "stonking": ("stonking", "26.10", "rolling"),
    },
    "debian": {
        "trixie": ("trixie", "13", "latest", "stable"),
        "bookworm": ("bookworm", "12", "oldstable"),
    },
    "fedora": {
        "44": ("44", "latest"),
        "43": ("43",),
        "45": ("45",),
    },
    "opensuse": {
        "latest": ("leap", "latest"),
    },
    "opensuse-tumbleweed": {
        "latest": ("tumbleweed", "rolling"),
    },
    "arch": {
        "latest": ("latest",),
    },
}

# Docker Hub exposes multi-platform images through manifest lists or OCI image
# indexes. Send both Accept values so the digest never silently falls back to a
# single-platform manifest.
MANIFEST_ACCEPT_HEADERS = ", ".join(
    (
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
    )
)


def parse_args():
    """Parse the arguments used by the workflow and local runs."""
    parser = argparse.ArgumentParser(
        description="Check an upstream image digest and render a systemd Dockerfile.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--distro",
        required=True,
        choices=tuple(sorted(TARGET_TAGS)),
        help="Distribution template to render",
    )
    parser.add_argument(
        "--upstream-repo",
        required=True,
        help="Docker Hub repository, for example library/ubuntu or opensuse/leap",
    )
    parser.add_argument(
        "--upstream-tag",
        required=True,
        help="Upstream Docker tag to check",
    )
    parser.add_argument(
        "--target-image",
        required=True,
        help="Target Docker Hub image name used in rendered banners and logs",
    )
    parser.add_argument(
        "--output-env",
        required=True,
        type=Path,
        help="GitHub Actions KEY=value output file",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Build even when the upstream digest is unchanged",
    )
    return parser.parse_args()


def normalize_repository(value):
    """Return a Docker Hub repository path without a registry prefix."""
    repository = value.strip().strip("/")
    for prefix in (
        "docker.io/",
        "index.docker.io/",
        "registry-1.docker.io/",
    ):
        if repository.startswith(prefix):
            repository = repository[len(prefix) :]
            break
    if not repository:
        raise ValueError("upstream repository cannot be empty")
    if "/" not in repository:
        repository = f"library/{repository}"
    return repository


def base_image_for(repository):
    """Convert a Docker Hub repository path into an image reference."""
    if repository.startswith("library/"):
        return repository.split("/", 1)[1]
    return repository


def read_json(url):
    """Fetch JSON from a URL."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return json.load(response)


def fetch_anonymous_token(repository):
    """Return an anonymous pull token for a public Docker Hub repository."""
    token_url = (
        "https://auth.docker.io/token"
        "?service=registry.docker.io"
        f"&scope=repository:{repository}:pull"
    )
    payload = read_json(token_url)
    token = payload.get("token") or payload.get("access_token")
    if not token:
        raise RuntimeError(f"no bearer token returned for {repository}")
    return token


def fetch_manifest_digest(repository, tag, token):
    """Read Docker-Content-Digest with a HEAD request, downloading no layers."""
    manifest_url = (
        f"https://registry-1.docker.io/v2/{repository}/manifests/{tag}"
    )
    request = urllib.request.Request(
        manifest_url,
        method="HEAD",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": MANIFEST_ACCEPT_HEADERS,
            "User-Agent": USER_AGENT,
        },
    )

    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        digest = (response.headers.get("Docker-Content-Digest") or "").strip()

    algorithm, separator, encoded = digest.partition(":")
    if (
        not separator
        or not algorithm
        or not encoded
        or any(character not in "0123456789abcdef" for character in encoded)
    ):
        raise RuntimeError(
            "registry response did not include a valid Docker-Content-Digest"
        )
    return digest


def digest_state_root():
    """Directory holding the per-target digest state files.

    Defaults to <repo>/digests. The workflow sets DIGEST_STATE_DIR when the
    checkout directory is ephemeral (for example a self-hosted runner whose
    workspace is cleaned after every job) so state persists in $HOME instead
    of needing actions/cache.
    """
    configured = os.environ.get("DIGEST_STATE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return REPOSITORY_ROOT / "digests"


def read_digest(path):
    """Read a previous digest, returning an empty string when none exists."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def atomic_write(path, content):
    """Write a file atomically so interrupted jobs never leave partial state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.name}.tmp.{os.getpid()}")

    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def write_command_file(path, values):
    """Write GitHub Actions KEY=value command-file content."""
    content = "".join(f"{key}={value}\n" for key, value in values.items())
    atomic_write(path, content)


def render_dockerfile(distro, upstream_tag, base_image, target_image, target_tags):
    """Render templates/<distro>.Dockerfile.template to the root Dockerfile."""
    template_path = (
        REPOSITORY_ROOT / "templates" / f"{distro}.Dockerfile.template"
    )
    dockerfile_path = REPOSITORY_ROOT / "Dockerfile"

    template = template_path.read_text(encoding="utf-8")
    substitutions = {
        "{{BASE_IMAGE}}": base_image,
        "{{BASE_TAG}}": upstream_tag,
        "{{IMAGE_NAME}}": target_image,
        "{{TARGET_TAGS}}": ",".join(target_tags),
    }

    rendered = template
    for placeholder, value in substitutions.items():
        rendered = rendered.replace(placeholder, value)

    if "{{" in rendered or "}}" in rendered:
        raise RuntimeError(
            f"{template_path.name} contains unsupported or unresolved placeholders"
        )

    atomic_write(dockerfile_path, rendered)
    return dockerfile_path


def run(args):
    """Execute one digest check and render when needed."""
    tags = TARGET_TAGS[args.distro].get(args.upstream_tag)
    if tags is None:
        supported = ", ".join(sorted(TARGET_TAGS[args.distro]))
        raise ValueError(
            f"unsupported upstream tag '{args.upstream_tag}' for "
            f"{args.distro} (supported: {supported})"
        )
    if any(character in args.upstream_tag for character in ("/", "\\", ":")):
        raise ValueError("upstream tag contains unsupported path characters")

    repository = normalize_repository(args.upstream_repo)
    base_image = base_image_for(repository)
    target_tags = ",".join(tags)
    state_path = digest_state_root() / f"{args.distro}_{args.upstream_tag}.txt"
    previous_digest = read_digest(state_path)

    print(f"Checking {repository}:{args.upstream_tag}")
    token = fetch_anonymous_token(repository)
    digest = fetch_manifest_digest(repository, args.upstream_tag, token)
    print(f"Previous digest: {previous_digest or '<none>'}")
    print(f"Upstream digest: {digest}")

    changed = digest != previous_digest
    should_build = changed or args.force

    if should_build:
        reason = "forced build" if args.force and not changed else "digest changed"
        print(f"Build required ({reason}); rendering {args.distro} Dockerfile.")
        dockerfile_path = render_dockerfile(
            args.distro,
            args.upstream_tag,
            base_image,
            args.target_image,
            tags,
        )
        atomic_write(state_path, f"{digest}\n")
        print(f"Wrote {dockerfile_path.relative_to(REPOSITORY_ROOT)}")
        print(f"Target tags: {target_tags}")
        print(
            f"::notice::Building {args.target_image} for "
            f"{args.distro}:{args.upstream_tag} ({target_tags}) because {reason}."
        )
    else:
        print("Upstream image is unchanged; skipping the build.")

    write_command_file(
        args.output_env,
        {
            "should_build": "true" if should_build else "false",
            "target_tags": target_tags,
        },
    )
    return 0


def main():
    """CLI entry point."""
    args = parse_args()
    try:
        return run(args)
    except Exception as error:
        print(f"::error::Upstream digest check failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
