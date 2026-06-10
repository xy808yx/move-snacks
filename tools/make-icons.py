#!/usr/bin/env python3
"""Move Snacks brand assets — single source of truth for the logo and Champ.

Two designs live here:

1. MODERN LOGO (smooth vector, not pixel art): a rounded lightning bolt in
   gold on the brand pink->orange gradient tile. Used for the header brand
   chip, the SVG data-URI favicon, and every PNG icon (favicon-32,
   apple-touch-icon, icon-192, icon-512), rendered with PIL at high
   resolution and downscaled for clean anti-aliasing.

2. PIXEL CHAMP: the celebration mascot that stamps in when you finish a
   snack. Hand-drawn 24x28 grid below — big happy face, pink sweatband,
   raised victory fists, tapering bolt tail, twinkle sparkles.

Run:  python3 tools/make-icons.py
  - writes favicon-32.png, apple-touch-icon.png, icon-192.png, icon-512.png
  - writes tools/icon-preview.png + tools/champ-preview.png (eyeball checks)
  - patches index.html in place: favicon data-URI, brand chip SVG, done SVG
"""
import math, os, re, sys, urllib.parse
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ================================================================ modern logo
# Bolt polygon in a 48x48 design space: flat top, right shelf spike, long
# tail to a bottom-left tip. (x, y, corner_radius) per vertex, clockwise.
BOLT = [
    (22.0,  3.0, 3.0),   # top-left corner of the flat top edge
    (38.0,  3.0, 3.0),   # top-right corner
    (27.0, 22.0, 2.5),   # inner corner where head meets the right shelf
    (40.0, 22.0, 2.5),   # right spike point
    (14.0, 45.0, 2.5),   # bottom tip
    (20.0, 27.0, 2.5),   # inner corner above the tip
    ( 8.0, 27.0, 2.5),   # left spike point
]
TILE_TOP, TILE_BOT = (255, 94, 126), (255, 157, 92)    # #FF5E7E -> #FF9D5C
GOLD_TOP, GOLD_BOT = (255, 240, 174), (255, 198, 40)   # #FFF0AE -> #FFC628
SHADOW_RGBA = (122, 16, 54)                            # soft plum shadow
DS = 48.0                                              # design space size


def _norm(vx, vy):
    d = math.hypot(vx, vy) or 1.0
    return vx / d, vy / d


def bolt_segments(scale=1.0):
    """Rounded-corner outline as (line_to, ctrl, curve_to) triples, scaled
    about the design-space center."""
    cx = cy = DS / 2
    pts = [((x - cx) * scale + cx, (y - cy) * scale + cy, r * scale)
           for x, y, r in BOLT]
    segs = []
    n = len(pts)
    for i, (x, y, r) in enumerate(pts):
        px, py, _ = pts[(i - 1) % n]
        nx, ny, _ = pts[(i + 1) % n]
        ix, iy = _norm(x - px, y - py)
        ox, oy = _norm(nx - x, ny - y)
        segs.append(((x - ix * r, y - iy * r), (x, y), (x + ox * r, y + oy * r)))
    return segs


def bolt_svg_path(scale=1.0):
    f = lambda v: ("%.2f" % v).rstrip("0").rstrip(".")
    d = []
    for i, (p1, c, p2) in enumerate(bolt_segments(scale)):
        d.append(("M" if i == 0 else "L") + f(p1[0]) + " " + f(p1[1]))
        d.append("Q" + f(c[0]) + " " + f(c[1]) + " " + f(p2[0]) + " " + f(p2[1]))
    return "".join(d) + "Z"


def bolt_points(scale, px_scale, steps=16):
    """Flattened polygon points in pixel space for PIL."""
    pts = []
    for p1, c, p2 in bolt_segments(scale):
        for s in range(steps):
            t = s / float(steps)
            x = (1 - t) ** 2 * p1[0] + 2 * (1 - t) * t * c[0] + t ** 2 * p2[0]
            y = (1 - t) ** 2 * p1[1] + 2 * (1 - t) * t * c[1] + t ** 2 * p2[1]
            pts.append((x * px_scale, y * px_scale))
    return pts


def _gradient(size, top, bot, diagonal=False):
    n = 128
    g = Image.new("RGB", (n, n))
    px = []
    for y in range(n):
        for x in range(n):
            t = (x + y) / (2.0 * (n - 1)) if diagonal else y / float(n - 1)
            px.append(tuple(int(a + (b - a) * t + .5) for a, b in zip(top, bot)))
    g.putdata(px)
    return g.resize((size, size), Image.Resampling.BILINEAR)


def render_icon(size, bolt_scale, rounded=False):
    """Render the modern logo tile at `size` px (master 1536, downscaled)."""
    M = 1536
    s = M / DS
    tile = _gradient(M, TILE_TOP, TILE_BOT, diagonal=True)

    # soft shadow under the bolt
    mask = Image.new("L", (M, M), 0)
    ImageDraw.Draw(mask).polygon(bolt_points(bolt_scale, s), fill=255)
    sh = mask.transform((M, M), Image.Transform.AFFINE,
                        (1, 0, -M * 0.000, 0, 1, -M * 0.016))
    sh = sh.filter(ImageFilter.GaussianBlur(M * 0.016)).point(lambda v: v * 0.30)
    tile.paste(Image.new("RGB", (M, M), SHADOW_RGBA), (0, 0), sh)

    # gold gradient bolt, mapped across the bolt's own vertical extent
    ys = [p[1] for p in bolt_points(bolt_scale, s)]
    y0, y1 = min(ys), max(ys)
    gold = _gradient(M, GOLD_TOP, GOLD_BOT).transform(
        (M, M), Image.Transform.AFFINE,
        (1, 0, 0, 0, (y1 - y0) / M, y0))
    tile.paste(gold, (0, 0), mask)

    if rounded:
        a = Image.new("L", (M, M), 0)
        ImageDraw.Draw(a).rounded_rectangle([0, 0, M - 1, M - 1],
                                            radius=M * 0.225, fill=255)
        tile = tile.convert("RGBA")
        tile.putalpha(a)
    out = tile.resize((size, size), Image.Resampling.LANCZOS)
    return out


def logo_svg(rx=None, shadow=True, cls=None):
    """Inline SVG for the brand chip (square tile, CSS rounds it) or the
    favicon (rx baked in)."""
    c = ' class="%s"' % cls if cls else ""
    rxa = ' rx="%s"' % rx if rx else ""
    sh = ('<path d="%s" transform="translate(0 1.3)" fill="#7A1036" '
          'opacity=".22"/>' % bolt_svg_path(0.86)) if shadow else ""
    return (
        '<svg%s viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" '
        'aria-hidden="true">'
        '<defs>'
        '<linearGradient id="lgT" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#FF5E7E"/><stop offset="1" stop-color="#FF9D5C"/>'
        '</linearGradient>'
        '<linearGradient id="lgB" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#FFF0AE"/><stop offset="1" stop-color="#FFC628"/>'
        '</linearGradient>'
        '</defs>'
        '<rect width="48" height="48"%s fill="url(#lgT)"/>'
        '%s'
        '<path d="%s" fill="url(#lgB)"/>'
        '</svg>' % (c, rxa, sh, bolt_svg_path(0.86))
    )


# ================================================================ pixel champ
# 24x28 grid. '.' empty.  Y gold  P/O sweatband (pink/orange)  E eye  W shine
# R cheek  M mouth  T tongue  C cyan sparkle  p pink twinkle dot
# Outline (K), highlight (H) and shade (D) are derived automatically.
CHAMP = [
    "..........................",
    "......YYYYYYYYYYYYYY......",
    ".....PPPPPPPPPPPPPPPP.....",
    ".....OOOOOOOOOOOOOOOO.....",
    ".....YYYYYYYYYYYYYYYY.....",
    ".....YYYYYYYYYYYYYYYY.....",
    ".....YYYYWEYYYYWEYYYY.....",
    ".....YYYYEEYYYYEEYYYY.....",
    ".....YYYYEEYYYYEEYYYY.....",
    ".C...YRRYYYMMMMYYYRRY..p..",
    "CCC..YYYYYYMTTMYYYYYY.....",
    ".C...YYYYYYYYYYYYYYYY.....",
    ".....YYYYYYYYYYYYYYYY.....",
    ".........YYYYYYYYYYYYYYY..",
    ".........YYYYYYYYYYYYY....",
    "........YYYYYYYYYYY.......",
    "........YYYYYYYYY....C....",
    "....p..YYYYYYYY.....CCC...",
    ".......YYYYYY........C....",
    "......YYYYY...............",
    ".....YYYY.................",
    ".....YY...................",
    "..........................",
    "..........................",
]
CW, CH = 26, 24

CPAL = {
    "Y": "#FFD23E", "H": "#FFE894", "D": "#E8960C", "K": "#2A2138",
    "E": "#2A2138", "W": "#FFFFFF", "R": "#FF9DB0", "M": "#3A1E2A",
    "T": "#FF7A93", "P": "#FF5E7E", "O": "#FF9D5C",
    "C": "#7DE8FF", "p": "#FF5E7E",
}
BODY = set("YHDEWRMTPO")
SPARK = set("Cp")


def champ_cells():
    """Resolve grid -> ({(x,y):key} body incl. outline/shade, sparkA, sparkB)."""
    grid = {}
    for y, row in enumerate(CHAMP):
        assert len(row) == CW, "row %d is %d chars" % (y, len(row))
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            assert ch in CPAL, "unknown char %r" % ch
            grid[(x, y)] = ch
    body = {k: v for k, v in grid.items() if v in BODY}
    cells = dict(body)
    # outer outline: any empty cell 4-adjacent to body -> K
    for (x, y) in list(body):
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (nx, ny) not in body and 0 <= nx < CW and 0 <= ny < CH:
                cells[(nx, ny)] = "K"
    # shade / highlight on plain gold cells along the silhouette
    for (x, y), ch in body.items():
        if ch != "Y":
            continue
        below = (x, y + 1) in body
        right = (x + 1, y) in body
        above = (x, y - 1) in body
        left = (x - 1, y) in body
        if not below or not right:
            cells[(x, y)] = "D"
        elif not above and left:
            cells[(x, y)] = "H"
    # sparkles, split into two groups for alternating CSS twinkle
    sparkA, sparkB = {}, {}
    for (x, y), ch in grid.items():
        if ch in SPARK:
            (sparkA if x > CW // 2 else sparkB)[(x, y)] = ch
    return cells, sparkA, sparkB


def runs(cellmap):
    """Merge horizontal runs per color -> {hex: [(x, y, w), ...]}."""
    by = {}
    for (x, y), key in cellmap.items():
        by.setdefault(CPAL[key], set()).add((x, y))
    out = {}
    for color, pts in by.items():
        rects = []
        for (x, y) in sorted(pts, key=lambda p: (p[1], p[0])):
            if (x, y) not in pts:
                continue
            w = 1
            while (x + w, y) in pts:
                pts.discard((x + w, y))
                w += 1
            pts.discard((x, y))
            rects.append((x, y, w))
        out[color] = rects
    return out


def rect_group(color, rects):
    body = "".join('<rect x="%d" y="%d" width="%d" height="1"/>' % r
                   for r in rects)
    return '<g fill="%s">%s</g>' % (color, body)


def champ_svg():
    cells, sparkA, sparkB = champ_cells()
    g = "".join(rect_group(c, r) for c, r in sorted(runs(cells).items()))
    a = "".join(rect_group(c, r) for c, r in sorted(runs(sparkA).items()))
    b = "".join(rect_group(c, r) for c, r in sorted(runs(sparkB).items()))
    return ('<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" '
            'shape-rendering="crispEdges">%s'
            '<g class="spkA">%s</g><g class="spkB">%s</g></svg>'
            % (CW, CH, g, a, b))


def champ_preview(path, scale=18):
    cells, sparkA, sparkB = champ_cells()
    pad = 24
    img = Image.new("RGB", (CW * scale + pad * 2, CH * scale + pad * 2),
                    (255, 246, 234))
    d = ImageDraw.Draw(img)
    for cm in (cells, sparkA, sparkB):
        for (x, y), key in cm.items():
            h = CPAL[key].lstrip("#")
            col = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
            d.rectangle([pad + x * scale, pad + y * scale,
                         pad + (x + 1) * scale - 1, pad + (y + 1) * scale - 1],
                        fill=col)
    img.save(path, optimize=True)
    print("wrote", path)


# ================================================================ html patch
def patch_index(favicon_uri, chip, done):
    p = os.path.join(ROOT, "index.html")
    with open(p) as f:
        html = f.read()
    subs = [
        (r'<link rel="icon" type="image/svg\+xml" href="data:image/svg\+xml,[^"]*">',
         '<link rel="icon" type="image/svg+xml" href="%s">' % favicon_uri),
        (r'(<span class="logo">)<svg.*?</svg>',
         lambda m: m.group(1) + chip),
        (r'(<div class="done-bolt" id="doneBolt"[^>]*>\s*)<svg.*?</svg>',
         lambda m: m.group(1) + done),
    ]
    for pat, rep in subs:
        html, n = re.subn(pat, rep, html, count=1, flags=re.S)
        assert n == 1, "anchor not found: %s" % pat[:60]
    with open(p, "w") as f:
        f.write(html)
    print("patched index.html (favicon, brand chip, done champ)")


# ================================================================ main
if __name__ == "__main__":
    # PNG icons — full-bleed squares for PWA/touch (maskable-safe bolt),
    # rounded with alpha for the 32px favicon.
    for name, size, scale, rounded in [
        ("favicon-32.png",       32,  0.92, True),
        ("apple-touch-icon.png", 180, 0.84, False),
        ("icon-192.png",         192, 0.78, False),
        ("icon-512.png",         512, 0.78, False),
    ]:
        render_icon(size, scale, rounded).save(os.path.join(ROOT, name),
                                               optimize=True)
        print("wrote", name)
    render_icon(512, 0.84, True).save(
        os.path.join(ROOT, "tools", "icon-preview.png"), optimize=True)
    print("wrote tools/icon-preview.png")

    champ_preview(os.path.join(ROOT, "tools", "champ-preview.png"))

    fav = "data:image/svg+xml," + urllib.parse.quote(
        logo_svg(rx=11, shadow=True), safe="/:=' ")
    if "--no-patch" not in sys.argv:
        patch_index(fav, logo_svg(shadow=True, cls="bolt"), champ_svg())
