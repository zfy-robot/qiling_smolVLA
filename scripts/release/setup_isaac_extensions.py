#!/usr/bin/env python3
"""Download, verify and install NVIDIA Kit extensions into the local cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCK = ROOT / "release" / "isaac_extensions_5.1.lock.json"
DEFAULT_DOWNLOAD_DIR = ROOT / ".s4" / "vendor-downloads"
DEFAULT_CACHE_ROOT = ROOT / ".s4" / "cache" / "home" / ".local" / "share" / "ov" / "data" / "exts" / "v2"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_archive(path: Path, spec: dict[str, object]) -> None:
    expected_size = int(spec["size"])
    actual_size = path.stat().st_size
    if actual_size != expected_size:
        raise ValueError(f"Archive size mismatch for {path}: expected={expected_size} actual={actual_size}")
    actual_sha = sha256_file(path)
    if actual_sha != spec["sha256"]:
        raise ValueError(f"Archive SHA256 mismatch for {path}: {actual_sha}")
    with zipfile.ZipFile(path) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise ValueError(f"Corrupt ZIP member in {path}: {bad_member}")


def safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    for member in members:
        relative = PurePosixPath(member.filename)
        mode = member.external_attr >> 16
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe ZIP path: {member.filename}")
        if stat.S_ISLNK(mode):
            link_target = archive.read(member).decode("utf-8")
            target_path = PurePosixPath(link_target)
            if target_path.is_absolute() or ".." in target_path.parts:
                raise ValueError(f"Unsafe ZIP symlink: {member.filename} -> {link_target}")
    return members


def extract_archive(archive: zipfile.ZipFile, destination: Path) -> None:
    for member in safe_members(archive):
        relative = PurePosixPath(member.filename)
        output = destination.joinpath(*relative.parts)
        mode = member.external_attr >> 16
        if member.is_dir():
            output.mkdir(parents=True, exist_ok=True)
            continue
        output.parent.mkdir(parents=True, exist_ok=True)
        if stat.S_ISLNK(mode):
            output.symlink_to(archive.read(member).decode("utf-8"))
            continue
        with archive.open(member) as source, output.open("wb") as target_stream:
            shutil.copyfileobj(source, target_stream)
        if stat.S_IMODE(mode):
            output.chmod(stat.S_IMODE(mode))


def verify_installed(archive_path: Path, target: Path, spec: dict[str, object]) -> int:
    checked = 0
    with zipfile.ZipFile(archive_path) as archive:
        for member in safe_members(archive):
            if member.is_dir():
                continue
            installed = target.joinpath(*PurePosixPath(member.filename).parts)
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                expected_target = archive.read(member).decode("utf-8")
                if not installed.is_symlink() or os.readlink(installed) != expected_target:
                    raise ValueError(f"Installed extension symlink differs: {installed}")
                checked += 1
                continue
            if not installed.is_file() or installed.stat().st_size != member.file_size:
                raise ValueError(f"Installed extension file is missing or has wrong size: {installed}")
            digest = hashlib.sha256()
            with archive.open(member) as source, installed.open("rb") as actual:
                while True:
                    expected_chunk = source.read(1024 * 1024)
                    actual_chunk = actual.read(1024 * 1024)
                    if expected_chunk != actual_chunk:
                        raise ValueError(f"Installed extension differs from locked ZIP: {installed}")
                    if not expected_chunk:
                        break
                    digest.update(expected_chunk)
            checked += 1
    extension_toml = target / "config" / "extension.toml"
    if sha256_file(extension_toml) != spec["extension_toml_sha256"]:
        raise ValueError(f"extension.toml SHA256 mismatch: {extension_toml}")
    license_path = target / str(spec["license_path"])
    if not license_path.is_file():
        raise ValueError(f"NVIDIA license file is missing: {license_path}")
    return checked


def download(archive_path: Path, url: str) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "curl",
            "--fail",
            "--location",
            "--http1.1",
            "--continue-at",
            "-",
            "--retry",
            "12",
            "--retry-all-errors",
            "--retry-delay",
            "5",
            "--connect-timeout",
            "30",
            "--output",
            str(archive_path),
            url,
        ],
        check=True,
    )


def install(archive_path: Path, target: Path, spec: dict[str, object]) -> int:
    if target.exists():
        return verify_installed(archive_path, target, spec)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        with zipfile.ZipFile(archive_path) as archive:
            extract_archive(archive, temporary)
        checked = verify_installed(archive_path, temporary, spec)
        os.replace(temporary, target)
        return checked
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--download-dir", type=Path, default=DEFAULT_DOWNLOAD_DIR)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--accept-nvidia-license", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not args.accept_nvidia_license:
        raise SystemExit(
            "NVIDIA extensions use NVIDIA license terms. Re-run with --accept-nvidia-license "
            "after reviewing the license/EULA."
        )

    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    if lock.get("schema_version") != "s4_isaac_extensions_v1":
        raise ValueError(f"Unsupported extension lock: {args.lock}")
    total_files = 0
    for spec in lock["extensions"]:
        archive_path = args.download_dir / spec["archive"]
        if not archive_path.is_file():
            if args.verify_only:
                raise FileNotFoundError(f"Locked archive is missing: {archive_path}")
            print(f"[DOWNLOAD] {spec['name']} <- {spec['url']}", flush=True)
            download(archive_path, spec["url"])
        validate_archive(archive_path, spec)
        target = args.cache_root / spec["directory"]
        checked = verify_installed(archive_path, target, spec) if args.verify_only else install(archive_path, target, spec)
        total_files += checked
        print(f"[OK] {spec['name']}: archive SHA256 and {checked} installed files", flush=True)
    print(f"[OK] NVIDIA Kit extension cache ready: extensions={len(lock['extensions'])} files={total_files}")
    print(args.cache_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
