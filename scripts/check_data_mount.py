"""Preflight the running Paperplane data volume before replacing its container."""
import json
import subprocess
import sys


def inspect_command(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True, stderr=subprocess.DEVNULL)


def check_data_mount(config: dict, mounts: list[dict]) -> None:
    expected = config["volumes"]["paperplane_data"]["name"]
    data_mounts = [mount for mount in mounts if mount.get("Destination") == "/data"]
    if len(data_mounts) != 1:
        raise ValueError("The existing container has no unique /data mount.")
    mount = data_mounts[0]
    if mount.get("Type") != "volume" or mount.get("Name") != expected or not mount.get("RW"):
        raise ValueError("The existing /data mount differs from the writable named volume selected by Compose.")


def main() -> int:
    try:
        # Include stopped containers: a failed app must not be replaced using a new volume.
        containers = inspect_command("compose", "ps", "-a", "-q", "paperplane").split()
        if not containers:
            # container_name is fixed in Compose. Detect a project-name change.
            containers = inspect_command("ps", "-a", "-q", "--filter", "name=^/paperplane-app$").split()
        if not containers:
            print("No existing Paperplane container. Confirm the volume before a first deployment.")
            return 0
        if len(containers) != 1:
            raise ValueError("Multiple Paperplane containers matched the data-volume preflight.")
        config = json.loads(inspect_command("compose", "config", "--no-env-resolution", "--format", "json"))
        mounts = json.loads(inspect_command("inspect", "--format", "{{json .Mounts}}", containers[0]))
        check_data_mount(config, mounts)
    except ValueError as error:
        if isinstance(error, json.JSONDecodeError):
            print("Paperplane data-volume preflight could not read Docker output.", file=sys.stderr)
        else:
            print(str(error), file=sys.stderr)
        return 1
    except (OSError, KeyError, subprocess.CalledProcessError):
        print("Paperplane data-volume preflight could not read Docker configuration.", file=sys.stderr)
        return 1
    print("Verified existing Paperplane /data volume.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
