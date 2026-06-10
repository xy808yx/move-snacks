#!/usr/bin/env python3
"""Move Snacks mascot generator — single source of truth for the chibi lightning bolt.

The GRID below is the entire design. Run this script to regenerate:
  favicon-32.png, icon-192.png, icon-512.png, apple-touch-icon.png
and to print the inline-SVG rect groups (brand chip, done screen, data-URI favicon)
that get pasted into index.html.

  python3 tools/make-icons.py
"""
import os, sys, zlib, struct, urllib.parse

# ---------------------------------------------------------------- design
# 20x20 cells. '.' = empty. Only the bolt BODY (Y), face and slash are drawn
# by hand; the dark outline (K), top-left highlight (H) and bottom-right
# shade (D) are derived automatically so the silhouette stays easy to edit.
#   Y bolt gold   E eye (ink)   W eye shine   R rosy cheek   M mouth
#   B slash blue  C slash cyan
GRID = [
    "....................",
    "......YYYYYYYYY.....",
    "......YYYYYYYYY.....",
    ".....YYEEYYEEY......",
    ".....YYEEYYEEY......",
    ".....YRYYYYYRY......",
    "....YYYYMMYYY.......",
    "....YYYYTTYYY.......",
    "...YYYYYYYYYYYYYYY..",
    "....YYYYYYYYYYYYYY..",
    "..........YYYYYYY...",
    ".........YYYYYYY....",
    ".........YYYYYY.....",
    "........YYYYYY......",
    "........YYYYY.......",
    ".......YYYYY........",
    ".......YYYY.........",
    "......YYY...........",
    ".....YY.............",
    "....................",
]
# eye shine: drawn over the top-left pixel of each eye block
SHINES = [(7, 3), (11, 3)]
# speed streaks behind the bolt: list of ((x0,y0),(x1,y1)) segments, 2px tall
SLASH = [((1, 17), (4, 14)), ((15, 4), (18, 1))]

PAL = {
    "Y": (255, 210, 62),   # bolt body  #FFD23E
    "H": (255, 232, 148),  # highlight  #FFE894
    "D": (232, 150, 12),   # shade      #E8960C
    "K": (42, 33, 56),     # outline    #2A2138
    "E": (42, 33, 56),     # eyes (same ink)
    "W": (255, 255, 255),  # eye shine
    "R": (255, 157, 176),  # cheeks     #FF9DB0
    "M": (58, 30, 42),     # mouth      #3A1E2A
    "T": (255, 122, 147),  # tongue     #FF7A93
    "B": (74, 140, 255),   # slash blue #4A8CFF
    "C": (125, 232, 255),  # slash cyan #7DE8FF
}
BG = (255, 246, 234)       # icon tile background #FFF6EA
S = 20                     # grid size

BODY = set("YEWRMT")       # cells that count as bolt body (get outlined)

def build_cells():
    """Return {(x,y): key} fully resolved: slash, body, auto outline/shade/highlight."""
    cells = {}
    # 1. speed streaks behind everything
    for (x0, y0), (x1, y1) in SLASH:
        steps = max(abs(x1 - x0), abs(y1 - y0))
        for i in range(steps + 1):
            x = round(x0 + (x1 - x0) * i / steps)
            y = round(y0 + (y1 - y0) * i / steps)
            for yy, key in ((y, "C"), (y + 1, "B")):
                if 0 <= x < S and 0 <= yy < S:
                    cells[(x, yy)] = key
    # 2. body (overwrites slash where they overlap)
    grid = {}
    for y, row in enumerate(GRID):
        for x, ch in enumerate(row):
            if ch != ".":
                grid[(x, y)] = ch
                cells[(x, y)] = ch
    for x, y in SHINES:
        grid[(x, y)] = "W"; cells[(x, y)] = "W"
    # 3. auto outline: any non-body cell 4-adjacent to body -> K (wins over slash)
    for (x, y), ch in list(grid.items()):
        if ch in BODY:
            for nx, ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                if grid.get((nx, ny)) not in BODY and 0 <= nx < S and 0 <= ny < S:
                    cells[(nx, ny)] = "K"
    # 4. auto shade/highlight on plain gold cells along the body edge
    for (x, y), ch in grid.items():
        if ch != "Y":
            continue
        below = grid.get((x, y+1)) in BODY
        right = grid.get((x+1, y)) in BODY
        above = grid.get((x, y-1)) in BODY
        left  = grid.get((x-1, y)) in BODY
        if not below or not right:
            cells[(x, y)] = "D"      # bottom/right inner edge -> shade
        elif not above and left:
            cells[(x, y)] = "H"      # top inner edge -> highlight
    return cells

# ---------------------------------------------------------------- SVG out
def hexc(key):
    r, g, b = PAL[key]
    return "#%02X%02X%02X" % (r, g, b)

def svg_rects(cells):
    """Merge horizontal runs per color into compact <rect> groups."""
    by_color = {}
    for (x, y), key in sorted(cells.items(), key=lambda c: (c[0][1], c[0][0])):
        by_color.setdefault(hexc(key), []).append((x, y))
    groups = []
    for color, pts in by_color.items():
        pts = set(pts)
        rects = []
        for (x, y) in sorted(pts, key=lambda p: (p[1], p[0])):
            if (x, y) not in pts:
                continue
            w = 1
            while (x + w, y) in pts:
                pts.discard((x + w, y)); w += 1
            pts.discard((x, y))
            rects.append('<rect x="%d" y="%d" width="%d" height="1"/>' % (x, y, w))
        groups.append('<g fill="%s">%s</g>' % (color, "".join(rects)))
    return "".join(groups)

def svg_doc(cells, bg=None, rx=None):
    bgrect = ""
    if bg:
        bgrect = '<rect width="%d" height="%d"%s fill="%s"/>' % (
            S, S, (' rx="%s"' % rx) if rx else "", bg)
    return ('<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" '
            'shape-rendering="crispEdges">%s%s</svg>' % (S, S, bgrect, svg_rects(cells)))

# ---------------------------------------------------------------- PNG out
def write_png(path, size, cells, scale, bg=BG):
    art = S * scale
    off = (size - art) // 2
    px = [[bg] * size for _ in range(size)]
    for (x, y), key in cells.items():
        for dy in range(scale):
            for dx in range(scale):
                px[off + y*scale + dy][off + x*scale + dx] = PAL[key]
    try:
        from PIL import Image
        img = Image.new("RGB", (size, size))
        img.putdata([c for row in px for c in row])
        img.save(path, optimize=True)
    except ImportError:
        raw = b"".join(b"\x00" + bytes(v for c in row for v in c) for row in px)
        def chunk(tag, data):
            c = tag + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))
        png = (b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
        with open(path, "wb") as f:
            f.write(png)
    print("wrote %s (%dx%d, art %dpx)" % (path, size, size, art))

# ---------------------------------------------------------------- main
if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cells = build_cells()
    write_png(os.path.join(root, "favicon-32.png"), 32, cells, 1)
    write_png(os.path.join(root, "apple-touch-icon.png"), 180, cells, 8)
    write_png(os.path.join(root, "icon-192.png"), 192, cells, 7)
    write_png(os.path.join(root, "icon-512.png"), 512, cells, 20)
    write_png(os.path.join(root, "tools", "preview-512.png"), 512, cells, 22)

    print("\n--- inline SVG (brand chip / done screen; transparent bg) ---")
    print(svg_doc(cells))
    print("\n--- inline SVG with tile bg (brand chip style) ---")
    print(svg_doc(cells, bg="#FFF6EA"))
    print("\n--- data-URI favicon (rounded tile) ---")
    doc = svg_doc(cells, bg="#FFF6EA", rx="3.5")
    print("data:image/svg+xml," + urllib.parse.quote(doc, safe="/:=' "))
