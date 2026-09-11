#!/usr/bin/env python3
"""Plan or materialize the public ModelScope artifact tree.

The default mode is read-only and reports exactly what would be published.
Use --materialize only after reviewing the plan. Large immutable files are
hard-linked when possible and copied otherwise; text metadata is rewritten to
remove workstation-specific absolute paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "release" / "artifacts.yaml"
DEFAULT_OUTPUT = ROOT / "release" / "staging" / "qiling_smolvla"
TEXT_SUFFIXES = {".json", ".md", ".txt", ".yaml", ".yml", ".csv"}
SECRET_PATTERNS = (
    re.compile(r"(?i)(?:hf|ms)-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)(?:access[_-]?token|api[_-]?key|secret)\s*[:=]\s*['\"]?[^\s'\"]{8,}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
)


def load_config(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "s4_artifacts_v1":
        raise ValueError(f"Unsupported artifact schema in {path}")
    return data


def source_path(spec: dict[str, Any]) -> Path:
    if "source" in spec:
        path = ROOT / spec["source"]
    else:
        value = os.environ.get(spec["source_env"], spec.get("source_default", ""))
        if not value:
            raise ValueError(f"Set {spec['source_env']} for this artifact")
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = ROOT / path
    return path.resolve()


def excluded(relative: Path, names: set[str]) -> bool:
    return any(part in names for part in relative.parts)


def iter_files(source: Path, excludes: set[str]):
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if excluded(relative, excludes):
            continue
        if path.is_symlink():
            resolved = path.resolve()
            try:
                resolved.relative_to(source)
            except ValueError as exc:
                raise ValueError(f"Symlink escapes artifact root: {path} -> {resolved}") from exc
        if path.is_file():
            yield path, relative


def replacements(config: dict[str, Any]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for spec in config["artifacts"].values():
        src = source_path(spec)
        values.append((str(src), spec["destination"]))

    # Metadata can refer to the parent model/data/output roots instead of the
    # selected leaf. Longest matches must win.
    values.extend(
        [
            (str(ROOT / "s4_smolvla_isaaclab" / "models"), "models"),
            (str(ROOT / "s4_smolvla_isaaclab" / "datasets"), "datasets"),
            (str(ROOT / "s4_smolvla_isaaclab" / "outputs"), "policies"),
        ]
    )
    return sorted(set(values), key=lambda pair: len(pair[0]), reverse=True)


def sanitize_text(raw: bytes, mapping: list[tuple[str, str]], source: Path) -> bytes:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Expected UTF-8 metadata: {source}") from exc
    for old, new in mapping:
        text = text.replace(old, new)
    # Conversion reports may intentionally retain raw episode provenance. Keep
    # the relative session path while removing the publishing workstation user.
    text = re.sub(r"/(?:home|Users)/[^/]+/", "workstation/", text)
    if "/home/" in text or "/Users/" in text:
        raise ValueError(f"Unresolved workstation path in {source}")
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            raise ValueError(f"Possible credential in {source}: {pattern.pattern}")
    return text.encode("utf-8")


def copy_file(source: Path, target: Path, mapping: list[tuple[str, str]]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() in TEXT_SUFFIXES:
        target.write_bytes(sanitize_text(source.read_bytes(), mapping, source))
        shutil.copystat(source, target)
        return
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def artifact_plan(config: dict[str, Any], selected: list[str]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for name in selected:
        spec = config["artifacts"][name]
        source = source_path(spec)
        if not source.is_dir():
            raise FileNotFoundError(f"Missing source for {name}: {source}")
        excludes = set(spec.get("exclude", []))
        files = list(iter_files(source, excludes))
        plan.append(
            {
                "name": name,
                "source": str(source),
                "destination": spec["destination"],
                "files": len(files),
                "bytes": sum(path.stat().st_size for path, _ in files),
                "excluded_names": sorted(excludes),
            }
        )
    return plan


def write_repository_files(output: Path, config: dict[str, Any], plan: list[dict[str, Any]]) -> None:
    repo = config["repository"]
    readme = f"""---
license: Apache License 2.0
---

# Qiling S4 SmolVLA artifacts

Versioned runtime artifacts for the public S4 SmolVLA tutorial. This is an
artifact repository: model, policy, LeRobotDataset, and project asset
directories are kept in one ModelScope dataset repository and can be
downloaded selectively.

Repository: `{repo['repo_id']}`

The repository-level Apache-2.0 metadata covers project-authored manifests and
documentation. Third-party model cards and licenses remain applicable to their
respective files. Isaac Sim binaries and NVIDIA-provided Isaac assets are not
distributed here.

## Published directories

"""
    for item in plan:
        gib = item["bytes"] / (1024**3)
        readme += f"- `{item['destination']}` — {item['files']} files, {gib:.2f} GiB\n"
    readme += "\nSee `artifact-manifest.json` and `SHA256SUMS` for provenance and integrity.\n"
    (output / "README.md").write_text(readme, encoding="utf-8")
    public_plan = [
        {key: value for key, value in item.items() if key != "source"}
        for item in plan
    ]
    manifest = {
        "schema_version": "s4_modelscope_bundle_v1",
        "repository": repo,
        "artifacts": public_plan,
    }
    (output / "artifact-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    shutil.copy2(ROOT / "LICENSE", output / "LICENSE")
    shutil.copy2(ROOT / "NOTICE", output / "NOTICE")

    cards = {
        "datasets/lerobot_data/s4_drawer_insert_close_v4_12phase_serial_acquire/README.md": """---
license: Apache License 2.0
task_categories: [robotics]
---
# S4 drawer insert-and-close simulation dataset

LeRobotDataset recorded in Isaac Sim for the 12-phase bimanual drawer task.
The authoritative observation/action/language contract is `meta/s4_contract.json`.
""",
        "datasets/lerobot_data/s4_real_drawer_right_v1/README.md": """---
license: Apache License 2.0
task_categories: [robotics]
---
# S4 real-robot right drawer dataset

LeRobotDataset for right-arm drawer open/close. Camera observations are
published with the project owner's authorization. See `meta/s4_contract.json`
for the state, action, camera, timing, and language contract.
""",
        "policies/sim/drawer_insert_close_v4/350000/pretrained_model/README.md": """---
license: apache-2.0
library_name: lerobot
pipeline_tag: robotics
base_model: lerobot/smolvla_base
---
# S4 simulation policy — step 350000

SmolVLA policy selected for the public IsaacLab drawer tutorial. It requires
the matching `s4_drawer_insert_close_v4_12phase_serial_acquire` contract.
Only deployment files are included; optimizer and `training_state` are omitted.
""",
        "policies/real/drawer_right_v1/300000/pretrained_model/README.md": """---
license: apache-2.0
library_name: lerobot
pipeline_tag: robotics
base_model: lerobot/smolvla_base
---
# S4 real-robot policy — step 300000

SmolVLA deployment policy for the right-arm drawer open/close tutorial. The
required contract SHA256 is recorded in `deployment_manifest.json`.
Only deployment files are included; optimizer and `training_state` are omitted.
""",
        "assets/README.md": """# S4 project assets

This directory contains the S4 robot description/meshes and the small project
scene bundle used by the tutorial. The S4-authored material is released under
the repository Apache-2.0 license.

The LinkerHand O6 URDF and meshes originate from the Apache-2.0 licensed
`linker-bot/linkerhand-urdf` project; retain its copyright and license terms.

NVIDIA-provided Isaac Sim assets are deliberately not included. Users obtain
those assets from NVIDIA under the NVIDIA Isaac Sim Additional Software and
Materials License and mount or materialize them locally.
""",
    }
    for relative, content in cards.items():
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def write_checksums(output: Path) -> None:
    checksum_path = output / "SHA256SUMS"
    rows: list[str] = []
    for path in sorted(output.rglob("*")):
        if not path.is_file() or path == checksum_path:
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
        rows.append(f"{digest.hexdigest()}  {path.relative_to(output).as_posix()}")
    checksum_path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--artifact", action="append", dest="artifacts")
    parser.add_argument("--materialize", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    selected = args.artifacts or list(config["artifacts"])
    unknown = sorted(set(selected) - set(config["artifacts"]))
    if unknown:
        raise ValueError(f"Unknown artifacts: {', '.join(unknown)}")
    plan = artifact_plan(config, selected)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if not args.materialize:
        print("Plan only. Re-run with --materialize after review.", file=sys.stderr)
        return 0

    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty staging directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    mapping = replacements(config)
    for name in selected:
        spec = config["artifacts"][name]
        source = source_path(spec)
        destination = output / spec["destination"]
        excludes = set(spec.get("exclude", []))
        for path, relative in iter_files(source, excludes):
            copy_file(path, destination / relative, mapping)
    write_repository_files(output, config, plan)
    write_checksums(output)
    print(f"Materialized verified upload tree: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
