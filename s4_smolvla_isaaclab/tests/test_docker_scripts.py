from __future__ import annotations

import os
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
S4 = WORKSPACE_ROOT / "s4"
DOCKER_VERIFY = WORKSPACE_ROOT / "docker/verify_runtime.sh"


def test_release_pull_uses_manifest_digest_and_local_compose_tag(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "docker-args.txt"
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" >> \"$DOCKER_ARGS_CAPTURE\"\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "DOCKER_ARGS_CAPTURE": str(capture),
            "S4_SIM_IMAGE": "local/s4-sim:test",
        }
    )

    result = subprocess.run(
        ["bash", str(S4), "pull", "sim"],
        cwd=WORKSPACE_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    remote = (
        "ghcr.io/zfy-robot/qiling-smolvla-sim@"
        "sha256:e0fb24a132c27ef271e20fd234fa215d34cf2e331296010f3f92d0ee55288c44"
    )
    assert capture.read_text(encoding="utf-8").splitlines() == [
        "image",
        "pull",
        remote,
        "image",
        "tag",
        remote,
        "local/s4-sim:test",
    ]
    assert f"[S4][PULL] ready: local/s4-sim:test <- {remote}" in result.stdout


def test_release_pull_rejects_unknown_service_without_running_docker(tmp_path: Path) -> None:
    fake_docker = tmp_path / "docker"
    fake_docker.write_text("#!/usr/bin/env bash\nexit 99\n", encoding="utf-8")
    fake_docker.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:/usr/bin:/bin"

    result = subprocess.run(
        ["/bin/bash", str(S4), "pull", "unknown"],
        cwd=WORKSPACE_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Unknown pull target" in result.stderr


def test_rollout_verifier_runs_camera_check_as_a_script() -> None:
    verifier = DOCKER_VERIFY.read_text(encoding="utf-8")
    assert 'isaac_camera_verify="$project_root/scripts/verify_isaac_camera.py"' in verifier
    assert '"$isaac_camera_verify" >"$kit_log" 2>&1' in verifier
    assert 'isaaclab_root/isaaclab.sh" -p -c' not in verifier
