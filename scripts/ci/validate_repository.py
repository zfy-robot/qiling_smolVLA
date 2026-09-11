#!/usr/bin/env python3
"""Fast, network-free release boundary checks for the public repository."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
MAX_TRACKED_BYTES = 10 * 1024 * 1024
GITLINKS = {
    "IsaacLab": "f764c12a5ccf5cc6997de699653b4bb70e56a3f7",
    "lerobot": "3f2179f3b69708b6ad009b2e7685dd9d05269ee1",
}
FORBIDDEN_EXACT = {
    ".env",
    "docker/Dockerfile",
    "docker/build_full.sh",
    "docker/compose.yaml",
    "docker/entrypoint.sh",
    "docker/prepare_kit_extensions.sh",
    "docker/prepare_workspace.sh",
    "docker/run.sh",
    "s4_smolvla_isaaclab/hardware_teleop/config/ros_env.sh",
    "s4_smolvla_isaaclab/real_vla/config/cameras.yaml",
}
FORBIDDEN_PREFIXES = (
    ".s4/",
    "docker/runtime/",
    "release/staging/",
    "s4_smolvla_isaaclab/assets/",
    "s4_smolvla_isaaclab/local_assets/",
    "s4_smolvla_isaaclab/models/",
    "s4_smolvla_isaaclab/datasets/",
    "s4_smolvla_isaaclab/outputs/",
)
TEXT_SUFFIXES = {
    ".cfg", ".conf", ".env", ".ini", ".json", ".md", ".py", ".sh",
    ".toml", ".txt", ".yaml", ".yml",
}
SECRET_PATTERNS = {
    "GitHub token": re.compile(r"(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}"),
    "Hugging Face token": re.compile(r"hf_[A-Za-z0-9]{20,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private key": re.compile(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY"),
}
HOST_HOME = re.compile(r"(?<![A-Za-z0-9_.-])/(?:home|Users)/[A-Za-z0-9._-]+/")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True)


def tracked_files() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [item.decode() for item in raw.split(b"\0") if item]


def validate_locks(errors: list[str]) -> None:
    for relative in (
        "release/isaac_assets_5.1.lock.json",
        "release/isaac_extensions_5.1.lock.json",
    ):
        path = ROOT / relative
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{relative}: invalid JSON: {exc}")
            continue
        for key, value in walk_json(payload):
            if key.endswith("sha256") and (not isinstance(value, str) or not SHA256.fullmatch(value)):
                errors.append(f"{relative}: invalid SHA256 field {key}")
            if key.endswith("url") and isinstance(value, str) and not value.startswith("https://"):
                errors.append(f"{relative}: URL is not HTTPS: {key}")


def validate_release_manifest(errors: list[str]) -> None:
    relative = "release/manifest.yaml"
    path = ROOT / relative
    if not path.is_file():
        errors.append(f"missing formal release manifest: {relative}")
        return
    text = path.read_text(encoding="utf-8")
    if "TODO" in text:
        errors.append(f"{relative}: unresolved TODO")

    if not re.search(r"(?m)^release_status:\s*released\s*$", text):
        errors.append(f"{relative}: release_status is not released")
    public_statuses = re.findall(r"(?m)^\s*publication_status:\s*public\s*$", text)
    if len(public_statuses) != 4:
        errors.append(f"{relative}: expected public status for image set and all three images")
    if len(re.findall(r"(?m)^\s*remote_digest_verified:\s*\d{4}-\d{2}-\d{2}\s*$", text)) != 3:
        errors.append(f"{relative}: expected three remote digest verification dates")
    if len(re.findall(r"(?m)^\s*anonymous_pull_verified:\s*\d{4}-\d{2}-\d{2}\s*$", text)) != 3:
        errors.append(f"{relative}: expected three anonymous pull verification dates")

    release_match = re.search(r"(?m)^release:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$", text)
    if not release_match:
        errors.append(f"{relative}: release is not semantic version X.Y.Z")
        release = None
    else:
        release = release_match.group(1)

    project_match = re.search(
        r"(?m)^  project:\n    repository: [^\n]+\n    commit: ([0-9a-f]{40})$",
        text,
    )
    if not project_match or not COMMIT.fullmatch(project_match.group(1)):
        errors.append(f"{relative}: missing immutable project source commit")
    else:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", project_match.group(1), "HEAD"],
            cwd=ROOT,
            check=False,
        )
        if result.returncode != 0:
            errors.append(f"{relative}: project source commit is not an ancestor of HEAD")

    for name, commit in GITLINKS.items():
        if commit not in text:
            errors.append(f"{relative}: missing pinned {name} commit {commit}")

    image_refs = re.findall(
        r"(?m)^\s+ref:\s*(ghcr\.io/zfy-robot/[a-z0-9-]+@sha256:[0-9a-f]{64})\s*$",
        text,
    )
    if len(image_refs) != 3 or len(set(image_refs)) != 3:
        errors.append(f"{relative}: expected three unique immutable GHCR image refs")
    if release:
        image_tags = re.findall(
            rf"(?m)^\s+tag:\s*ghcr\.io/zfy-robot/[a-z0-9-]+:v{re.escape(release)}\s*$",
            text,
        )
        if len(image_tags) != 3:
            errors.append(f"{relative}: expected three GHCR tags matching v{release}")

    for key, value in re.findall(r"(?m)^\s+([a-z_]*sha256):\s*([0-9a-f]+)\s*$", text):
        if not SHA256.fullmatch(value):
            errors.append(f"{relative}: invalid {key}")

    referenced_hashes = {
        "release/artifacts.yaml": re.search(
            r"(?m)^\s+manifest_sha256:\s*([0-9a-f]{64})\s*$", text
        ),
        "release/isaac_assets_5.1.lock.json": re.search(
            r"(?ms)lock_file:\s*release/isaac_assets_5\.1\.lock\.json\s*\n\s+lock_sha256:\s*([0-9a-f]{64})",
            text,
        ),
        "release/isaac_extensions_5.1.lock.json": re.search(
            r"(?ms)lock_file:\s*release/isaac_extensions_5\.1\.lock\.json\s*\n\s+lock_sha256:\s*([0-9a-f]{64})",
            text,
        ),
    }
    for referenced, match in referenced_hashes.items():
        actual = hashlib.sha256((ROOT / referenced).read_bytes()).hexdigest()
        if match is None or match.group(1) != actual:
            errors.append(f"{relative}: hash mismatch for {referenced}")


def walk_json(value: object, prefix: str = ""):
    if isinstance(value, dict):
        for key, item in value.items():
            field = f"{prefix}.{key}" if prefix else str(key)
            yield field, item
            yield from walk_json(item, field)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk_json(item, f"{prefix}[{index}]")


def main() -> int:
    errors: list[str] = []
    files = tracked_files()

    for relative in files:
        path = ROOT / relative
        if relative in FORBIDDEN_EXACT or relative.startswith(FORBIDDEN_PREFIXES):
            errors.append(f"forbidden generated/site file is tracked: {relative}")
            continue
        if path.is_file() and path.stat().st_size > MAX_TRACKED_BYTES:
            errors.append(f"tracked file exceeds 10 MiB: {relative} ({path.stat().st_size} bytes)")

        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if HOST_HOME.search(text):
            errors.append(f"host-specific absolute home path: {relative}")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"possible {label}: {relative}")
        if path.suffix == ".py":
            try:
                ast.parse(text, filename=relative)
            except SyntaxError as exc:
                errors.append(f"Python syntax error: {relative}:{exc.lineno}: {exc.msg}")

    stage_lines = git_output("ls-files", "--stage", *GITLINKS).splitlines()
    stages = {line.split(maxsplit=3)[3]: line.split(maxsplit=3)[:3] for line in stage_lines}
    for relative, expected in GITLINKS.items():
        record = stages.get(relative)
        if record is None:
            errors.append(f"missing submodule gitlink: {relative}")
        elif record[0] != "160000" or record[1] != expected:
            errors.append(f"submodule {relative} is not pinned to {expected}")

    validate_locks(errors)
    validate_release_manifest(errors)

    if errors:
        print("Repository release checks failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"[OK] repository boundary: {len(files)} tracked paths")
    print("[OK] Python syntax, secrets/paths, file sizes, submodules, locks and release manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
