"""Export the normalized Code conversation-relay mark to PNG and ICO."""

from pathlib import Path
from PIL import Image, ImageDraw


DESIGN_DIR = Path(__file__).resolve().parent
ROOT = DESIGN_DIR.parent.parent
ASSETS = ROOT / "assets"
BLACK_MARK_PNG = ASSETS / "code-logo-black.png"
WHITE_MARK_PNG = ASSETS / "code-logo-white.png"
ROOT_PNG = ROOT / "code-icon.png"
ROOT_ICO = ROOT / "code-icon.ico"
SCALE = 8
CANVAS = 64 * SCALE


def _arc_box(center_y, radius, scale):
    center_x = 32 * scale
    center_y *= scale
    radius *= scale
    return (
        round(center_x - radius),
        round(center_y - radius),
        round(center_x + radius),
        round(center_y + radius),
    )


def draw_mark(draw, color, scale=1.0, optical_small_size=False):
    """Draw the two exact semicircles from the 160-unit master grid."""
    # The 160-unit geometry is scaled into a 64-unit icon canvas.
    mark_scale = 0.31
    radius = 40 * mark_scale
    # Small system icons need a slightly wider negative-space gap so the two
    # halves do not merge after 16–24 px antialiasing. Exported logo assets keep
    # the exact R40/T14/54-distance master geometry.
    stroke_master = 13 if optical_small_size else 14
    upper_center = 60 if optical_small_size else 53
    lower_center = 100 if optical_small_size else 107
    stroke = max(1, round(stroke_master * mark_scale * scale))
    upper_y = 32 + (upper_center - 80) * mark_scale
    lower_y = 32 + (lower_center - 80) * mark_scale
    draw.arc(_arc_box(upper_y, radius, scale), start=-90, end=90, fill=color, width=stroke)
    draw.arc(_arc_box(lower_y, radius, scale), start=90, end=270, fill=color, width=stroke)


def render_app_icon(size=256):
    """Use the white mark on a black containment tile for OS-level icons."""
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (4 * SCALE, 4 * SCALE, 60 * SCALE, 60 * SCALE),
        radius=16 * SCALE,
        fill="#000000",
    )
    draw_mark(draw, "#FFFFFF", SCALE, optical_small_size=True)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def render_transparent_mark(color, size=256):
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw_mark(ImageDraw.Draw(image), color, SCALE)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    icon = render_app_icon(256)
    icon.save(ROOT_PNG, "PNG", optimize=True)
    render_transparent_mark("#000000").save(BLACK_MARK_PNG, "PNG", optimize=True)
    render_transparent_mark("#FFFFFF").save(WHITE_MARK_PNG, "PNG", optimize=True)
    icon.save(
        ROOT_ICO,
        format="ICO",
        sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40),
               (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    for path in (BLACK_MARK_PNG, WHITE_MARK_PNG, ROOT_PNG, ROOT_ICO):
        print(path)


if __name__ == "__main__":
    main()
