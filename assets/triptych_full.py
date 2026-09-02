#!/usr/bin/env python3
"""Triptych full pipeline: render → rename → gofile → Telegram.

Run after `triptych-video-pipeline` skill is installed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_paths import OUT, find_bgm, probe_duration  # noqa: E402


def run_ffmpeg(args: list[str], desc: str) -> bool:
    print(f"  {desc}")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("  ✗ ffmpeg 失败:")
        for line in (r.stderr or "unknown").strip().splitlines()[-6:]:
            print(f"    {line}")
        return False
    return True


def upload_gofile(path: Path) -> str | None:
    print("  上传到 gofile.io...")
    try:
        r = subprocess.run(["curl", "-s", "--max-time", "30",
                            "https://api.gofile.io/servers"],
                           capture_output=True, text=True, timeout=60)
        servers = json.loads(r.stdout).get("data", {}).get("servers", [])
        server = servers[0]["name"] if servers else "store-eu-par-4"
    except Exception:
        server = "store-eu-par-4"
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "1800", "-F", f"file=@{path}",
             f"https://{server}.gofile.io/contents/uploadfile"],
            capture_output=True, text=True, timeout=1900)
        url = json.loads(r.stdout).get("data", {}).get("downloadPage", "")
        if url:
            print(f"  ✓ {url}")
            return url
    except Exception as e:
        print(f"  ✗ 上传出错: {e}")
    print("  ✗ 上传失败")
    return None


def send_telegram(cover: Path, video_name: str, gofile_url: str, caption: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",")[0].strip()
    if not token or not chat_id:
        print("  ⚠ TELEGRAM_BOT_TOKEN 或 TELEGRAM_ALLOWED_USERS 未设置，跳过发送")
        return False
    print(f"  发送到 Telegram (chat_id={chat_id})...")
    r = subprocess.run([
        "curl", "-s", "-X", "POST",
        f"https://api.telegram.org/bot{token}/sendPhoto",
        "-F", f"chat_id={chat_id}",
        "-F", f"photo=@{cover}",
        "-F", f"caption={caption}",
    ], capture_output=True, text=True, timeout=60)
    if r.returncode == 0 and json.loads(r.stdout).get("ok"):
        print("  ✓ Telegram 发送成功")
        return True
    print(f"  ✗ Telegram 发送失败: {r.stdout}")
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Triptych full pipeline")
    ap.add_argument("video", help="源视频")
    ap.add_argument("--outdir", default=None, help="输出目录(默认 out/)")

    c = ap.add_argument_group("封面文案")
    c.add_argument("--title", required=True, help="中文大标题(两字最佳)")
    c.add_argument("--en", required=True, help="英文副标")
    c.add_argument("--kicker", default="LOOP · SERIES")
    c.add_argument("--tag", default="", help="中文 tagline")
    c.add_argument("--foot", default="for you", help="页脚英文小字")
    c.add_argument("--theme", choices=["cool", "warm"], default="warm")
    c.add_argument("--hero-at", type=float, default=0.0)
    c.add_argument("--yoff", type=float, default=-0.02)

    t = ap.add_argument_group("时长与淡入淡出")
    t.add_argument("--intro", type=float, default=3.0)
    t.add_argument("--fade-in", type=float, default=1.0)
    t.add_argument("--fade-out", type=float, default=1.5)
    t.add_argument("--afade-in", type=float, default=2.0)
    t.add_argument("--afade-out", type=float, default=3.0)
    t.add_argument("--duration", type=float, default=None, help="冒烟测试用总时长(秒)")

    ap.add_argument("--no-upload", action="store_true", help="不上传 gofile")
    ap.add_argument("--no-notify", action="store_true", help="不发 Telegram")
    ap.add_argument("--keep-temp", action="store_true", help="保留中间文件")
    args = ap.parse_args()

    outdir = Path(args.outdir).resolve() if args.outdir else OUT
    outdir.mkdir(parents=True, exist_ok=True)

    # 1. Run auto_triptych.py
    auto_script = Path(__file__).resolve().parent / "auto_triptych.py"
    cmd = [
        sys.executable, str(auto_script), args.video,
        "--cover-title", args.title,
        "--cover-en", args.en,
        "--cover-kicker", args.kicker,
        "--cover-tag", args.tag,
        "--cover-foot", args.foot,
        "--theme", args.theme,
        "--hero-at", str(args.hero_at),
        "--yoff", str(args.yoff),
        "--intro", str(args.intro),
        "--fade-in", str(args.fade_in),
        "--fade-out", str(args.fade_out),
        "--afade-in", str(args.afade_in),
        "--afade-out", str(args.afade_out),
        "--outdir", str(outdir),
    ]
    if args.duration:
        cmd += ["--duration", str(args.duration)]
    if args.keep_temp:
        cmd.append("--keep-temp")

    print("=" * 60)
    print("Triptych Full Pipeline")
    print("=" * 60)
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit(1)

    # 2. Find and rename outputs
    stem = Path(args.video).stem
    base = f"{stem}_final"
    final_src = outdir / f"{base}.mp4"
    cover_png_src = outdir / f"cover_{stem}.png"
    cover_jpg_src = outdir / f"cover_{stem}.jpg"

    final_name = f"{args.title}·{args.en}.mp4"
    cover_png_name = f"{args.title}·{args.en}.png"
    cover_jpg_name = f"{args.title}·{args.en}.jpg"

    final_dst = outdir / final_name
    cover_png_dst = outdir / cover_png_name
    cover_jpg_dst = outdir / cover_jpg_name

    for src, dst in [(final_src, final_dst), (cover_png_src, cover_png_dst), (cover_jpg_src, cover_jpg_dst)]:
        if src.exists():
            src.rename(dst)
            print(f"  重命名: {src.name} → {dst.name}")

    # 3. Upload to gofile
    gofile_url = None
    if not args.no_upload and final_dst.exists():
        gofile_url = upload_gofile(final_dst)

    # 4. Send to Telegram
    if not args.no_notify and gofile_url and cover_jpg_dst.exists():
        caption = f"{args.title}·{args.en}\n\ngofile: {gofile_url}\n\n封面: {cover_jpg_name}\n视频: {final_name} ({final_dst.stat().st_size / 1024 / 1024:.0f} MB, {probe_duration(find_bgm()):.1f}s)\n\n系列三联屏，BGM: Runway-Dreams (Chill Pop)，{args.theme} 主题"
        send_telegram(cover_jpg_dst, final_name, gofile_url, caption)

    print("\n" + "=" * 60)
    print("✓ 全流程完成")
    print("=" * 60)
    print(f"视频: {final_dst}")
    print(f"封面: {cover_png_dst} / {cover_jpg_dst}")
    if gofile_url:
        print(f"gofile: {gofile_url}")
    print("=" * 60)


if __name__ == "__main__":
    main()