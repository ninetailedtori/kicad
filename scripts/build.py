#!/usr/bin/env python3
"""Build script for our Catppuccin KiCad theme!"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import NotRequired, TypedDict
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from packaging.version import Version as SemVer


# ============================================================================
# TYPING
# ============================================================================


class VersionEntry(TypedDict):
    """Data holding a single version's release."""

    version: str
    status: str
    kicad_version: str
    kicad_version_max: NotRequired[str]
    platforms: list[str]
    download_url: str
    download_sha256: str
    download_size: int
    install_size: int


class Package(TypedDict):
    """packages.json entry."""

    identifier: str
    name: str
    versions: list[VersionEntry]


class Repository(TypedDict):
    """repository.json entry."""

    url: str
    sha256: str
    update_timestamp: int
    update_time_utc: str


# ============================================================================
# HELPERS
# ============================================================================


# Metadata
def _fetch_last_commit_date() -> tuple[int, int, int, int, int, int]:
    """Get the date of the last commit."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            capture_output=True,
            text=True,
            check=True,
        )
        timestamp = int(result.stdout.strip())
        dt = datetime.fromtimestamp(timestamp)
        return dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second
    except (subprocess.CalledProcessError, ValueError):
        return 2024, 1, 1, 0, 0, 0


def _fetch_semver() -> SemVer:
    """Extract version from pyproject.toml."""
    l_proj = Path("pyproject.toml")
    l_content = l_proj.read_text()
    l_match = re.search(r'version\s*=\s*"([^"]+)"', l_content)
    if not l_match:
        raise ValueError("Version not found in pyproject.toml")
    return SemVer(l_match.group(1))


def _calc_checksum(p_file: Path) -> str:
    """Compute SHA256 checksum of a file."""
    l_hash = hashlib.sha256()
    with open(p_file, "rb") as f:
        while i_chunk := f.read(4096):
            l_hash.update(i_chunk)
    return l_hash.hexdigest()


def _calc_archive_size(p_zip: Path) -> int:
    """Get total uncompressed size of zip contents."""
    with ZipFile(p_zip, "r") as l_zip:
        return sum(info.file_size for info in l_zip.infolist())


# Builders
def _build_archive(p_zip: Path) -> None:
    """Create zip archive with deterministic timestamps based on last commit."""

    fixed_date = _fetch_last_commit_date()
    with ZipFile(p_zip, "w", ZIP_DEFLATED) as l_zip:
        for i_item in ["colors", "resources", "LICENSE"]:
            l_path = Path(i_item)
            if l_path.is_file():
                l_info = ZipInfo(l_path.name, date_time=fixed_date)
                l_zip.writestr(l_info, l_path.read_bytes())
            elif l_path.is_dir():
                for i_file in l_path.rglob("*"):
                    if i_file.is_file():
                        l_archive = i_file.relative_to(".").as_posix()
                        l_info = ZipInfo(l_archive, date_time=fixed_date)
                        l_zip.writestr(l_info, i_file.read_bytes())


# JSON
def _load_json(p_files: dict[str, Path]) -> tuple[dict, dict, dict]:
    """Load multiple JSON files."""
    l_result = {}
    for i_key, i_file in p_files.items():
        if not i_file.exists():
            raise FileNotFoundError(f"Missing: {i_file}")
        l_result[i_key] = json.loads(i_file.read_text())

    return l_result["metadata"], l_result["packages"], l_result["repo"]


def _save_json(p_files: dict[Path, dict]) -> None:
    """Save JSON files."""
    for i_file, i_data in p_files.items():
        i_file.write_text(json.dumps(i_data, indent=2))


# ============================================================================
# MAIN
# ============================================================================


def main() -> int:
    version = _fetch_semver()
    zip_filename = Path(f"catppuccin-kicad-v{version}.zip")

    # Snapshot metadata before whiskers
    metadata_path = Path("metadata.json")
    old_metadata = metadata_path.read_text() if metadata_path.exists() else None

    print("Running whiskers...")
    if (
        subprocess.run(
            ["whiskers", "scripts/kicad.tera"], check=False
        ).returncode
        != 0
    ):
        print("Error: whiskers command failed", file=sys.stderr)
        return 1

    # Restore old metadata if whiskers didn't meaningfully change it
    new_metadata = metadata_path.read_text()
    if old_metadata and json.loads(old_metadata) == json.loads(new_metadata):
        metadata_path.write_text(old_metadata)

    print(f"Creating {zip_filename}...")
    _build_archive(zip_filename)

    mdata, pdata, rdata = _load_json(
        {
            "metadata": metadata_path,
            "packages": Path("packages.json"),
            "repo": Path("repository.json"),
        }
    )

    l_checksum = _calc_checksum(zip_filename)
    version_str = str(version)

    old_version = next(
        (
            v
            for v in pdata["packages"][0]["versions"]
            if v["version"] == version_str
        ),
        None,
    )
    if old_version and old_version["download_sha256"] == l_checksum:
        print(f"v{version} unchanged, skipping metadata update")
        return 0

    l_timestamp = datetime.now()
    entry: VersionEntry = {
        "version": version_str,
        "status": "stable",
        "kicad_version": "7.0",
        "platforms": ["windows", "macos", "linux"],
        "download_url": f"https://github.com/catppuccin/kicad/releases/download/v{version}/{zip_filename.name}",
        "download_sha256": l_checksum,
        "download_size": zip_filename.stat().st_size,
        "install_size": _calc_archive_size(zip_filename),
    }

    mdata["versions"] = [
        v for v in mdata["versions"] if v["version"] != version_str
    ]
    pdata["packages"][0]["versions"] = [
        v
        for v in pdata["packages"][0]["versions"]
        if v["version"] != version_str
    ]

    mdata["versions"].insert(
        0,
        {
            "version": entry["version"],
            "status": entry["status"],
            "kicad_version": entry["kicad_version"],
        },
    )
    pdata["packages"][0]["versions"].insert(0, entry)

    packages_json_str = json.dumps(pdata, indent=2)
    rdata["packages"] = {
        "url": "https://raw.githubusercontent.com/catppuccin/kicad/main/packages.json",
        "sha256": hashlib.sha256(packages_json_str.encode()).hexdigest(),
        "update_timestamp": int(l_timestamp.timestamp()),
        "update_time_utc": l_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
    }

    _save_json(
        {
            Path("metadata.json"): mdata,
            Path("packages.json"): pdata,
            Path("repository.json"): rdata,
        }
    )

    print(f":3 Updated metadata for v{version}")
    print(f"  Archive SHA256: {entry['download_sha256']}")
    print(f"  Archive size: {entry['download_size']:,} bytes")
    print(f"  Unpacked size: {entry['install_size']:,} bytes")

    return 0


if __name__ == "__main__":
    sys.exit(main())
