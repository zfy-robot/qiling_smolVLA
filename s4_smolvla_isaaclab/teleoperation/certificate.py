#!/usr/bin/env python3
"""Generate a local self-signed HTTPS certificate with the workstation IP SAN."""

from __future__ import annotations

import argparse
import ipaddress
import socket
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = PROJECT_ROOT / ".local" / "teleoperation"


def detect_lan_ip() -> str:
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        return str(sock.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        if sock is not None:
            sock.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the HTTPS certificate required by Quest WebXR.")
    parser.add_argument("--ip", default=detect_lan_ip(), help="Workstation LAN IP used by Quest 3.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    ipaddress.ip_address(args.ip)
    output_dir = args.output_dir.resolve()
    cert = output_dir / "cert.pem"
    key = output_dir / "key.pem"
    if (cert.exists() or key.exists()) and not args.overwrite:
        print(f"Certificate already exists: {cert}")
        print("Use --overwrite to replace it.")
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-sha256",
            "-nodes",
            "-days",
            str(max(args.days, 1)),
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-subj",
            "/CN=S4 Quest Teleoperation",
            "-addext",
            f"subjectAltName=IP:{args.ip},IP:127.0.0.1,DNS:localhost",
        ],
        check=True,
    )
    key.chmod(0o600)
    print(f"Generated certificate: {cert}")
    print(f"Generated private key: {key}")
    print(f"Quest URL: https://{args.ip}:8443")
    print("Open this URL in Quest Browser and accept the certificate warning once.")


if __name__ == "__main__":
    main()
