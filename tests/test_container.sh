#!/usr/bin/env bash
#
# Boot a locally built systemd image and verify that systemd reaches a usable
# state. "degraded" is accepted because minimal containers commonly have a few
# optional units that cannot run without host-specific resources.
#
# Usage: tests/test_container.sh IMAGE

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 IMAGE" >&2
    exit 2
fi

IMAGE="$1"
CONTAINER="systemd-test-$$"
READY_STATE=""
LAST_STATE="unknown"
MAX_ATTEMPTS=15

# Accept docker first, falling back to podman; the CLIs largely agree for the
# commands used below.
if command -v docker >/dev/null 2>&1; then
    CLI="docker"
elif command -v podman >/dev/null 2>&1; then
    CLI="podman"
else
    echo "error: docker or podman is required to run the integration test" >&2
    exit 2
fi

# shellcheck disable=SC2317  # Invoked indirectly by the EXIT trap.
cleanup() {
    if "${CLI}" container inspect "${CONTAINER}" >/dev/null 2>&1; then
        "${CLI}" rm --force "${CONTAINER}" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

echo "Starting ${IMAGE} as ${CONTAINER} with ${CLI}"

# --privileged and --cgroupns=host let systemd manage cgroups in the same way
# it does on a normal Linux host. The host cgroup filesystem must be mounted
# read-write for units to start reliably on both cgroup v1 and v2 systems.
# Do not override the image CMD: distributions use different systemd paths.
if ! "${CLI}" run \
    --detach \
    --name "${CONTAINER}" \
    --privileged \
    --cgroupns=host \
    --volume /sys/fs/cgroup:/sys/fs/cgroup:rw \
    "${IMAGE}" >/dev/null; then
    echo "error: failed to start the test container" >&2
    "${CLI}" logs "${CONTAINER}" 2>&1 || true
    exit 1
fi

# Poll for up to 15 seconds. is-system-running exits non-zero for "degraded"
# and "starting", so capture its output without letting set -e abort the loop.
for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do
    LAST_STATE="$("${CLI}" exec "${CONTAINER}" systemctl is-system-running 2>/dev/null || true)"

    case "${LAST_STATE}" in
        running|degraded)
            READY_STATE="${LAST_STATE}"
            break
            ;;
    esac

    if [[ ${attempt} -lt ${MAX_ATTEMPTS} ]]; then
        sleep 1
    fi
done

if [[ -n "${READY_STATE}" ]]; then
    echo "systemd is ${READY_STATE}; integration test passed."
    exit 0
fi

echo "error: systemd did not become ready within 15 seconds (last state: ${LAST_STATE:-unknown})" >&2
echo "--- container logs (last 100 lines) ---" >&2
"${CLI}" logs --tail 100 "${CONTAINER}" 2>&1 || true
echo "--- systemctl status ---" >&2
"${CLI}" exec "${CONTAINER}" systemctl --no-pager --full status 2>&1 || true
exit 1
