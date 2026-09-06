#!/usr/bin/env python3
"""Shared paths + constants for the triptych video pipeline.

Everything resolves from this file's own location, so the pipeline keeps
working if the repo is moved or renamed (the old scripts hardcoded
/workspaces/hermes-agent/assets and broke when the checkout became
/workspaces/hermes).
"""
from __future__ import annotations

import subprocess
from fractions import Fraction
from pathlib import Path

# assets/ -> repo root
ASSETS = Path(__file__).resolve().parent
REPO = ASSETS.parent

# Media directories as laid out after the 2026-08 restore.
VIDEOS = REPO / "videos"            # finished v1..v15, t3, triptych_loop*, 勾勒_final
EXTRA = REPO / "extra"              # 勾勒.mp4 source + "new videos"/v17..v21 finals
NEW_VIDEOS = EXTRA / "new videos"
V16 = REPO / "v16"
COVERS = REPO / "covers"
BGM_DIR = REPO / "bgm"

# Where new renders land (kept out of the finished-work dirs).
OUT = REPO / "out"

# Noto CJK — installed via `apt-get install fonts-noto-cjk`.
SANS_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
SERIF_BOLD = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"

# Render settings the whole series was cut with.
CRF = 20
PRESET = "medium"
PIX_FMT = "yuv420p"


def find_bgm() -> Path:
    """The series BGM. Falls back to any mp3 in bgm/ if the original is gone."""
    mp3s = sorted(BGM_DIR.glob("*.mp3"))
    if not mp3s:
        raise FileNotFoundError(f"no .mp3 found in {BGM_DIR}")
    for m in mp3s:
        if "Runway-Dreams" in m.name:
            return m
    return mp3s[0]


def probe_duration(path: Path | str) -> float:
    """Exact duration in seconds. The old scripts hardcoded 172.486531."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def probe_video(path: Path | str) -> dict:
    """Width/height/fps/codec/duration for a video file.

    fps is parsed with Fraction instead of eval() — ffprobe reports
    avg_frame_rate as "0/0" for some streams, which crashed the old
    eval-based version with ZeroDivisionError.
    """
    import json

    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(out.stdout)
    vs = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if vs is None:
        raise ValueError(f"no video stream in {path}")

    raw_fps = vs.get("avg_frame_rate") or "0/0"
    try:
        fps = float(Fraction(raw_fps))
    except (ZeroDivisionError, ValueError):
        fps = 0.0

    return {
        "width": int(vs["width"]),
        "height": int(vs["height"]),
        "duration": float(data["format"]["duration"]),
        "fps": fps,
        "codec": vs["codec_name"],
    }


def resolve_source(name: str) -> Path:
    """Find a source video by bare name across the restored media dirs."""
    p = Path(name)
    if p.is_absolute() and p.exists():
        return p

    candidates = [
        Path.cwd() / name,
        NEW_VIDEOS / name,
        EXTRA / name,
        VIDEOS / name,
        V16 / name,
        OUT / name,
        ASSETS / name,
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        f"source video not found: {name}\nlooked in: "
        + ", ".join(str(c.parent) for c in candidates)
    )
