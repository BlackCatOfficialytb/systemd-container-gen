#!/usr/bin/env python3
"""Check an upstream Ubuntu tag and render its Dockerfile when it changes.

Each supported Ubuntu release tag has isolated digest state and a separate
generated Dockerfile so the GitHub Actions matrix jobs never race each other.

The script deliberately uses only the Python standard library so it can run in
a stock GitHub Actions runner without a package installation step.

Usage:
    python3 scripts/check_and_render.py ENV_FILE --tag jammy [--force] \
        [--github-output GITHUB_OUTPUT]

ENV_FILE receives GitHub Actions KEY=value lines (normally $GITHUB_ENV).
The optional GITHUB_OUTPUT file receives the same keys as step outputs.
"""

import json
import os
import sys
import urllib.request
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
HTTP_TIMEOUT_SECONDS = 30
USER_AGENT = "ubuntu-systemd-digest-check/2.0"
IMAGE_NAME = "quanvm0501alt1/ubuntu-systemd"

# Each entry is one upstream Ubuntu release and one independent build tier.
# Adding another Ubuntu series only requires another entry here and in the
# workflow matrix. A future non-Ubuntu distribution can reuse the polling and
# renderer with its own template and repository settings.
TARGETS = {
    "jammy": {
        "base_image": "ubuntu",
        "base_tag": "jammy",
        "registry": "registry-1.docker.io",
        "repository": "library/ubuntu",
        "docker_tags": ("jammy", "22.04"),
        "template": "Dockerfile.template",
        "dockerfile": "Dockerfile.jammy",
        "state_file": "digests/last_digest_jammy.txt",
    },
    "noble": {
        "base_image": "ubuntu",
        "base_tag": "noble",
        "registry": "registry-1.docker.io",
        "repository": "library/ubuntu",
        "docker_tags": ("noble", "24.04"),
        "template": "Dockerfile.template",
        "dockerfile": "Dockerfile.noble",
        "state_file": "digests/last_digest_noble.txt",
    },
    "resolute": {
        "base_image": "ubuntu",
        "base_tag": "resolute",
        "registry": "registry-1.docker.io",
        "repository": "library/ubuntu",
        "docker_tags": ("resolute", "26.04", "latest"),
        "template": "Dockerfile.template",
        "dockerfile": "Dockerfile.resolute",
        "state_file": "digests/last_digest_resolute.txt",
    },
    "stonking": {
        "base_image": "ubuntu",
        "base_tag": "stonking",
        "registry": "registry-1.docker.io",
        "repository": "library/ubuntu",
        "docker_tags": ("stonking", "26.10", "rolling"),
        "template": "Dockerfile.template",
        "dockerfile": "Dockerfile.stonking",
        "state_file": "digests/last_digest_stonking.txt",
    },
}

# Accept both manifest lists (Docker) and image indexes (OCI). Without an
# explicit Accept header, Docker Hub may return a single-platform manifest.
MANIFEST_ACCEPT_HEADERS = ", ".join(
    (
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
    )
)


def usage(stream=sys.stdout):
    """Print command-line help without pulling in argparse."""
    print(
        "Usage: check_and_render.py ENV_FILE --tag TAG [--force] "
        "[--github-output FILE]\n"
        "\n"
        "  ENV_FILE              File to receive GitHub Actions KEY=value lines\n"
        "  --tag TAG             Upstream Ubuntu tag to check (required)\n"
        "  --force               Render and build even when the digest is unchanged\n"
        "  --github-output FILE  Also write step outputs (normally $GITHUB_OUTPUT)\n"
        "\n"
        f"Available tags: {', '.join(sorted(TARGETS))}",
        file=stream,
    )


def parse_args(argv):
    """Return (env_file, github_output, force, tag) from CLI arguments."""
    env_file = None
    github_output = None
    force = False
    tag = None
    index = 0

    while index < len(argv):
        argument = argv[index]

        if argument in ("-h", "--help"):
            usage()
            raise SystemExit(0)
        if argument == "--force":
            force = True
        elif argument == "--tag":
            index += 1
            if index >= len(argv):
                raise ValueError("--tag requires a value")
            tag = argv[index]
        elif argument.startswith("--tag="):
            tag = argument.split("=", 1)[1]
            if not tag:
                raise ValueError("--tag requires a value")
        elif argument == "--github-output":
            index += 1
            if index >= len(argv):
                raise ValueError("--github-output requires a value")
            github_output = Path(argv[index])
        elif argument.startswith("--github-output="):
            value = argument.split("=", 1)[1]
            if not value:
                raise ValueError("--github-output requires a value")
            github_output = Path(value)
        elif argument.startswith("-"):
            raise ValueError(f"unknown option: {argument}")
        elif env_file is None:
            env_file = Path(argument)
        else:
            raise ValueError("only one ENV_FILE argument is allowed")

        index += 1

    if env_file is None:
        raise ValueError("missing required ENV_FILE argument")
    if tag is None:
        raise ValueError("missing required --tag argument")

    return env_file, github_output, force, tag


def read_json(url):
    """Fetch a JSON document from a URL."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return json.load(response)


def fetch_anonymous_token(registry, repository):
    """Return an anonymous pull token for a public repository."""
    token_url = (
        "https://auth.docker.io/token"
        "?service=registry.docker.io"
        f"&scope=repository:{repository}:pull"
    )
    payload = read_json(token_url)
    token = payload.get("token") or payload.get("access_token")
    if not token:
        raise RuntimeError(f"no bearer token returned for {registry}/{repository}")
    return token


def fetch_manifest_digest(registry, repository, tag, token):
    """Return Docker-Content-Digest without downloading any image layers."""
    manifest_url = f"https://{registry}/v2/{repository}/manifests/{tag}"
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


def read_digest(path):
    """Return the previously recorded digest, or an empty string."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def atomic_write(path, content):
    """Write a file atomically so interrupted runs cannot leave partial state."""
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


def render_dockerfile(config):
    """Render the target's template and return the generated Dockerfile path."""
    template_path = REPOSITORY_ROOT / config["template"]
    dockerfile_path = REPOSITORY_ROOT / config["dockerfile"]

    template = template_path.read_text(encoding="utf-8")
    substitutions = {
        "{{BASE_IMAGE}}": config["base_image"],
        "{{BASE_TAG}}": config["base_tag"],
        "{{IMAGE_NAME}}": IMAGE_NAME,
        "{{TARGET_TAGS}}": ",".join(config["docker_tags"]),
    }

    rendered = template
    for placeholder, value in substitutions.items():
        rendered = rendered.replace(placeholder, value)

    if "{{" in rendered or "}}" in rendered:
        raise RuntimeError(
            f"{config['template']} contains unsupported or unresolved placeholders"
        )

    atomic_write(dockerfile_path, rendered)
    return dockerfile_path


def write_actions_file(path, values):
    """Write GitHub Actions KEY=value command-file content."""
    content = "".join(f"{key}={value}\n" for key, value in values.items())
    atomic_write(path, content)


def write_result(
    env_file,
    github_output,
    tag,
    config,
    digest,
    should_build,
    previous_digest,
):
    """Expose the check result to the workflow as env vars and step outputs."""
    values = {
        "should_build": "true" if should_build else "false",
        "docker_tags": ",".join(config["docker_tags"]),
        "upstream_digest": digest,
        "previous_digest": previous_digest or "none",
        "base_image": f"{config['base_image']}:{config['base_tag']}",
        "tag": tag,
        "image_name": IMAGE_NAME,
    }

    write_actions_file(env_file, values)
    if github_output is not None:
        write_actions_file(github_output, values)


def check_and_render(env_file, github_output, force, tag):
    """Run one digest check, rendering only when a build is needed."""
    config = TARGETS.get(tag)
    if config is None:
        available = ", ".join(sorted(TARGETS))
        raise ValueError(f"unknown tag '{tag}' (available: {available})")

    base_reference = f"{config['base_image']}:{config['base_tag']}"
    state_path = REPOSITORY_ROOT / config["state_file"]
    previous_digest = read_digest(state_path)

    print(
        f"Checking {base_reference} from {config['registry']} "
        f"({config['repository']})"
    )
    token = fetch_anonymous_token(config["registry"], config["repository"])
    digest = fetch_manifest_digest(
        config["registry"],
        config["repository"],
        config["base_tag"],
        token,
    )

    print(f"Previous digest: {previous_digest or '<none>'}")
    print(f"Upstream digest: {digest}")

    changed = digest != previous_digest
    if not changed and not force:
        print("Upstream image is unchanged; skipping the build.")
        write_result(
            env_file,
            github_output,
            tag,
            config,
            digest,
            should_build=False,
            previous_digest=previous_digest,
        )
        return 0

    reason = "forced build" if not changed and force else "upstream digest changed"
    print(f"Build required ({reason}); rendering {config['dockerfile']}.")
    dockerfile_path = render_dockerfile(config)

    # Record the digest only after rendering succeeds. The workflow saves this
    # file to the Actions cache only after a successful test and push.
    atomic_write(state_path, f"{digest}\n")

    print(f"Wrote {dockerfile_path.relative_to(REPOSITORY_ROOT)}")
    write_result(
        env_file,
        github_output,
        tag,
        config,
        digest,
        should_build=True,
        previous_digest=previous_digest,
    )
    print(
        f"::notice::Building {IMAGE_NAME} for {tag} "
        f"(tags: {','.join(config['docker_tags'])}) because {reason} ({digest})."
    )
    return 0


def main(argv):
    """CLI entry point. Return a shell-friendly exit status."""
    try:
        env_file, github_output, force, tag = parse_args(argv)
        return check_and_render(env_file, github_output, force, tag)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        usage(stream=sys.stderr)
        return 2
    except Exception as error:
        print(f"::error::Upstream digest check failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
