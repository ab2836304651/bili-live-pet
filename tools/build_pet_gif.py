"""精灵帧目录 -> 透明 GIF 构建工具。

素材：OpenGameArt「Mascot Bunny Character」by Sashim（CC0）
  https://opengameart.org/content/mascot-bunny-character

用法：
    python tools/build_pet_gif.py \
        --frames assets/mascot_bunny/MascotBunnyCharacter/Bunny1/01-Idle \
        --out assets/pet_idle.gif --duration 120 --scale 220
    python tools/build_pet_gif.py \
        --frames assets/mascot_bunny/MascotBunnyCharacter/Bunny1/05-JumpThrow \
        --out assets/pet_talk.gif --duration 90 --scale 220

说明：
- 每帧裁掉透明边后按并集 bbox 统一居中（防抖动）；
- --scale 平滑缩放到目标最大边长（卡通素材用 LANCZOS）；
- 透明像素映射到调色板中未使用的索引作为 GIF 透明色。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def load_frames(frames_dir: Path) -> list:
    files = sorted(frames_dir.glob("*.png"))
    if not files:
        raise SystemExit(f"目录里没有 PNG 帧: {frames_dir}")
    return [Image.open(f).convert("RGBA") for f in files]


def normalize(frames: list, scale: int) -> list:
    """统一画布居中 + 平滑缩放。"""
    boxes = [f.getbbox() for f in frames]
    x0 = min(b[0] for b in boxes if b)
    y0 = min(b[1] for b in boxes if b)
    x1 = max(b[2] for b in boxes if b)
    y1 = max(b[3] for b in boxes if b)
    cw, ch = x1 - x0, y1 - y0
    out = []
    for f, b in zip(frames, boxes):
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        if b:
            canvas.paste(f.crop(b), (0, 0))
        if scale:
            w, h = canvas.size
            k = scale / max(w, h)
            canvas = canvas.resize((max(1, int(w * k)), max(1, int(h * k))), Image.LANCZOS)
        out.append(canvas)
    return out


def frame_to_p_with_transparency(rgba: Image.Image) -> Image.Image:
    """RGBA -> P 模式，透明像素统一映射到未使用的调色板索引。"""
    alpha = rgba.getchannel("A")
    p = rgba.quantize(colors=255, method=Image.FASTOCTREE).convert("P")
    px = p.load()
    used = set()
    for y in range(p.height):
        for x in range(p.width):
            if alpha.getpixel((x, y)) >= 128:
                used.add(px[x, y])
    transparent_idx = 0 if 0 not in used else next(
        i for i in range(256) if i not in used
    )
    for y in range(p.height):
        for x in range(p.width):
            if alpha.getpixel((x, y)) < 128:
                px[x, y] = transparent_idx
    p.info["transparency"] = transparent_idx
    return p


def to_gif(frames: list, out_path: Path, duration_ms: int) -> None:
    frames = [frame_to_p_with_transparency(f) for f in frames]
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
        transparency=frames[0].info["transparency"],
        disposal=2,
    )
    print(f"已生成 {out_path}（{len(frames)} 帧, {duration_ms}ms/帧）")


def main() -> int:
    ap = argparse.ArgumentParser(description="精灵帧目录转透明 GIF")
    ap.add_argument("--frames", required=True, help="PNG 帧目录")
    ap.add_argument("--out", required=True, help="输出 GIF 路径")
    ap.add_argument("--duration", type=int, default=120, help="每帧毫秒数")
    ap.add_argument("--scale", type=int, default=0, help="最大边长（0=不缩放）")
    args = ap.parse_args()

    frames_dir = Path(args.frames)
    if not frames_dir.is_absolute():
        frames_dir = ROOT / frames_dir
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = ROOT / out_path

    frames = normalize(load_frames(frames_dir), args.scale)
    out_path.parent.mkdir(exist_ok=True)
    to_gif(frames, out_path, args.duration)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
