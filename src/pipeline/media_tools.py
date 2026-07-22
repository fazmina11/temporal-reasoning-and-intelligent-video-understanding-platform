from __future__ import annotations

import os
import shutil
from pathlib import Path


class MediaToolError(RuntimeError):
    """Raised when a configured FFmpeg executable cannot be used."""


def resolve_media_tool(name: str) -> Path | None:
    """Resolve ffmpeg/ffprobe from explicit configuration or the system PATH."""
    executable_name = f"{name}.exe" if os.name == "nt" else name
    explicit_path = os.getenv(f"{name.upper()}_PATH")
    bin_dir = os.getenv("FFMPEG_BIN_DIR")

    configured_candidates: list[Path] = []
    if explicit_path:
        configured_candidates.append(Path(explicit_path).expanduser())
    if bin_dir:
        configured_candidates.append(Path(bin_dir).expanduser() / executable_name)

    for candidate in configured_candidates:
        if candidate.is_file():
            return candidate.resolve()
        raise MediaToolError(
            f"Configured {name} executable does not exist: {candidate}"
        )

    discovered = shutil.which(name)
    if discovered:
        return Path(discovered).resolve()

    # WinGet sometimes updates the user PATH after the current process starts.
    # This fallback lets an already-running API discover a standard Gyan install.
    if os.name == "nt":
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            packages_dir = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
            if packages_dir.is_dir():
                matches = sorted(
                    packages_dir.glob(f"Gyan.FFmpeg_*/*/bin/{executable_name}"),
                    reverse=True,
                )
                if matches:
                    return matches[0].resolve()

    return None
