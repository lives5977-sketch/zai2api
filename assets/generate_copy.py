#!/usr/bin/env python3
"""AI-generated cover copy for the triptych pipeline.

Generates Chinese title + English subtitle + tagline from a source video's
first frame (or from user-provided keywords).

Usage:
    python3 assets/generate_copy.py <video> [--theme cool] [--model glm-4.5-flash]
    python3 assets/generate_copy.py --keywords "neon rain cyberpunk"
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_paths import resolve_source  # noqa: E402


def extract_frame(video: Path, at: float = 0.0, out: Path | None = None) -> Path:
    """抽一帧作为视觉描述输入。"""
    import subprocess
    if out is None:
        out = Path(tempfile.gettempdir()) / f"_frame_{video.stem}_{at:g}.jpg"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", str(at), "-i", str(video), "-frames:v", "1", "-q:v", "2",
         str(out)],
        check=True,
    )
    return out


def get_api_key() -> str:
    """从 ~/.hermes/.env 读取 ZAI_API_KEY。"""
    key_path = Path.home() / ".hermes" / ".env"
    if key_path.exists():
        for line in key_path.read_text().splitlines():
            if line.startswith("ZAI_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("ZAI_API_KEY not found in ~/.hermes/.env")


def call_llm(system_prompt: str, user_prompt: str, image: Path | None = None,
             model: str = "glm-4.5-flash") -> str:
    """调 api.z.ai 画图/文。"""
    import httpx
    url = "https://api.z.ai/api/paas/v4/chat/completions"
    api_key = get_api_key()

    msgs = [{"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}]
    if image and image.exists():
        data = base64.b64encode(image.read_bytes()).decode()
        msgs[-1] = {
            "role": "user",
            "content": [
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{data}"
                }},
            ],
        }

    r = httpx.post(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }, json={"model": model, "messages": msgs, "max_tokens": 500,
             "thinking": {"type": "disabled"}}, timeout=60)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


SYSTEM_PROMPT = """你是一个视频封面文案策划。输出 JSON，包含：
- title: 中文大标题，固定2字，意境精准
- en: 英文副标，全大写，3-6词
- kicker: 风格标签，如"COOL · DARK VIBES"
- tag: 中文tagline，10-20字，描述画面氛围
- foot: 英文页脚小字，2-4词

只输出JSON，不要解释。"""


USER_PROMPT_TEMPLATE = """请根据以下视频画面的视觉描述，生成封面文案：

{description}

要求：
- title 要有诗意，适合视频主题
- en 要简洁有力，与title呼应
- tag 要能抓住画面核心氛围"""


def parse_copy(text: str) -> dict:
    """从LLM输出解析JSON。"""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON found in: {text}")
    return json.loads(text[start:end + 1])


def main() -> None:
    ap = argparse.ArgumentParser(description="AI生成封面文案")
    ap.add_argument("video", nargs="?", help="源视频(不传则用keywords)")
    ap.add_argument("--keywords", default="", help="视觉关键词(替代视频描述)")
    ap.add_argument("--at", type=float, default=0.0, help="抽帧时间点")
    ap.add_argument("--model", default="glm-4.5-flash", help="LLM模型")
    ap.add_argument("--describe-model", default="glm-4.5-flash", help="视觉描述模型")
    args = ap.parse_args()

    if args.video:
        src = resolve_source(args.video)
        frame = extract_frame(src, args.at)
        try:
            desc_prompt = "请用100字详细描述这张图片的内容、色彩、氛围、构图。"
            description = call_llm(
                "你是一个视觉描述专家，输出纯文本描述。",
                desc_prompt,
                image=frame,
                model=args.describe_model,
            )
        finally:
            frame.unlink(missing_ok=True)
    else:
        description = args.keywords or "抽象艺术风格，流动的光影，冷暖色调对比"

    copy = call_llm(SYSTEM_PROMPT, USER_PROMPT_TEMPLATE.format(description=description),
                    model=args.model)
    result = parse_copy(copy)

    print("=" * 60)
    print("AI生成封面文案")
    print("=" * 60)
    for k, v in result.items():
        print(f"  {k}: {v}")
    print("=" * 60)
    print("使用示例:")
    print(f'  --cover-title "{result["title"]}" \\')
    print(f'  --cover-en "{result["en"]}" \\')
    print(f'  --cover-kicker "{result["kicker"]}" \\')
    print(f'  --cover-tag "{result["tag"]}" \\')
    print(f'  --cover-foot "{result["foot"]}"')


if __name__ == "__main__":
    main()
