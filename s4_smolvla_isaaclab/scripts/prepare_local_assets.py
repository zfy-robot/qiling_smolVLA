#!/usr/bin/env python3
"""Copy the project's NVIDIA USD dependency closure into ignored local_assets.

Run through ``bash run.sh prepare-assets`` so the matching Isaac Sim USD
libraries are placed on Python's library paths. The destination intentionally
remains outside Git and can be archived/distributed separately by the user.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from pxr import UsdUtils


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(os.environ.get("ISAAC_ASSET_ROOT", Path.home() / "isaacsim_assets/Assets/Isaac/5.1"))
DEFAULT_DESTINATION = PROJECT_ROOT / "local_assets" / "isaac" / "5.1"
ENTRY_ASSETS = (
    "Isaac/Environments/Simple_Warehouse/warehouse.usd",
    "Isaac/Props/Sektion_Cabinet/sektion_cabinet_instanceable.usd",
    "Isaac/Props/YCB/Axis_Aligned/005_tomato_soup_can.usd",
    "Isaac/Props/YCB/Axis_Aligned/002_master_chef_can.usd",
    "Isaac/Props/YCB/Axis_Aligned/006_mustard_bottle.usd",
    "Isaac/Props/YCB/Axis_Aligned/021_bleach_cleanser.usd",
    "Isaac/Props/PackingTable/packing_table.usd",
    # IsaacLab visualization helpers resolve these through the global asset
    # root at runtime; they are not reachable from the task USD references.
    "Isaac/Props/UIElements/frame_prim.usd",
    "Isaac/Props/UIElements/arrow_x.usd",
)
# USD's dependency collector does not parse relative imports inside MDL source.
# Without these two modules the warehouse materials compile as red error shaders.
AUXILIARY_FILES = (
    "Isaac/Environments/Simple_Warehouse/Materials/OmniUe4Base.mdl",
    "Isaac/Environments/Simple_Warehouse/Materials/OmniUe4Function.mdl",
)
BUILTIN_UNRESOLVED = {"OmniPBR.mdl"}
MDL_RESOURCE_PATTERN = re.compile(
    r'''["']([^"']+\.(?:png|jpg|jpeg|exr|hdr|tif|tiff|tx|ies))["']''',
    re.IGNORECASE,
)


def _layer_path(layer) -> str:
    return str(getattr(layer, "realPath", "") or getattr(layer, "identifier", ""))


def dependency_closure(source_root: Path) -> tuple[list[Path], list[str]]:
    paths: set[Path] = set()
    unresolved: set[str] = set()
    for relative in ENTRY_ASSETS:
        entry = source_root / relative
        if not entry.is_file():
            raise FileNotFoundError(f"Missing source asset: {entry}")
        layers, files, missing = UsdUtils.ComputeAllDependencies(str(entry))
        paths.update(Path(path) for path in (_layer_path(layer) for layer in layers) if path)
        paths.update(Path(path) for path in files)
        unresolved.update(str(path) for path in missing)

    outside = [path for path in paths if source_root not in path.resolve().parents]
    if outside:
        formatted = "\n  ".join(str(path) for path in sorted(outside))
        raise RuntimeError(f"USD dependencies escaped source root {source_root}:\n  {formatted}")
    existing = sorted(path.resolve() for path in paths if path.is_file())
    return existing, sorted(unresolved)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def recover_missing_source_assets(
    source_root: Path,
    unresolved: list[str],
) -> tuple[list[tuple[Path, Path]], list[str]]:
    """Find source-shipped files whose USD reference points at the wrong folder.

    Isaac 5.1's PackingTable references several corrugated-box textures one
    directory too high. The files are still present elsewhere under the same
    asset tree. Recovery is accepted only when every same-name candidate has
    identical content, so this cannot silently substitute a different texture.
    """
    missing_paths = [Path(value) for value in unresolved if Path(value).is_absolute()]
    wanted_names = {path.name for path in missing_paths}
    candidates: dict[str, list[Path]] = {name: [] for name in wanted_names}
    for path in source_root.rglob("*"):
        if path.is_file() and path.name in wanted_names and ".thumbs" not in path.parts:
            candidates[path.name].append(path.resolve())

    recovered: list[tuple[Path, Path]] = []
    still_missing: list[str] = []
    for missing in missing_paths:
        matches = candidates.get(missing.name, [])
        if not matches:
            still_missing.append(str(missing))
            continue
        hashes = {sha256(path) for path in matches}
        if len(hashes) != 1:
            raise RuntimeError(
                f"Ambiguous recovery for {missing}: same-name source files have different contents"
            )
        source = min(matches, key=lambda path: (len(path.parts), len(str(path))))
        recovered.append((source, missing.resolve().relative_to(source_root)))
    return recovered, still_missing


def mdl_resource_files(source_root: Path, sources: list[Path]) -> list[Path]:
    """Resolve texture/light-profile files referenced inside copied MDL code."""
    resources: set[Path] = set()
    unresolved: list[str] = []
    for source in sources:
        if source.suffix.lower() != ".mdl":
            continue
        text = source.read_text(encoding="utf-8-sig", errors="replace")
        for value in MDL_RESOURCE_PATTERN.findall(text):
            # MDL resources beginning with / are module-search paths and are
            # provided by Isaac Sim. The warehouse files use relative paths.
            if value.startswith("/"):
                continue
            resource = (source.parent / value).resolve()
            if resource.is_file():
                if source_root not in resource.parents:
                    raise RuntimeError(f"MDL resource escaped source root: {resource}")
                resources.add(resource)
            else:
                unresolved.append(f"{source}: {value}")
    if unresolved:
        raise FileNotFoundError("Missing MDL resource(s):\n  " + "\n  ".join(sorted(unresolved)))
    return sorted(resources)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--verify", action="store_true", help="Hash source and destination files after copying.")
    args = parser.parse_args()

    source_root = args.source_root.expanduser().resolve()
    destination = args.destination.expanduser().resolve()
    files, unresolved = dependency_closure(source_root)
    recovered, unrecovered_source = recover_missing_source_assets(source_root, unresolved)
    destination.mkdir(parents=True, exist_ok=True)

    copy_items = [(path, path.relative_to(source_root), False) for path in files]
    copy_items.extend((source, relative, True) for source, relative in recovered)
    copied_relatives = {relative for _, relative, _ in copy_items}
    for relative_text in AUXILIARY_FILES:
        relative = Path(relative_text)
        source = source_root / relative
        if not source.is_file():
            raise FileNotFoundError(f"Missing implicit runtime asset: {source}")
        if relative not in copied_relatives:
            copy_items.append((source.resolve(), relative, False))
            copied_relatives.add(relative)
    mdl_resources = mdl_resource_files(source_root, [source for source, _, _ in copy_items])
    for source in mdl_resources:
        relative = source.relative_to(source_root)
        if relative not in copied_relatives:
            copy_items.append((source, relative, False))
            copied_relatives.add(relative)
    total_bytes = sum(source.stat().st_size for source, _, _ in copy_items)
    print(f"[ASSETS] source={source_root}")
    print(f"[ASSETS] destination={destination}")
    print(
        f"[ASSETS] dependency_files={len(files)} recovered_textures={len(recovered)} "
        f"mdl_resources={len(mdl_resources)} size={total_bytes / (1024**2):.1f} MiB"
    )

    manifest_files: list[dict[str, object]] = []
    for index, (source, relative, was_recovered) in enumerate(copy_items, start=1):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        item: dict[str, object] = {"path": relative.as_posix(), "size": source.stat().st_size}
        if was_recovered:
            item["recovered_from"] = source.relative_to(source_root).as_posix()
        if args.verify:
            source_hash = sha256(source)
            if sha256(target) != source_hash:
                raise OSError(f"Checksum mismatch after copying {relative}")
            item["sha256"] = source_hash
        manifest_files.append(item)
        if index == 1 or index % 25 == 0 or index == len(copy_items):
            print(f"[ASSETS] copied {index}/{len(copy_items)}")

    unresolved_external = [
        value
        for value in unresolved
        if Path(value).name not in BUILTIN_UNRESOLVED and not Path(value).is_absolute()
    ]
    destination_unresolved: list[str] = []
    if args.verify:
        _, destination_unresolved = dependency_closure(destination)
        unexpected_destination = [
            value for value in destination_unresolved if Path(value).name not in BUILTIN_UNRESOLVED
        ]
        if unexpected_destination:
            raise RuntimeError(
                f"Packaged USD dependency closure is incomplete: {unexpected_destination}"
            )
        print("[ASSETS] packaged USD dependency closure verified")
    manifest = {
        "format": "s4-local-isaac-assets-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "entry_assets": list(ENTRY_ASSETS),
        "auxiliary_files": list(AUXILIARY_FILES),
        "mdl_resource_files": [path.relative_to(source_root).as_posix() for path in mdl_resources],
        "files": manifest_files,
        "unresolved_builtin": sorted(value for value in unresolved if Path(value).name in BUILTIN_UNRESOLVED),
        "unresolved_source_assets": unrecovered_source,
        "unresolved_external": unresolved_external,
        "packaged_unresolved_builtin": sorted(
            value for value in destination_unresolved if Path(value).name in BUILTIN_UNRESOLVED
        ),
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[ASSETS] manifest={manifest_path}")
    if unresolved_external:
        raise RuntimeError(f"Unexpected unresolved dependencies: {unresolved_external}")
    if unrecovered_source:
        raise RuntimeError(f"Unresolved source assets: {unrecovered_source}")


if __name__ == "__main__":
    main()
