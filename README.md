# ubuntu-systemd

[![Build systemd images](https://github.com/BlackCatOfficialytb/ubuntu-systemd-container-gen/actions/workflows/auto-build.yml/badge.svg?branch=main)](https://github.com/BlackCatOfficialytb/ubuntu-systemd-container-gen/actions/workflows/auto-build.yml)
[![Docker Pulls](https://img.shields.io/docker/pulls/quanvm0501alt1/ubuntu-systemd)](https://hub.docker.com/r/quanvm0501alt1/ubuntu-systemd)

A small, automatically maintained set of Ubuntu images with `systemd` running as
PID 1. Four upstream Ubuntu release channels are built independently and
published as
[`quanvm0501alt1/ubuntu-systemd`](https://hub.docker.com/r/quanvm0501alt1/ubuntu-systemd).
Each tier is rebuilt only when its official Ubuntu image digest changes.

## Image details

| Property | Value |
| --- | --- |
| Upstream base | Official `docker.io/library/ubuntu` tags: `jammy`, `noble`, `resolute`, `stonking` |
| PID 1 | `/sbin/init` |
| Stop signal | `SIGRTMIN+3` |
| Published Docker tags | `jammy`, `22.04`, `noble`, `24.04`, `resolute`, `26.04`, `latest`, `stonking`, `26.10`, `rolling` |
| Current build architecture | `linux/amd64` |

The image explicitly installs only `systemd`, `systemd-sysv`, and `udev` (plus
their required dependencies) and skips recommended packages. `getty` and
virtual-console activation are disabled because this is a headless container
image. Each container generates its own machine ID at boot.

## Available tags

| Docker tag | Upstream Ubuntu tag | Ubuntu version | LTS status | Pull command |
| --- | --- | --- | --- | --- |
| `jammy` | `jammy` | 22.04 | LTS | `docker pull quanvm0501alt1/ubuntu-systemd:jammy` |
| `22.04` | `jammy` | 22.04 | LTS | `docker pull quanvm0501alt1/ubuntu-systemd:22.04` |
| `noble` | `noble` | 24.04 | LTS | `docker pull quanvm0501alt1/ubuntu-systemd:noble` |
| `24.04` | `noble` | 24.04 | LTS | `docker pull quanvm0501alt1/ubuntu-systemd:24.04` |
| `resolute` | `resolute` | 26.04 | LTS | `docker pull quanvm0501alt1/ubuntu-systemd:resolute` |
| `26.04` | `resolute` | 26.04 | LTS | `docker pull quanvm0501alt1/ubuntu-systemd:26.04` |
| `latest` | `resolute` | 26.04 | LTS | `docker pull quanvm0501alt1/ubuntu-systemd:latest` |
| `stonking` | `stonking` | 26.10 | Interim | `docker pull quanvm0501alt1/ubuntu-systemd:stonking` |
| `26.10` | `stonking` | 26.10 | Interim | `docker pull quanvm0501alt1/ubuntu-systemd:26.10` |
| `rolling` | `stonking` | 26.10 | Interim | `docker pull quanvm0501alt1/ubuntu-systemd:rolling` |

Tags in the same tier refer to the same image. `latest` intentionally follows
the 26.04 LTS release (`resolute`), not the newest interim release. Use
`rolling` to follow 26.10 (`stonking`).

## Quick start

These images are **system containers**, not application containers. They need
access to the host cgroup hierarchy so systemd can manage services correctly.
Replace `:latest` with any tag from the table above.

### Podman

```bash
podman run -it --rm \
  --name ubuntu-systemd \
  --security-opt label=disable \
  --systemd=always \
  quanvm0501alt1/ubuntu-systemd:latest
```

`--systemd=always` configures the container mode, stop signal, and the tmpfs
mounts systemd expects. To run it in the background instead:

```bash
podman run -dit \
  --name ubuntu-systemd \
  --security-opt label=disable \
  --systemd=always \
  quanvm0501alt1/ubuntu-systemd:latest

podman exec -it ubuntu-systemd bash
```

For rootless Podman, the host must use cgroup v2 with systemd cgroup delegation;
otherwise run Podman as root or use a properly delegated user session.

### Docker

```bash
docker run -d \
  --name ubuntu-systemd \
  --privileged \
  --cgroupns=host \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
  quanvm0501alt1/ubuntu-systemd:latest

docker exec -it ubuntu-systemd bash
```

Check the systemd state and stop the container cleanly:

```bash
docker exec ubuntu-systemd systemctl is-system-running
docker stop ubuntu-systemd
docker rm ubuntu-systemd
```

Depending on host restrictions, systemd may report `degraded` when optional
kernel filesystems cannot be mounted inside the container. Inspect the affected
units with `systemctl --failed`; the integration test intentionally accepts
`degraded` as a successful boot.

`--privileged` is required for this Docker configuration because systemd needs
to manage mounts and cgroups. That grants the container extensive host access;
see [Security considerations](#security-considerations). Docker Desktop on
macOS or Windows does not expose a Linux host cgroup hierarchy, so systemd
containers are best run on a Linux host.

After starting the container, opening a Bash shell displays the same run
commands from the reminder banner in `/etc/bash.bashrc`.

## How the automated build works

The workflow in [`.github/workflows/auto-build.yml`](.github/workflows/auto-build.yml)
runs every Sunday at 05:30 UTC and can also be started manually from the Actions
tab. That window is after Canonical's weekly security rebuilds have normally
propagated to Docker Hub, while GitHub Actions is at its quietest. All matrix
jobs use GitHub's `ubuntu-26.04` runner image, which is currently Ubuntu 26.04.1
LTS. The workflow has four independent matrix jobs, one per upstream Ubuntu tag,
with `fail-fast: false` so one failed release does not block the others.

Each job avoids downloading image layers just to check for updates:

1. `scripts/check_and_render.py --tag <tag>` requests an anonymous pull token
   from `auth.docker.io`.
2. It sends a `HEAD` request for
   `registry-1.docker.io/v2/library/ubuntu/manifests/<tag>`, accepting both
   Docker manifest lists and OCI image indexes.
3. It reads the `Docker-Content-Digest` response header and compares it with the
   tier-specific state file `digests/last_digest_<tag>.txt`.
4. If the digest is unchanged and the run is not forced, that matrix job skips
   buildx setup, login, build, test, and push.
5. If the digest changed (or `force_build` was selected), the script renders
   `Dockerfile.template` into `Dockerfile.<tag>`, records the new digest, and
   emits `should_build=true` and the tier's comma-separated `docker_tags`.
6. The job builds `local/test-image:<tag>`, boots it with the required cgroup
   configuration, and polls `systemctl is-system-running` for up to 10 seconds.
   Both `running` and `degraded` are accepted.
7. Only after the integration test passes is the image pushed under every target
   tag for that tier.
8. On success, only that tier's digest file is saved to the Actions cache. A
   failed build never advances its cached digest, so the next run retries it.

For example, a changed `resolute` digest publishes `resolute`, `26.04`, and
`latest`; a changed `stonking` digest publishes `stonking`, `26.10`, and
`rolling`.

Digest state is isolated per matrix entry. The workflow caches exactly
`digests/last_digest_<tag>.txt` using `actions/cache/restore` and
`actions/cache/save`. Actions cache entries are immutable, so each successful
push saves a new run-specific key while restore uses a tag-specific prefix.

The matrix jobs may run in parallel. A job-level concurrency group per Ubuntu
tag prevents two workflow runs from publishing the same tier at the same time.

### Manual and forced runs

Use **Actions → Build systemd images → Run workflow** and enable `force_build`,
or use GitHub CLI:

```bash
gh workflow run auto-build.yml --ref main -f force_build=true
```

A forced run rebuilds and republishes all four tiers even when their upstream
digests have not changed. This is also how to publish a change to
`Dockerfile.template` before the next upstream digest update.

### Repository secrets

Configure these repository secrets before enabling the workflow:

| Secret | Purpose |
| --- | --- |
| `DOCKERHUB_USERNAME` | Docker Hub account that owns the repository |
| `DOCKERHUB_TOKEN` | Docker Hub access token with read/write permission |

The upstream digest check itself is anonymous and does not use either secret.
The workflow only has `contents: read` permission for `GITHUB_TOKEN`.

## Local development

The digest checker needs only Python 3 and its standard library. It has no
third-party dependencies.

Render one release tier and inspect the emitted variables:

```bash
python3 scripts/check_and_render.py /tmp/ubuntu-systemd-resolute.env \
  --tag resolute \
  --force

cat /tmp/ubuntu-systemd-resolute.env
```

To render all four tiers:

```bash
for tag in jammy noble resolute stonking; do
  python3 scripts/check_and_render.py "/tmp/ubuntu-systemd-${tag}.env" \
    --tag "${tag}" \
    --force
done
```

Build and test one rendered image locally on Linux:

```bash
docker buildx build --load \
  --file Dockerfile.resolute \
  --tag local/test-image:resolute .

bash tests/test_container.sh local/test-image:resolute
```

`Dockerfile.<tag>` and `digests/last_digest_<tag>.txt` are generated artifacts
and are ignored by Git. `Dockerfile.template` is the source of truth. After
changing the template or other build inputs, trigger the workflow manually with
`force_build` so the change is published even when the upstream digests have not
moved.

### Adding another Ubuntu tier

1. Add an entry to the `TARGETS` dictionary in
   `scripts/check_and_render.py`, including the upstream tag, Docker tags,
   generated Dockerfile path, and digest state path.
2. Add the tag to the workflow matrix.
3. Add the tag and pull command to the table in this README.
4. Render the Dockerfile, build it, and run the integration test before pushing.

### Adding another distribution

The polling, state, rendering, and test flow are not Ubuntu-specific. A future
Debian, Fedora, or Arch Linux tier can reuse them with a distribution-specific
template and a new entry in `TARGETS` (or a similarly named config mapping), plus
a matrix entry and isolated cache path. Run the rendered image through
`tests/test_container.sh` before allowing a push.

## Security considerations

- **Do not treat this image as a security boundary.** The documented Docker
  command uses `--privileged`, which gives the container broad control over the
  host. Run it only with trusted workloads and trusted users.
- The image runs systemd as root because PID 1 must manage services and cgroups.
  It is not a rootless application sandbox.
- Only a minimal package set is installed (`--no-install-recommends`) and apt
  metadata is removed in the same layer.
- Each weekly rebuild picks up updated packages for its Ubuntu release. If a
  tier fails, its previous image and tags remain published.
- `latest` stays on the 26.04 LTS tier. Use `rolling` deliberately if you want
  the 26.10 interim release.
- The digest check is read-only and anonymous. Docker Hub credentials are used
  only after a build is required and are supplied through repository secrets.
- The workflow has read-only repository permissions and never checks out with
  persisted credentials.
- For reproducible production deployments, pin the published image by digest
  instead of relying on a floating tag.
- Keep the Docker Hub access token scoped to the single repository and rotate it
  if it is exposed.

## Contributing

Issues and pull requests are welcome.

1. Fork the repository and create a focused branch.
2. Keep changes compatible with the template/configuration split; do not commit
   generated `Dockerfile.<tag>` files or digest state files.
3. Run the digest checker, build, and integration test locally for each affected
   tier.
4. Describe the change and any security implications in the pull request.
5. For a new Ubuntu tier or distribution, include a tested template,
   configuration entry, matrix entry, and documentation updates.

Please avoid opening public issues containing credentials or other secrets.

## Roadmap

- [ ] Debian support using the shared apt-based template pattern
- [ ] Fedora support using a dnf-specific template
- [ ] Arch Linux support using a pacman-specific template
- [ ] Multi-architecture image manifests with native integration testing
- [ ] SBOM generation and signed image provenance
