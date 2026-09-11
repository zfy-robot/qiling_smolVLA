#!/usr/bin/env python3
"""Download one named S4 artifact set from the pinned ModelScope revision."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
from pathlib import Path
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "release" / "artifacts.yaml"
DEFAULT_LOCAL_DIR = ROOT / ".s4" / "artifacts"


def load_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


REPOSITORY_FILES = {
    "README.md",
    "LICENSE",
    "NOTICE",
    "artifact-manifest.json",
    "SHA256SUMS",
    "assets/README.md",
}


def verify_download(root: Path, selected_patterns: list[str]) -> None:
    checksum_path = root / "SHA256SUMS"
    if not checksum_path.is_file():
        raise FileNotFoundError(f"Downloaded bundle has no {checksum_path}")
    checked = 0
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        if relative in REPOSITORY_FILES or any(
            fnmatch.fnmatchcase(relative, pattern) for pattern in selected_patterns
        ):
            path = root / relative
            if not path.is_file():
                raise FileNotFoundError(f"Missing downloaded artifact file: {relative}")
            hasher = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                    hasher.update(chunk)
            digest = hasher.hexdigest()
            if digest != expected:
                raise ValueError(f"Checksum mismatch: {relative}")
            checked += 1
    if checked == 0:
        raise ValueError("No selected files were covered by SHA256SUMS")
    print(f"Verified {checked} downloaded files")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("set_name", help="Name under download_sets in artifacts.yaml")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--local-dir", type=Path, default=DEFAULT_LOCAL_DIR)
    parser.add_argument("--revision", help="Immutable ModelScope commit; overrides config")
    parser.add_argument("--no-verify", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    try:
        names = config["download_sets"][args.set_name]
    except KeyError:
        choices = ", ".join(sorted(config.get("download_sets", {})))
        raise ValueError(f"Unknown set {args.set_name!r}; choose one of: {choices}") from None
    selected_patterns: list[str] = []
    for item in names:
        if isinstance(item, str):
            artifact_name = item
            include = None
        elif isinstance(item, dict):
            artifact_name = item.get("artifact")
            include = item.get("include")
            if not isinstance(artifact_name, str) or not isinstance(include, list) or not include:
                raise ValueError(f"Invalid selective artifact entry in {args.set_name}: {item!r}")
        else:
            raise ValueError(f"Invalid artifact entry in {args.set_name}: {item!r}")
        try:
            spec = config["artifacts"][artifact_name]
        except KeyError:
            raise ValueError(f"Unknown artifact {artifact_name!r} in {args.set_name}") from None
        destination = spec["destination"].rstrip("/")
        if include is None:
            selected_patterns.append(f"{destination}/**")
        else:
            selected_patterns.extend(f"{destination}/{pattern.lstrip('/')}" for pattern in include)
    patterns = sorted(REPOSITORY_FILES | set(selected_patterns))
    repo = config["repository"]
    revision = args.revision or repo.get("revision")
    if not revision or revision == "master":
        print(
            "WARNING: using mutable ModelScope revision 'master'; pass --revision COMMIT for a release",
            file=sys.stderr,
        )
    try:
        from modelscope.hub.snapshot_download import dataset_snapshot_download
    except ImportError as exc:
        raise RuntimeError("Install modelscope in the artifact helper environment") from exc

    local_dir = args.local_dir.resolve()
    local_dir.mkdir(parents=True, exist_ok=True)
    dataset_snapshot_download(
        dataset_id=repo["repo_id"],
        revision=revision,
        local_dir=str(local_dir),
        allow_patterns=patterns,
    )
    if not args.no_verify:
        verify_download(local_dir, selected_patterns)
    print(local_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
