# systemd container generator

[![Build systemd images](https://github.com/BlackCatOfficialytb/systemd-container-gen/actions/workflows/auto-build.yml/badge.svg?branch=main)](https://github.com/BlackCatOfficialytb/systemd-container-gen/actions/workflows/auto-build.yml)
[![Docker Pulls](https://img.shields.io/docker/pulls/quanvm0501alt1/ubuntu-systemd)](https://hub.docker.com/r/quanvm0501alt1/ubuntu-systemd)

A modular, digest-driven build system for minimal systemd containers. Each
distribution has its own Dockerfile template and digest state, while one
orchestrator renders the selected template and decides whether a weekly build is
needed.

Ubuntu is published to Docker Hub at
[`quanvm0501alt1/ubuntu-systemd`](https://hub.docker.com/r/quanvm0501alt1/ubuntu-systemd).
Debian, Fedora, and openSUSE Leap are currently **staging artifacts**: they are
built, boot-tested, saved as image tarballs, and attached to the Actions run for
three days. They are not pushed to Docker Hub.

## Deployment status

| Distribution | Matrix targets | Local artifact image | Hub target | Status |
| --- | --- | --- | --- | --- |
| Ubuntu | `resolute`, `noble`, `jammy`, `stonking` | `quanvm0501alt1/ubuntu-systemd` | `quanvm0501alt1/ubuntu-systemd` | Active Hub push |
| Debian | `trixie`, `bookworm` | `debian-systemd` | `<DOCKERHUB_USERNAME>/debian-systemd` | Staging artifact |
| Fedora | `44`, `43`, `45` | `fedora-systemd` | `<DOCKERHUB_USERNAME>/fedora-systemd` | Staging artifact |
| openSUSE Leap | `latest` | `opensuse-systemd` | `<DOCKERHUB_USERNAME>/opensuse-systemd` | Staging artifact |

Staging artifacts use a placeholder Hub repository. After downloading and
loading one, it is tagged locally as `<distro>-systemd:<tag>` so it can be run or
retagged for a future Hub push without requiring credentials in CI.

## Published and target tags

| Distribution | Upstream tag | Docker tags | Notes |
| --- | --- | --- | --- |
| Ubuntu | `resolute` | `resolute`, `26.04`, `latest` | Active Hub push; `latest` follows 26.04 LTS |
| Ubuntu | `noble` | `noble`, `24.04` | Active Hub push; LTS |
| Ubuntu | `jammy` | `jammy`, `22.04` | Active Hub push; LTS |
| Ubuntu | `stonking` | `stonking`, `26.10`, `rolling` | Active Hub push; interim release |
| Debian | `trixie` | `trixie`, `13`, `latest`, `stable` | Staging artifact |
| Debian | `bookworm` | `bookworm`, `12`, `oldstable` | Staging artifact |
| Fedora | `44` | `44`, `latest` | Staging artifact |
| Fedora | `43` | `43` | Staging artifact |
| Fedora | `45` | `45` | Staging artifact |
| openSUSE Leap | `latest` | `leap`, `latest` | Staging artifact for Leap 16 |

openSUSE Leap 16 no longer publishes the separate `systemd-sysvinit` package.
The template installs `systemd`, which provides `/usr/lib/systemd/systemd`, and
uses that path as the container command.

## Ubuntu quick start

These images are **system containers**, not application containers. They need
access to the host cgroup hierarchy so systemd can manage services correctly.
Replace `:latest` with any published Ubuntu tag.

Pull the published Ubuntu tags directly:

```bash
docker pull quanvm0501alt1/ubuntu-systemd:latest
docker pull quanvm0501alt1/ubuntu-systemd:24.04
docker pull quanvm0501alt1/ubuntu-systemd:22.04
docker pull quanvm0501alt1/ubuntu-systemd:rolling
```

### Podman

```bash
podman run -it --rm \
  --name ubuntu-systemd \
  --security-opt label=disable \
  --systemd=always \
  quanvm0501alt1/ubuntu-systemd:latest
```

`--systemd=always` configures the container mode, stop signal, and the tmpfs
mounts systemd expects. To run it in the background:

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

### Docker CLI

```bash
docker run -d \
  --name ubuntu-systemd \
  --privileged \
  --cgroupns=host \
  --stop-signal=SIGRTMIN+3 \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
  quanvm0501alt1/ubuntu-systemd:latest

docker exec -it ubuntu-systemd bash
docker exec ubuntu-systemd systemctl is-system-running
```

`--privileged` grants the container extensive host access and is required by
this example. Docker Desktop on macOS or Windows does not expose a Linux host
cgroup hierarchy, so systemd containers are best run on a Linux host.

### Docker Compose

```yaml
services:
  systemd:
    image: quanvm0501alt1/ubuntu-systemd:24.04
    container_name: ubuntu-systemd
    privileged: true
    cgroup: host
    stop_signal: SIGRTMIN+3
    volumes:
      - /sys/fs/cgroup:/sys/fs/cgroup:rw
    tmpfs:
      - /run
      - /run/lock
```

```bash
docker compose up -d
docker compose exec systemd bash
docker compose down
```

### Ansible Molecule

The Docker driver can boot the published Ubuntu image as a systemd-enabled
Molecule platform:

```yaml
driver:
  name: docker

platforms:
  - name: ubuntu-2404-systemd
    image: quanvm0501alt1/ubuntu-systemd:24.04
    pre_build_image: true
    privileged: true
    cgroupns_mode: host
    command: /sbin/init
    volumes:
      - /sys/fs/cgroup:/sys/fs/cgroup:rw

provisioner:
  name: ansible
```

Run the scenario with `molecule test`. For Debian use `/sbin/init`; Fedora and
openSUSE use `/usr/lib/systemd/systemd`. Loaded staging images can be substituted
in `platforms[].image` after `docker load`.

## Debian, Fedora, and openSUSE staging artifacts

Staging images are available from the **Artifacts** section of a successful
workflow run. Each artifact is retained for **3 days** and contains a
`docker save` tarball with every target tag.

| Artifact name | Tarball | Loaded tags |
| --- | --- | --- |
| `debian-trixie-systemd` | `debian-trixie.tar` | `debian-systemd:trixie`, `:13`, `:latest`, `:stable` |
| `debian-bookworm-systemd` | `debian-bookworm.tar` | `debian-systemd:bookworm`, `:12`, `:oldstable` |
| `fedora-44-systemd` | `fedora-44.tar` | `fedora-systemd:44`, `:latest` |
| `fedora-43-systemd` | `fedora-43.tar` | `fedora-systemd:43` |
| `fedora-45-systemd` | `fedora-45.tar` | `fedora-systemd:45` |
| `opensuse-latest-systemd` | `opensuse-latest.tar` | `opensuse-systemd:leap`, `:latest` |

### Download and load

Find a recent successful run and download its artifact with GitHub CLI:

```bash
gh run list --workflow auto-build.yml --limit 5
gh run download <run-id> \
  --name debian-trixie-systemd \
  --dir staging/debian-trixie

docker load --input staging/debian-trixie/debian-trixie.tar
docker image ls debian-systemd
```

You can also download the artifact ZIP from the run's **Artifacts** section in
the GitHub UI and load the tar file inside it.

Run the loaded staging image with the same systemd requirements as Ubuntu:

```bash
docker run -d \
  --name debian-systemd \
  --privileged \
  --cgroupns=host \
  --stop-signal=SIGRTMIN+3 \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
  debian-systemd:trixie

docker exec debian-systemd systemctl is-system-running
```

### Promote a staging image later

Authenticate to Docker Hub and retag every desired loaded tag under the eventual
Hub repository. For example:

```bash
docker login
docker tag debian-systemd:trixie <DOCKERHUB_USERNAME>/debian-systemd:trixie
docker tag debian-systemd:13 <DOCKERHUB_USERNAME>/debian-systemd:13
docker push <DOCKERHUB_USERNAME>/debian-systemd:trixie
docker push <DOCKERHUB_USERNAME>/debian-systemd:13
```

The CI itself does not use Docker Hub credentials for staging distributions.

## How the automated build works

The workflow in [`.github/workflows/auto-build.yml`](.github/workflows/auto-build.yml)
runs every Sunday at **05:37 UTC** and can also be started manually. It uses
GitHub's `ubuntu-26.04` runner image, which is currently Ubuntu 26.04.1 LTS.

The matrix has ten independent targets. `fail-fast: false` allows the remaining
targets to continue if one distribution fails, and a per-target concurrency group
prevents two runs from publishing the same tag.

For every target:

1. `actions/cache/restore` restores exactly
   `digests/<distro>_<upstream-tag>.txt` for that matrix entry.
2. `scripts/check_and_render.py` requests an anonymous Docker Hub token, then
   sends a `HEAD` request for `library/<distro>:<tag>` or
   `opensuse/leap:latest`, accepting Docker manifest lists and OCI indexes.
3. It reads `Docker-Content-Digest` without pulling layers and compares it with
   the cached state.
4. If unchanged and not forced, it writes `should_build=false`; all build, test,
   publish, and artifact steps are skipped.
5. If changed or forced, it renders `templates/<distro>.Dockerfile.template` to
   the root `Dockerfile`, records the new digest, and writes
   `should_build=true` plus the comma-separated `target_tags`.
6. The runner builds `local/test-image:<distro>-<tag>` with Buildx and runs
   `tests/test_container.sh`. The test boots the image with `--privileged`, polls
   `systemctl is-system-running` for up to 15 seconds, and accepts `running` or
   `degraded`.
7. Ubuntu logs in with `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` and pushes every
   target tag to `quanvm0501alt1/ubuntu-systemd`.
8. Staging distributions tag the local image as `<distro>-systemd:<tag>`, save a
   tarball with `docker save`, and upload it as a GitHub Actions artifact with
   three-day retention.
9. Only after the push or artifact upload succeeds is that target's digest file
   saved back to the Actions cache. Failed targets retry on the next run.

The state file is written before the build but is only persisted to the cache
after success. This prevents a failed build from advancing the digest and
silently skipping the next attempt.

### Manual and forced runs

Use **Actions → Build systemd images → Run workflow** and enable `force_build`,
or use GitHub CLI:

```bash
gh workflow run auto-build.yml --ref main -f force_build=true
```

A forced run rebuilds and republishes or re-uploads all ten targets, even when
their upstream digests are unchanged. This is also how to publish template
changes before the next upstream digest update.

### Secrets

| Secret | Purpose |
| --- | --- |
| `DOCKERHUB_USERNAME` | Docker Hub account for active Ubuntu pushes |
| `DOCKERHUB_TOKEN` | Docker Hub access token with Ubuntu repository write access |

Staging targets do not read either secret. The workflow has read-only repository
permissions and checks out with persisted credentials disabled.

## Repository layout

```text
.
├── .github/workflows/auto-build.yml
├── templates/
│   ├── ubuntu.Dockerfile.template
│   ├── debian.Dockerfile.template
│   ├── fedora.Dockerfile.template
│   └── opensuse.Dockerfile.template
├── scripts/check_and_render.py
├── tests/test_container.sh
├── Dockerfile                  # generated, ignored
├── digests/                    # generated state, ignored
└── README.md
```

## Local development

The orchestrator uses only Python 3 and its standard library. Render one target
and inspect the GitHub Actions-style output:

```bash
python3 scripts/check_and_render.py \
  --distro ubuntu \
  --upstream-repo library/ubuntu \
  --upstream-tag noble \
  --target-image quanvm0501alt1/ubuntu-systemd \
  --output-env /tmp/ubuntu-noble.env \
  --force

cat /tmp/ubuntu-noble.env
```

The output contains:

```text
should_build=true
target_tags=noble,24.04
```

Build and test the rendered root `Dockerfile`:

```bash
docker buildx build --load \
  --file Dockerfile \
  --tag local/test-image:ubuntu-noble .

bash tests/test_container.sh local/test-image:ubuntu-noble
```

Useful target arguments:

| Distribution | `--upstream-repo` | `--upstream-tag` | `--target-image` |
| --- | --- | --- | --- |
| Ubuntu | `library/ubuntu` | `resolute` | `quanvm0501alt1/ubuntu-systemd` |
| Ubuntu | `library/ubuntu` | `noble` | `quanvm0501alt1/ubuntu-systemd` |
| Ubuntu | `library/ubuntu` | `jammy` | `quanvm0501alt1/ubuntu-systemd` |
| Ubuntu | `library/ubuntu` | `stonking` | `quanvm0501alt1/ubuntu-systemd` |
| Debian | `library/debian` | `trixie` | `<DOCKERHUB_USERNAME>/debian-systemd` |
| Debian | `library/debian` | `bookworm` | `<DOCKERHUB_USERNAME>/debian-systemd` |
| Fedora | `library/fedora` | `44` | `<DOCKERHUB_USERNAME>/fedora-systemd` |
| Fedora | `library/fedora` | `43` | `<DOCKERHUB_USERNAME>/fedora-systemd` |
| Fedora | `library/fedora` | `45` | `<DOCKERHUB_USERNAME>/fedora-systemd` |
| openSUSE Leap | `opensuse/leap` | `latest` | `<DOCKERHUB_USERNAME>/opensuse-systemd` |

`Dockerfile`, `digests/`, and staging tarballs are generated artifacts and are
ignored by Git. After changing a template or the orchestrator, run the workflow
manually with `force_build` to publish the change.

### Adding a distribution or tag

1. Add the distribution template at `templates/<distro>.Dockerfile.template`.
2. Add its upstream-tag-to-target-tag mapping to `TARGET_TAGS` in
   `scripts/check_and_render.py`.
3. Add a matrix entry in `.github/workflows/auto-build.yml`, including
   `upstream_repo`, `upstream_tag`, `target_image`, and `push_to_hub`.
4. Add the tags and staging or active status to this README.
5. Render, build, and run `tests/test_container.sh` before pushing.

## Security considerations

- **Do not treat these images as a security boundary.** The documented Docker
  command uses `--privileged`, which grants broad control over the host. Run only
  trusted workloads with trusted users.
- The images run systemd as root because PID 1 must manage services and cgroups.
- Only a minimal package set is installed, and package-manager metadata is
  removed in the same layer.
- Ubuntu tags are updated weekly when the upstream digest changes. If a target
  fails, its previous Ubuntu image and tags remain published.
- Staging artifacts are unsigned GitHub Actions artifacts with a three-day
  retention. Verify their origin before loading or promoting them.
- For reproducible production deployments, pin images by digest rather than
  relying on a floating tag.
- Keep the Docker Hub access token scoped to the Ubuntu repository. Staging jobs
  do not receive it.

## Contributing

Issues and pull requests are welcome.

1. Fork the repository and create a focused branch.
2. Keep the template/orchestrator split; do not commit generated `Dockerfile`,
   `digests/`, or staging tarballs.
3. Run the renderer, build, and integration test for each affected target.
4. Describe any deployment or security implications in the pull request.
5. Include documentation updates for new tags, distributions, or artifact names.

Please avoid opening public issues containing credentials or other secrets.

## Roadmap

- [ ] Multi-architecture image manifests with native integration testing
- [ ] Signed staging artifacts and promoted-image provenance
- [ ] Optional automated Hub publishing for Debian, Fedora, and openSUSE
- [ ] SBOM generation for every distribution
