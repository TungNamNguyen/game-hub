"""Sinh favicon.ico + apple-touch-icon.png từ cùng một thiết kế với favicon.svg.

Chạy: python scripts/make_favicon.py

Vì sao cần cả ba file:
  - favicon.svg  — Chrome/Edge/Firefox mới dùng cái này, nét ở mọi cỡ.
  - favicon.ico  — Safari cũ và những thứ tự gọi /favicon.ico mà không đọc
                   <link> (RSS reader, app chat khi dán link, Windows pin).
  - apple-touch-icon.png — iOS/Android khi "Thêm vào màn hình chính".

Thiết kế phải TRÙNG favicon.svg: nền squircle gradient Indigo -> Violet -> Pink
kèm biểu tượng tay cầm chơi game trắng với D-pad và nút bấm màu nổi bật.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "static"
STOPS = (
    (0.00, (79, 70, 229)),    # #4f46e5
    (0.52, (124, 58, 237)),   # #7c3aed
    (1.00, (219, 39, 119)),   # #db2777
)
CANVAS = 1024
CORNER_R = 8.0


def _lerp_stops(t: float) -> tuple[int, int, int]:
    for idx in range(len(STOPS) - 1):
        t0, c0 = STOPS[idx]
        t1, c1 = STOPS[idx + 1]
        if t <= t1:
            local = (t - t0) / max(1e-6, t1 - t0)
            return tuple(round(a + (b - a) * local) for a, b in zip(c0, c1))
    return STOPS[-1][1]


def diagonal_gradient(size: int) -> Image.Image:
    """Gradient chéo 135 độ với 3 điểm dừng màu."""
    small = 128
    base = Image.new("RGB", (small, small))
    pixels = base.load()
    for y in range(small):
        for x in range(small):
            t = (x + y) / (2 * (small - 1))
            pixels[x, y] = _lerp_stops(t)
    return base.resize((size, size), Image.BICUBIC)


def _cubic(p0, p1, p2, p3, steps: int = 36):
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1.0 - t
        x = (u**3) * p0[0] + 3 * (u**2) * t * p1[0] + 3 * u * (t**2) * p2[0] + (t**3) * p3[0]
        y = (u**3) * p0[1] + 3 * (u**2) * t * p1[1] + 3 * u * (t**2) * p2[1] + (t**3) * p3[1]
        pts.append((x, y))
    return pts


def gamepad_polygon(scale: float) -> list[tuple[float, float]]:
    """Chuyển path tay cầm trong hệ toạ độ 32x32 sang đa giác mịn."""
    raw = [(9.6, 9.3), (22.4, 9.3)]
    raw += _cubic((22.4, 9.3), (25.5, 9.3), (27.6, 12.4), (27.4, 17.7))
    raw += _cubic((27.4, 17.7), (27.2, 21.6), (25.4, 23.4), (23.6, 23.4))
    raw += _cubic((23.6, 23.4), (22.1, 23.4), (21.0, 22.2), (19.7, 19.9))
    raw += _cubic((19.7, 19.9), (19.1, 18.8), (18.3, 18.5), (16.0, 18.5))
    raw += _cubic((16.0, 18.5), (13.7, 18.5), (12.9, 18.8), (12.3, 19.9))
    raw += _cubic((12.3, 19.9), (11.0, 22.2), (9.9, 23.4), (8.4, 23.4))
    raw += _cubic((8.4, 23.4), (6.6, 23.4), (4.8, 21.6), (4.6, 17.7))
    raw += _cubic((4.6, 17.7), (4.4, 12.4), (6.5, 9.3), (9.6, 9.3))
    return [(x * scale, y * scale) for x, y in raw]


def render(size: int) -> Image.Image:
    scale = CANVAS / 32.0
    tile = diagonal_gradient(CANVAS).convert("RGBA")

    # Phủ ánh sáng nhẹ phía trên giống #gh-sheen trong SVG.
    sheen = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    sheen_px = sheen.load()
    sheen_h = round(18 * scale)
    for y in range(sheen_h):
        alpha = round(56 * (1.0 - y / sheen_h))
        for x in range(CANVAS):
            sheen_px[x, y] = (255, 255, 255, alpha)
    tile = Image.alpha_composite(tile, sheen)

    mask = Image.new("L", (CANVAS, CANVAS), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, CANVAS - 1, CANVAS - 1), radius=round(CORNER_R * scale), fill=255
    )

    icon = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    icon.paste(tile, (0, 0), mask)

    # Viền sáng thuỷ tinh alpha-composite lên trên nền (tránh đè mất gradient).
    border = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    inset = 0.7 * scale
    ImageDraw.Draw(border).rounded_rectangle(
        (inset, inset, CANVAS - 1 - inset, CANVAS - 1 - inset),
        radius=round(7.3 * scale),
        outline=(255, 255, 255, 72),
        width=max(1, round(1.4 * scale)),
    )
    icon = Image.alpha_composite(icon, border)

    draw = ImageDraw.Draw(icon)

    # Thân tay cầm trắng
    draw.polygon(gamepad_polygon(scale), fill=(255, 255, 255, 255))

    # D-pad trái (#4338ca)
    dpad_color = (67, 56, 202, 255)
    draw.rounded_rectangle(
        (8.3 * scale, 13.35 * scale, 12.9 * scale, 15.05 * scale),
        radius=round(0.7 * scale),
        fill=dpad_color,
    )
    draw.rounded_rectangle(
        (9.75 * scale, 11.9 * scale, 11.45 * scale, 16.5 * scale),
        radius=round(0.7 * scale),
        fill=dpad_color,
    )

    # Thanh giữa (#a5b4fc)
    draw.rounded_rectangle(
        (14.7 * scale, 13.55 * scale, 17.3 * scale, 14.75 * scale),
        radius=round(0.6 * scale),
        fill=(165, 180, 252, 255),
    )

    # Hai nút bấm bên phải (#06b6d4 & #ec4899)
    for cx, cy, color in (
        (22.1, 12.8, (6, 182, 212, 255)),
        (19.6, 15.3, (236, 72, 153, 255)),
    ):
        r = 1.5 * scale
        draw.ellipse((cx * scale - r, cy * scale - r, cx * scale + r, cy * scale + r), fill=color)

    return icon.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    master = render(512)
    master.save(OUT / "apple-touch-icon.png")
    master.save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    for path in ("apple-touch-icon.png", "favicon.ico"):
        print(f"  {path}: {(OUT / path).stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
