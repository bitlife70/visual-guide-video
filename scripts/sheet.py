"""이미지 여러 장을 시각 라벨이 붙은 2x2 시트(1920x1080)로 묶는다 — 많은 프레임을 한 번에 검토할 때."""
import os

from PIL import Image, ImageDraw

from gfx import FONT_B, font


def make_sheets(files, out_dir, prefix="sheet"):
    """files: [(path, label), ...] → 시트 경로 목록."""
    f = font(FONT_B, 30)
    out = []
    for i in range(0, len(files), 4):
        sh = Image.new("RGB", (1920, 1080))
        d = ImageDraw.Draw(sh)
        for k, (fn, label) in enumerate(files[i:i + 4]):
            im = Image.open(fn).convert("RGB")
            im.thumbnail((960, 540))
            x, y = (k % 2) * 960, (k // 2) * 540
            sh.paste(im, (x, y))
            tw = d.textlength(label, font=f)
            d.rectangle([x, y, x + tw + 14, y + 42], fill=(220, 30, 30))
            d.text((x + 7, y + 3), label, font=f, fill="white")
        p = os.path.join(out_dir, f"{prefix}{i // 4:02d}.jpg")
        sh.save(p, quality=88)
        out.append(p)
    return out
