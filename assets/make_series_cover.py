#!/usr/bin/env python3
"""LOOP 系列封面生成器(1280x720)

把 make_thumb / make_cover_b / make_v3_cover / make_v17 四个换皮脚本合成一个,
配色和文案改成参数。版式与原系列逐像素一致:

  左侧竖向渐变深色底 + 右侧 560px hero 面板(左缘 120px alpha 羽化)
  左栏:色块 kicker → 190px 宋体粗中文大标题 → 78px 英文副标
        → 细分隔线 → 38px tagline → 30px 英文小字 + 爱心
  hero 上两条双层竖线分三格(呼应三联屏)
  播放按钮在 H*0.72(避开人脸)+ 高斯 vignette 压暗四角

hero 图可以是图片,也可以直接给视频 —— 会自动抽帧。

用法:
    python3 assets/make_series_cover.py --hero extra/勾勒.mp4 --at 12 \
        --theme cool --title 流光 --en RADIANCE \
        --kicker "COOL · DARK VIBES" --tag "冷冽暗夜 · 光影流动" \
        --foot "from the dark" --out covers/cover_test.png

主题:cool(冰蓝/深灰,v3/v17/LOOP 用)· warm(珊瑚/暖褐,确幸用)
"""
from __future__ import annotations

import argparse
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_paths import COVERS, SANS_BOLD, SERIF_BOLD, resolve_source  # noqa: E402

W, H = 1280, 720
HERO_W = 560
FEATHER = 120

THEMES = {
    "cool": {
        "dark": (12, 14, 18), "mid": (42, 44, 52),
        "accent": (120, 210, 255), "soft": (230, 235, 240),
        "halo": (60, 40, 34), "vignette": (10, 12, 16),
    },
    "warm": {
        "dark": (38, 32, 28), "mid": (65, 52, 44),
        "accent": (255, 143, 112), "soft": (230, 225, 220),
        "halo": (60, 40, 34), "vignette": (60, 40, 34),
    },
}
WHITE = (255, 255, 255)

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def hero_from_video(video: Path, at: float) -> Path:
    """在 at 秒抽一帧当 hero 图。原脚本要求手工准备 *_hero.jpg。"""
    tmp = Path(tempfile.gettempdir()) / f"_hero_{video.stem}_{at:g}.png"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", str(at), "-i", str(video), "-frames:v", "1", "-update", "1",
         str(tmp)],
        check=True,
    )
    return tmp


def load_hero(path: Path) -> Image.Image:
    img = Image.open(path).convert("RGB")
    img = trim_bars(img)
    img = ImageEnhance.Contrast(img).enhance(1.05)
    return ImageEnhance.Color(img).enhance(1.10)


def trim_bars(img: Image.Image, thresh: int = 14) -> Image.Image:
    """裁掉素材自带的信箱/邮筒黑边。

    竖版素材常被封装进 1920x1080 画布(两侧黑边)。不裁掉的话
    object-fit:cover 会把黑边一起塞进 hero 面板 —— 表现为封面右侧
    一条纯黑竖带。
    """
    a = np.asarray(img).astype(np.int16)
    col = a.mean(axis=(0, 2))
    row = a.mean(axis=(1, 2))
    w, h = img.size

    x0 = 0
    while x0 < w // 2 and col[x0] < thresh:
        x0 += 1
    x1 = w
    while x1 > w // 2 + 1 and col[x1 - 1] < thresh:
        x1 -= 1
    y0 = 0
    while y0 < h // 2 and row[y0] < thresh:
        y0 += 1
    y1 = h
    while y1 > h // 2 + 1 and row[y1 - 1] < thresh:
        y1 -= 1

    if (x0, y0, x1, y1) == (0, 0, w, h):
        return img
    print(f"  裁掉黑边: {w}x{h} → {x1 - x0}x{y1 - y0} "
          f"(左{x0} 右{w - x1} 上{y0} 下{h - y1})")
    return img.crop((x0, y0, x1, y1))


def cover_crop_offset(img: Image.Image, tw: int, th: int, yoff: float = 0.0) -> Image.Image:
    """object-fit: cover,可偏移竖向裁切位置(yoff<0 保留更多顶部)。"""
    iw, ih = img.size
    scale = max(tw / iw, th / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - tw) // 2
    top = max(0, min(nh - th, int((nh - th) * (0.5 + yoff))))
    return img.crop((left, top, left + tw, top + th))


def heart(draw: ImageDraw.ImageDraw, cx: float, cy: float, s: float, col) -> None:
    pts = []
    for i in range(315):
        t = i * 0.02
        x = 16 * math.sin(t) ** 3
        y = (13 * math.cos(t) - 5 * math.cos(2 * t)
             - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + x * s, cy - y * s))
    draw.polygon(pts, fill=col)


def build(hero_img: Image.Image, theme: dict, *, title: str, en: str,
          kicker: str, tag: str, foot: str, yoff: float) -> Image.Image:
    dark, mid = theme["dark"], theme["mid"]
    accent, soft = theme["accent"], theme["soft"]

    # 竖向渐变底
    canvas = Image.new("RGB", (W, H), dark)
    bd = ImageDraw.Draw(canvas)
    for y in range(H):
        t = y / H
        bd.line([(0, y), (W, y)],
                fill=tuple(int(dark[i] + (mid[i] - dark[i]) * t) for i in range(3)))

    # 右侧 hero 面板,左缘线性羽化
    hero_x = W - HERO_W
    hero = cover_crop_offset(hero_img, HERO_W, H, yoff=yoff).convert("RGBA")
    ax = np.clip(np.arange(HERO_W) / FEATHER, 0, 1)
    mask = Image.fromarray(np.tile((ax * 255).astype("uint8"), (H, 1)), "L")
    canvas.paste(hero, (hero_x, 0), mask)

    draw = ImageDraw.Draw(canvas, "RGBA")

    # kicker
    draw.rounded_rectangle([70, 88, 104, 126], radius=8, fill=accent)
    draw.text((118, 88), kicker, font=font(SANS_BOLD, 30), fill=soft)

    # 大标题 + 英文副标（字号按字数自适应,撑满左栏 520px）
    title_size = {1: 320, 2: 240, 3: 200}.get(len(title), 190)
    draw.text((62, 148), title, font=font(SERIF_BOLD, title_size), fill=WHITE)
    en_size = {1: 110, 2: 95, 3: 80}.get(len(en), 78)
    draw.text((68, 392), en, font=font(SANS_BOLD, en_size), fill=accent)

    draw.line([(70, 496), (520, 496)], fill=WHITE + (90,), width=3)
    draw.text((68, 516), tag, font=font(SANS_BOLD, 38), fill=soft)

    # 装饰十字星
    for sx, sy, ss in ((480, 180, 18), (520, 300, 14)):
        draw.line([(sx - ss, sy), (sx + ss, sy)], fill=accent, width=6)
        draw.line([(sx, sy - ss), (sx, sy + ss)], fill=accent, width=6)

    # 页脚小字 + 爱心(爱心尺寸/间距按文字实测,避免压字)
    ff = font(SANS_BOLD, 30)
    draw.text((68, 570), foot, font=ff, fill=soft)
    tb = draw.textbbox((68, 570), foot, font=ff)
    heart(draw, tb[2] + 34, (tb[1] + tb[3]) / 2 - 9, 1.3, accent)

    # 三联分隔线:暗光晕 + 亮芯,明暗背景都能看清
    for k in (1, 2):
        lx = hero_x + HERO_W * k // 3
        draw.line([(lx, 0), (lx, H)], fill=theme["halo"] + (130,), width=8)
        draw.line([(lx, 0), (lx, H)], fill=WHITE + (235,), width=3)

    # 播放按钮(压低避开人脸)
    pcx, pcy, pr = hero_x + HERO_W // 2, int(H * 0.72), 56
    draw.ellipse([pcx - pr - 4, pcy - pr - 4, pcx + pr + 4, pcy + pr + 4],
                 fill=theme["vignette"] + (130,))
    draw.ellipse([pcx - pr, pcy - pr, pcx + pr, pcy + pr], fill=WHITE + (235,))
    draw.polygon([(pcx - 18, pcy - 27), (pcx - 18, pcy + 27), (pcx + 30, pcy)],
                 fill=accent)

    # vignette
    vig = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vig).ellipse([-200, -160, W + 200, H + 160], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(170))
    return Image.composite(canvas, Image.new("RGB", (W, H), theme["vignette"]), vig)


def main() -> None:
    ap = argparse.ArgumentParser(description="LOOP 系列封面生成器")
    ap.add_argument("--hero", required=True, help="hero 素材:图片或视频")
    ap.add_argument("--at", type=float, default=1.0, help="视频抽帧时间点(秒)")
    ap.add_argument("--theme", choices=sorted(THEMES), default="cool")
    ap.add_argument("--title", required=True, help="中文大标题(两字最佳)")
    ap.add_argument("--en", required=True, help="英文副标")
    ap.add_argument("--kicker", default="LOOP · SERIES")
    ap.add_argument("--tag", default="", help="中文 tagline")
    ap.add_argument("--foot", default="for you", help="页脚英文小字")
    ap.add_argument("--yoff", type=float, default=-0.02,
                    help="hero 竖向裁切偏移,负值保留更多顶部(如 -0.30)")
    ap.add_argument("--out", default=None, help="输出 PNG 路径")
    args = ap.parse_args()

    src = Path(args.hero)
    if not src.exists():
        src = resolve_source(args.hero)

    tmp_hero = None
    if src.suffix.lower() in VIDEO_EXT:
        tmp_hero = hero_from_video(src, args.at)
        hero_path = tmp_hero
        print(f"从视频抽帧: {src.name} @ {args.at}s")
    else:
        hero_path = src

    out = Path(args.out) if args.out else COVERS / f"cover_{args.title}.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    img = build(load_hero(hero_path), THEMES[args.theme],
                title=args.title, en=args.en, kicker=args.kicker,
                tag=args.tag, foot=args.foot, yoff=args.yoff)
    img.save(out, "PNG")
    img.save(out.with_suffix(".jpg"), "JPEG", quality=92)

    if tmp_hero:
        tmp_hero.unlink(missing_ok=True)
    print(f"saved: {out} {img.size}")
    print(f"saved: {out.with_suffix('.jpg')}")


if __name__ == "__main__":
    main()
