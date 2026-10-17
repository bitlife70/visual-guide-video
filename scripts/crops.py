"""좌표 측정용 크롭: 지정 시각의 영역을 원본 해상도로 잘라 '원본 픽셀 좌표' 눈금을 그려 준다.

클릭 지점·하이라이트 사각형 좌표를 timeline.py 에 정확히 적기 위한 도구.

  python crops.py VIDEO --t 7.5,13.6 --box 0,700,480,300 --out crops.jpg   # 영역 확대(눈금 50px)
  python crops.py VIDEO --t 12 --full --out grid.jpg                     # 전체 화면 + 100px 격자
"""
import argparse
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from gfx import FONT_B, font  # noqa: E402


def grab(cap, fps, t):
    cap.set(cv2.CAP_PROP_POS_FRAMES, round(t * fps))
    ok, f = cap.read()
    if not ok:
        raise SystemExit(f"{t}s 프레임 없음")
    return f


def ruler(img, x0, y0, scale, step):
    """img(PIL) 위에 원본 좌표 기준 눈금·격자."""
    d = ImageDraw.Draw(img, "RGBA")
    f = font(FONT_B, 16)
    w, h = img.size
    sx = (step - x0 % step) % step
    for gx in np.arange(x0 + sx, x0 + w / scale, step):
        px = (gx - x0) * scale
        d.line([px, 0, px, h], fill=(255, 255, 0, 60))
        d.line([px, 0, px, 10], fill=(255, 255, 0, 255), width=2)
        d.text((px + 2, 10), str(int(gx)), font=f, fill=(255, 255, 0, 255), stroke_width=2, stroke_fill=(0, 0, 0))
    sy = (step - y0 % step) % step
    for gy in np.arange(y0 + sy, y0 + h / scale, step):
        py = (gy - y0) * scale
        d.line([0, py, w, py], fill=(0, 255, 255, 60))
        d.line([0, py, 10, py], fill=(0, 255, 255, 255), width=2)
        d.text((12, py + 1), str(int(gy)), font=f, fill=(0, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--t", required=True, help="쉼표로 구분한 시각(초)")
    ap.add_argument("--box", help="x,y,w,h (원본 픽셀)")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--step", type=int, default=0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    W0, H0 = int(cap.get(3)), int(cap.get(4))
    tiles = []
    for t in [float(x) for x in args.t.split(",")]:
        f = cv2.cvtColor(grab(cap, fps, t), cv2.COLOR_BGR2RGB)
        if args.full:
            x, y, w, h = 0, 0, W0, H0
        else:
            x, y, w, h = [int(v) for v in args.box.split(",")]
            x, y = max(0, x), max(0, y)
            w, h = min(w, W0 - x), min(h, H0 - y)
        crop = f[y:y + h, x:x + w]
        scale = min(1920 / w, 1.0 if args.full else 2.0)
        if args.full:
            scale = 1600 / w
        im = Image.fromarray(crop).resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        ruler(im, x, y, scale, args.step or (100 if args.full else 50))
        d = ImageDraw.Draw(im)
        d.rectangle([im.width - 130, 0, im.width, 34], fill=(220, 30, 30))
        d.text((im.width - 122, 3), f"{t:.2f}s", font=font(FONT_B, 24), fill="white")
        tiles.append(im)
    tw = max(i.width for i in tiles)
    sheet = Image.new("RGB", (tw, sum(i.height for i in tiles) + 6 * (len(tiles) - 1)), (40, 40, 40))
    y = 0
    for i in tiles:
        sheet.paste(i, (0, y))
        y += i.height + 6
    sheet.save(args.out, quality=90)
    print(args.out, sheet.size)


if __name__ == "__main__":
    main()
