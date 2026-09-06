#!/usr/bin/env python3
"""全自动三联视频生成器 v4

v4 的三个改动:
  1. 片头卡 = 系列封面(从素材首帧生成),不再是 2 秒纯黑
  2. 视频淡入淡出 + 音频淡入淡出(v3 只有音频淡出)
  3. 三联主体时长 = BGM 时长 - 片头时长,总长精确等于 BGM

用法:
    python3 assets/auto_triptych.py <视频> \\
        --cover-title 流光 --cover-en RADIANCE \\
        --cover-kicker "COOL · DARK VIBES" \\
        --cover-tag "冷冽暗夜 · 光影流动" --cover-foot "from the dark" \\
        --theme cool

封面文案(--cover-*)由调用方撰写:先看素材首帧,再据画面内容写中英标题。
不传则回退到文件名,视觉效果会很差 —— 文案是这套封面的主体。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_paths import (  # noqa: E402
    CRF, OUT, PIX_FMT, PRESET, find_bgm, probe_duration, probe_video,
    resolve_source,
)
from make_series_cover import (  # noqa: E402
    THEMES, build as build_cover, hero_from_video, load_hero,
)

FONT_SERIF = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"


def detect_content_box(src: Path) -> tuple[int, int, int, int] | None:
    """用 cropdetect 找出素材的实际画面区域(去掉信箱/邮筒黑边)。

    竖版素材常被封装进 1920x1080 画布,两侧是纯黑。不去掉的话三联屏
    会把黑边当画面裁进去。返回 (w, h, x, y),检测不到返回 None。
    """
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-ss", "1", "-i", str(src),
         "-vf", "cropdetect=limit=24:round=2:reset=0", "-frames:v", "60",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    box = None
    for line in (r.stderr or "").splitlines():
        if "crop=" in line:
            box = line.rsplit("crop=", 1)[1].strip()
    if not box:
        return None
    try:
        w, h, x, y = (int(v) for v in box.split(":"))
    except ValueError:
        return None
    return (w, h, x, y) if w > 0 and h > 0 else None


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


def build_filter(info: dict, box: tuple[int, int, int, int] | None = None) -> str:
    """三联屏 filter_complex:竖条 → 640x1080 → split=3 → hstack=3。"""
    w, h = info["width"], info["height"]

    # 先去掉素材自带的黑边,再按去边后的真实画面判断横竖
    pre = ""
    if box and (box[0] != w or box[1] != h):
        bw, bh, bx, by = box
        pre = f"crop={bw}:{bh}:{bx}:{by},"
        print(f"  去黑边: {w}x{h} → {bw}x{bh} (偏移 {bx},{by})")
        w, h = bw, bh

    aspect = w / h
    if aspect > 1.3:                       # 横屏:居中裁竖条
        crop_w, crop_h = 598, 1080
        crop_x, crop_y = (w - crop_w) // 2, max(0, (h - crop_h) // 2)
    else:                                  # 竖屏:原样
        crop_w, crop_h, crop_x, crop_y = w, h, 0, 0

    scale_h = int(640 * crop_h / crop_w)
    chain = f"{pre}crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale=640:{scale_h}"
    if scale_h > 1080:
        chain += f",crop=640:1080:0:{(scale_h - 1080) // 2}"
    elif scale_h < 1080:
        chain += f",pad=640:1080:0:{(1080 - scale_h) // 2}"

    print(f"  画面 {w}x{h} (比例 {aspect:.2f}) → 单格 640x1080 → 三联 1920x1080")
    return (f"[0:v]{chain},setsar=1[base];"
            f"[base]split=3[p1][p2][p3];[p1][p2][p3]hstack=3[tript]")


def make_cover_png(src: Path, out: Path, *, at: float, theme: str,
                   title: str, en: str, kicker: str, tag: str, foot: str,
                   yoff: float) -> bool:
    """从素材首帧生成 1280x720 系列封面。"""
    print(f"  抽取 hero 帧 @ {at}s → 生成封面...")
    try:
        hero = hero_from_video(src, at)
        img = build_cover(load_hero(hero), THEMES[theme], title=title, en=en,
                          kicker=kicker, tag=tag, foot=foot, yoff=yoff)
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out, "PNG")
        img.save(out.with_suffix(".jpg"), "JPEG", quality=92)
        hero.unlink(missing_ok=True)
        print(f"  ✓ {out.name} + {out.with_suffix('.jpg').name}")
        return True
    except Exception as e:
        print(f"  ✗ 封面生成失败: {e}")
        return False


def cover_to_card(cover: Path, out: Path, duration: float) -> bool:
    """封面 PNG → 定长片头视频(放大到 1920x1080)。"""
    return run_ffmpeg([
        "-loop", "1", "-i", str(cover), "-t", f"{duration}",
        "-vf", "scale=1920:1080:flags=lanczos,setsar=1,format=" + PIX_FMT,
        "-r", "30", "-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF),
        "-pix_fmt", PIX_FMT, "-aspect", "16:9", str(out),
    ], f"封面 → {duration}s 片头卡...")


def generate_triptych(src: Path, out: Path, duration: float) -> bool:
    info = probe_video(src)
    box = detect_content_box(src)
    return run_ffmpeg([
        "-stream_loop", "-1", "-i", str(src),
        "-filter_complex", build_filter(info, box),
        "-map", "[tript]", "-t", f"{duration}", "-r", "30",
        "-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF),
        "-pix_fmt", PIX_FMT, "-aspect", "16:9", str(out),
    ], f"生成三联主体 ({duration:.1f}s)...")


def concat_with_fades(card: Path, tript: Path, out: Path, *, total: float,
                      fade_in: float, fade_out: float) -> bool:
    """拼接片头 + 主体,并在整段首尾做视频淡入淡出。"""
    fo_start = max(0.0, total - fade_out)
    vf = (f"[0:v][1:v]concat=n=2:v=1:a=0[c];"
          f"[c]fade=t=in:st=0:d={fade_in:.3f},"
          f"fade=t=out:st={fo_start:.3f}:d={fade_out:.3f}[v]")
    return run_ffmpeg([
        "-i", str(card), "-i", str(tript),
        "-filter_complex", vf, "-map", "[v]",
        "-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF),
        "-pix_fmt", PIX_FMT, "-aspect", "16:9", str(out),
    ], f"拼接 + 视频淡入 {fade_in}s / 淡出 {fade_out}s...")


def add_bgm(combined: Path, bgm: Path, out: Path, *, duration: float,
            fade_in: float, fade_out: float) -> bool:
    fo_start = max(0.0, duration - fade_out)
    af = (f"afade=t=in:st=0:d={fade_in:.3f},"
          f"afade=t=out:st={fo_start:.3f}:d={fade_out:.3f}")
    return run_ffmpeg([
        "-i", str(combined), "-i", str(bgm),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{duration}",
        "-af", af, "-map", "0:v", "-map", "1:a", "-shortest", str(out),
    ], f"贴 BGM + 音频淡入 {fade_in}s / 淡出 {fade_out}s...")


def upload_to_gofile(path: Path) -> str | None:
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


def main() -> None:
    ap = argparse.ArgumentParser(description="全自动三联视频生成器 v4")
    ap.add_argument("video", help="源视频(裸文件名会自动在媒体目录里查找)")
    ap.add_argument("--outdir", default=None, help="输出目录(默认 out/)")

    c = ap.add_argument_group("封面文案(由调用方撰写)")
    c.add_argument("--cover-title", default=None, help="中文大标题(两字最佳)")
    c.add_argument("--cover-en", default=None, help="英文副标")
    c.add_argument("--cover-kicker", default="LOOP · SERIES")
    c.add_argument("--cover-tag", default="", help="中文 tagline")
    c.add_argument("--cover-foot", default="for you", help="页脚英文小字")
    c.add_argument("--theme", choices=sorted(THEMES), default="cool")
    c.add_argument("--hero-at", type=float, default=0.0,
                   help="hero 帧时间点,默认 0 = 首帧")
    c.add_argument("--yoff", type=float, default=-0.02, help="hero 竖向裁切偏移")
    c.add_argument("--cover", default=None, help="直接指定现成封面 PNG,跳过生成")

    t = ap.add_argument_group("时长与淡入淡出")
    t.add_argument("--intro", type=float, default=3.0, help="片头封面时长(秒)")
    t.add_argument("--fade-in", type=float, default=1.0, help="视频淡入(秒)")
    t.add_argument("--fade-out", type=float, default=1.5, help="视频淡出(秒)")
    t.add_argument("--afade-in", type=float, default=2.0, help="音频淡入(秒)")
    t.add_argument("--afade-out", type=float, default=3.0, help="音频淡出(秒)")
    t.add_argument("--duration", type=float, default=None,
                   help="覆盖总时长(秒),仅用于冒烟测试")

    ap.add_argument("--upload", action="store_true", help="完成后上传 gofile.io")
    ap.add_argument("--keep-temp", action="store_true", help="保留中间文件")
    args = ap.parse_args()

    src = resolve_source(args.video)
    outdir = Path(args.outdir).resolve() if args.outdir else OUT
    outdir.mkdir(parents=True, exist_ok=True)

    bgm = find_bgm()
    total = args.duration if args.duration else probe_duration(bgm)
    intro = min(args.intro, total / 2)
    body = total - intro

    stem = src.stem
    title = args.cover_title or stem
    base = f"{stem}_final"
    cover = Path(args.cover) if args.cover else outdir / f"cover_{stem}.png"
    card = outdir / f"{base}_card.mp4"
    tript = outdir / f"{base}_triptych.mp4"
    combined = outdir / f"{base}_combined.mp4"
    final = outdir / f"{base}.mp4"

    print("=" * 62)
    print("全自动三联视频生成器 v4")
    print("=" * 62)
    print(f"源视频: {src}")
    print(f"BGM:    {bgm.name}")
    print(f"总时长: {total:.3f}s = 片头 {intro:.1f}s + 主体 {body:.1f}s")
    print(f"淡入淡出: 视频 {args.fade_in}s/{args.fade_out}s  "
          f"音频 {args.afade_in}s/{args.afade_out}s")
    print(f"封面:   {title} / {args.cover_en or '(无英文副标)'}  [{args.theme}]")
    print()

    print("[1/4] 封面")
    if args.cover:
        print(f"  使用现成封面: {cover}")
        if not cover.exists():
            print("  ✗ 封面文件不存在")
            sys.exit(1)
    elif not make_cover_png(src, cover, at=args.hero_at, theme=args.theme,
                            title=title, en=args.cover_en or stem.upper(),
                            kicker=args.cover_kicker, tag=args.cover_tag,
                            foot=args.cover_foot, yoff=args.yoff):
        sys.exit(1)
    if not cover_to_card(cover, card, intro):
        sys.exit(1)

    print("\n[2/4] 三联主体")
    if not generate_triptych(src, tript, body):
        sys.exit(1)

    print("\n[3/4] 拼接 + 视频淡入淡出")
    if not concat_with_fades(card, tript, combined, total=total,
                             fade_in=args.fade_in, fade_out=args.fade_out):
        sys.exit(1)

    print("\n[4/4] BGM + 音频淡入淡出")
    if not add_bgm(combined, bgm, final, duration=total,
                   fade_in=args.afade_in, fade_out=args.afade_out):
        sys.exit(1)

    if not args.keep_temp:
        for f in (card, tript, combined):
            f.unlink(missing_ok=True)

    url = upload_to_gofile(final) if args.upload else None

    print("\n" + "=" * 62)
    print("✓ 完成")
    print("=" * 62)
    print(f"视频: {final} ({final.stat().st_size / 1024 / 1024:.0f} MB)")
    print(f"封面: {cover}")
    if url:
        print(f"下载: {url}")
    print("=" * 62)


if __name__ == "__main__":
    main()
