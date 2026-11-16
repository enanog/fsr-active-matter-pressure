"""Regenerate the app icons (<app>.ico next to this script): two letters on a rounded square in the project
palette. Run once after changing a colour or a label; construir.py picks them up."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ICONS = {"vidfetch": ("VF", "#2a78d6"), "fsrscope": ("FS", "#eb6834")}


def font(size: int):
    for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


for app, (text, color) in ICONS.items():
    s = 256
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((8, 8, s - 8, s - 8), radius=48, fill=color)
    f = font(120)
    w, h = d.textbbox((0, 0), text, font=f)[2:]
    d.text(((s - w) / 2, (s - h) / 2 - 10), text, font=f, fill="white")
    im.save(HERE / f"{app}.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(HERE / f"{app}.ico")
