"""收集 OGA 兔兔素材候选（预选清单版）：下载预览图并拼编号总览图。"""
from __future__ import annotations

import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "options"
CACHE = OUT / "_cache"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"

CANDIDATES = [
    "mascot-bunny-character",               # 已在用的卡通白兔
    "hand-painted-bunny-unrigged-version",  # 手绘兔
    "lucky-bunny",                          # 幸运兔
    "rabbit-0",                             # Case Conflict 兔（动画gif）
    "rabbit-1",
    "rabbit-2",
    "animated-rabbit-with-a-hat-in-seven-actions",  # 戴帽兔 7动作
    "rabbit-eating",                        # 吃萝卜兔
    "cute-rabbit",                          # 可爱兔
    "tiny-rabbit-spirit",                   # 小兔精灵
    "bunny-animation",                      # 兔兔动画
    "easter-bunny",                         # 复活节兔
    "bunny-sprite",
    "pixel-rabbit-people",
    "rabbit-head-sprite-sheet",
    "spring-monster-pack",                  # 春季怪物包（含兔）
    "characters-the-woods",
    "monster-pack-rabbits",
    "animal-pack-redux",                    # 动物包
    "tiny-creatures",                       # 小生物包
]


def fetch(url: str, binary: bool = False) -> bytes:
    CACHE.mkdir(parents=True, exist_ok=True)
    key = urllib.parse.quote(url, safe="")[:150]
    path = CACHE / key
    if path.exists() and not binary:
        return path.read_bytes()
    data = subprocess.run(
        ["curl", "-sL", "--max-time", "25", "-A", UA, url],
        capture_output=True,
    ).stdout
    time.sleep(0.6)
    if not binary:
        path.write_bytes(data)
    return data


def html_of(url: str) -> str:
    for _ in range(3):
        data = fetch(url)
        html = data.decode("utf-8", errors="ignore")
        if "license-name" in html:
            return html
        time.sleep(2)
    return html


def scan(path: str) -> dict:
    html = html_of(f"https://opengameart.org/content/{path}")
    titles = [t.strip() for t in re.findall(r"<h2[^>]*>([^<]+)</h2>", html)
              if t.strip() not in {"User login", "Comments", "FAQ", "FAQ ", "Chat with us!"}]
    lic = sorted(set(re.findall(r"license-name'>\s*([^<]+?)\s*<", html)))
    imgs = re.findall(r'(?:src|href)="(https://opengameart.org/sites/default/files/[^"]+\.(?:png|gif))"', html)
    imgs = [u for u in imgs if not re.search(r"css|js|icon|banner|logo|cover", u, re.I)]
    return {"path": path, "title": titles[0] if titles else path, "lic": lic, "imgs": imgs}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows, sheet_imgs = [], []
    for i, p in enumerate(CANDIDATES, 1):
        try:
            info = scan(p)
        except Exception as exc:
            print(f"#{i} {p} ERR {exc}", flush=True)
            continue
        fname = OUT / f"{i:02d}.png"
        url = info["imgs"][0] if info["imgs"] else ""
        if url:
            try:
                data = fetch(url, binary=True)
                if data and len(data) > 500:
                    (OUT / "tmp_preview").write_bytes(data)
                    im = Image.open(OUT / "tmp_preview")
                    if getattr(im, "is_animated", False):
                        im.seek(0)
                    im = im.convert("RGBA")
                    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
                    bg.alpha_composite(im)
                    bg.convert("RGB").save(fname)
                    sheet_imgs.append((i, info["title"], fname))
            except Exception as exc:
                print(f"#{i} 预览失败 {exc}", flush=True)
            finally:
                (OUT / "tmp_preview").unlink(missing_ok=True)
        rows.append(f"{i}. {info['title']} | 许可: {','.join(info['lic']) or '?'} | https://opengameart.org/content/{p}")
        print(f"#{i} done: {info['title']} | {','.join(info['lic'])} | imgs={len(info['imgs'])}", flush=True)

    if sheet_imgs:
        cell_w, cell_h, cols = 300, 280, 3
        grid = [sheet_imgs[i:i + cols] for i in range(0, len(sheet_imgs), cols)]
        sheet = Image.new("RGB", (cols * cell_w, len(grid) * cell_h), (245, 245, 245))
        draw = ImageDraw.Draw(sheet)
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 22)
            font_s = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 14)
        except OSError:
            font = font_s = ImageFont.load_default()
        for r, row in enumerate(grid):
            for c, (idx, title, fname) in enumerate(row):
                x, y = c * cell_w, r * cell_h
                draw.rectangle([x, y, x + cell_w, y + cell_h], outline=(200, 200, 200))
                try:
                    im = Image.open(fname)
                    im.thumbnail((cell_w - 20, cell_h - 54))
                    sheet.paste(im, (x + (cell_w - im.width) // 2, y + 6))
                except Exception:
                    pass
                draw.text((x + 8, y + cell_h - 48), f"#{idx} {title[:14]}", fill=(40, 40, 40), font=font_s)
                draw.text((x + 8, y + 4), str(idx), fill=(220, 60, 60), font=font)
        sheet.save(OUT / "contact_sheet.png")
        print("总览图:", OUT / "contact_sheet.png", sheet.size, flush=True)

    (OUT / "summary.txt").write_text("\n".join(rows), encoding="utf-8")
    print("清单:", OUT / "summary.txt", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
