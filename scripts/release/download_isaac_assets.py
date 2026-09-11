#!/usr/bin/env python3
"""Download the locked Isaac Sim 5.1 asset subset directly from NVIDIA."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCK = PROJECT_ROOT / "release" / "isaac_assets_5.1.lock.json"
DEFAULT_DESTINATION = PROJECT_ROOT / "s4_smolvla_isaaclab" / "local_assets" / "isaac" / "5.1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid(path: Path, item: dict[str, object]) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == item["size"]
        and sha256(path) == item["sha256"]
    )


def download_one(
    base_url: str,
    destination: Path,
    item: dict[str, object],
    retries: int,
) -> tuple[str, str]:
    relative = Path(str(item["path"]))
    target = destination / relative
    if valid(target, item):
        return "cached", relative.as_posix()

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".part")
    source = urllib.parse.quote(str(item.get("source", item["path"])), safe="/")
    url = f"{base_url.rstrip('/')}/{source}"
    headers = {"User-Agent": "s4-smolvla-asset-downloader/1"}
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=300) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            if not valid(temporary, item):
                raise OSError(f"size or SHA256 mismatch: {relative}")
            os.replace(temporary, target)
            return "downloaded", relative.as_posix()
        except (OSError, urllib.error.URLError) as error:
            last_error = error
            temporary.unlink(missing_ok=True)
            if attempt < retries:
                time.sleep(min(2**attempt, 20))
    raise RuntimeError(f"failed after {retries} attempts: {url}: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--workers", type=int, default=int(os.environ.get("S4_ISAAC_DOWNLOAD_WORKERS", "6")))
    parser.add_argument("--retries", type=int, default=8)
    args = parser.parse_args()
    if args.workers < 1 or args.retries < 1:
        parser.error("--workers and --retries must be positive")

    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    destination = args.destination.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    files = lock["files"]
    print(
        f"[ISAAC-ASSETS] NVIDIA direct download: files={len(files)} "
        f"size={lock['total_bytes'] / (1024**2):.1f} MiB destination={destination}"
    )

    counts = {"cached": 0, "downloaded": 0}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(download_one, lock["base_url"], destination, item, args.retries)
            for item in files
        ]
        for index, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            status, relative = future.result()
            counts[status] += 1
            if status == "downloaded" or index == len(futures) or index % 25 == 0:
                print(f"[ISAAC-ASSETS] {index}/{len(futures)} {status}: {relative}")

    manifest = {
        "format": "s4-local-isaac-assets-v1",
        "isaac_sim_asset_version": lock["isaac_sim_version"],
        "source": lock["base_url"],
        "lock_sha256": sha256(args.lock),
        "files": [
            {key: item[key] for key in ("path", "size", "sha256")}
            for item in files
        ],
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"[ISAAC-ASSETS] verified={len(files)} downloaded={counts['downloaded']} "
        f"cached={counts['cached']}"
    )


if __name__ == "__main__":
    main()
