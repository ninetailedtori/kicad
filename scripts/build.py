#!/usr/bin/env python3
"""Build script for our Catppuccin KiCad theme!"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import NotRequired, TypedDict

from packaging.version import Version as SemVer


# ============================================================================
# TYPING
# ============================================================================


@dataclass(frozen=True)
class Checksum:
    """Immutable checksum result."""

    hex: str

    def short(self, p_len: int = 16) -> str:
        """Return truncated hex."""
        return self.hex[:p_len]


class VersionEntry(TypedDict):
    """Data holding a single version's release."""

    checksum: Checksum
    download_size: int
    install_size: int
    timestamp: int
    time_utc: str
    semver: SemVer
    status: str
    platforms: list[str]
    kicad_version: str
    kicad_version_max: NotRequired[str]
    download_url: NotRequired[str]
    download_sha256: NotRequired[str]


class Package(TypedDict):
    """packages.json entry."""

    identifier: str
    name: str
    versions: list[VersionEntry]


class Repository(TypedDict):
    """repository.json entry."""

    url: str
    sha256: Checksum
    timestamp: int
    time_utc: str


# ============================================================================
# HELPERS
# ============================================================================


def _get_semver() -> SemVer:
    """Extract version from pyproject.toml."""
    l_proj = Path("pyproject.toml")
    l_content = l_proj.read_text()
    l_match = re.search(r'version\s*=\s*"([^"]+)"', l_content)
    if not l_match:
        raise ValueError("Version not found in pyproject.toml")
    return SemVer(l_match.group(1))


def _get_checksum(p_file: Path) -> Checksum:
    """Compute SHA256 checksum of a file."""
    l_hash = hashlib.sha256()
    with open(p_file, "rb") as f:
        while i_chunk := f.read(4096):
            l_hash.update(i_chunk)
    return Checksum(l_hash.hexdigest())


def _get_zip_size(p_zip: Path) -> int:
    """Get total uncompressed size of zip contents."""
    with zipfile.ZipFile(p_zip, "r") as l_zip:
        return sum(info.file_size for info in l_zip.infolist())


def _build_zip(p_zip: Path) -> None:
    """Create zip archive."""
    with zipfile.ZipFile(p_zip, "w", zipfile.ZIP_DEFLATED) as l_zip:
        for i_item in ["colors", "resources", "LICENSE", "metadata.json"]:
            l_path = Path(i_item)
            if l_path.is_file():
                l_zip.write(l_path, arcname=l_path.name)
            elif l_path.is_dir():
                for i_file in l_path.rglob("*"):
                    if i_file.is_file():
                        l_zip.write(i_file, arcname=i_file.relative_to("."))


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


def _update_version(
    p_updates: list[tuple[list[VersionEntry], VersionEntry]],
) -> None:
    """Update or insert version in each list."""
    for i_list, i_new in p_updates:
        l_cur = next(
            (
                i_idx
                for i_idx, i_ver in enumerate(i_list)
                if i_ver["semver"] == i_new["semver"]
            ),
            None,
        )
        if l_cur is not None:
            i_list[l_cur] = i_new
        else:
            i_list.insert(0, i_new)


# ============================================================================
# MAIN
# ============================================================================


def main() -> int:
    semver = _get_semver()
    zip_filename = Path(f"catppuccin-kicad-v{semver}.zip")

    print("Running whiskers...")
    if (
        subprocess.run(
            ["whiskers", "scripts/kicad.tera"], check=False
        ).returncode
        != 0
    ):
        print("Error: whiskers command failed", file=sys.stderr)
        return 1

    print(f"Creating {zip_filename}...")
    _build_zip(zip_filename)

    mdata, pdata, repo = _load_json(
        {
            "metadata": Path("metadata.json"),
            "packages": Path("packages.json"),
            "repo": Path("repository.json"),
        }
    )

    # Build version metadata
    l_checksum = _get_checksum(zip_filename)
    l_now = datetime.now(timezone.utc)
    version: VersionEntry = {
        "semver": semver,
        "status": "stable",
        "platforms": ["windows", "macos", "linux"],
        "kicad_version": "7.0",
        "checksum": l_checksum,
        "download_size": zip_filename.stat().st_size,
        "install_size": _get_zip_size(zip_filename),
        "timestamp": int(l_now.timestamp()),
        "time_utc": l_now.strftime("%Y-%m-%d %H:%M:%S"),
        "download_url": f"https://github.com/catppuccin/kicad/releases/download/v{semver}/{zip_filename.name}",
        "download_sha256": l_checksum.hex,
    }

    _update_version(
        [
            (mdata["versions"], version),
            (pdata["packages"][0]["versions"], version),
        ]
    )

    # Update repository metadata
    packages_json_str = json.dumps(pdata, indent=2)
    repo["packages"] = {
        "url": "https://raw.githubusercontent.com/catppuccin/kicad/main/packages.json",
        "sha256": hashlib.sha256(packages_json_str.encode()).hexdigest(),
        "update_timestamp": version["timestamp"],
        "update_time_utc": version["time_utc"],
    }

    _save_json(
        {
            Path("metadata.json"): mdata,
            Path("packages.json"): pdata,
            Path("repository.json"): repo,
        }
    )

    print(f":3 Updated metadata for v{semver}")
    print(f"  SHA256: {version['download_sha256']}")
    print(f"  Download: {version['download_size']:,} bytes")
    print(f"  Installed: {version['install_size']:,} bytes")

    return 0


if __name__ == "__main__":
    sys.exit(main())
