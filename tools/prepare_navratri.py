"""Build every image the Navratri Creative Studio needs from the two official
Indira IVF Navratri templates.

Run from the project root:

    python tools/prepare_navratri.py

Inputs (tools/src):
    navratri-diya-source.png   template 1, 1122 x 1402, pink-ringed photo circle
    navratri-durga-source.png  template 2, 1024 x 1536, gold-bordered photo square

Outputs (templates/):
    navratri-<id>.png        the artwork, untouched (shown before text is typed)
    navratri-<id>-clean.png  the artwork with the printed placeholder text removed
    header-durga.png         Durga eyes / bindi / nath motif for the round header mark
    favicon.png              64 px tab icon

The script also fits the photo window of each template to the grey placeholder
that is printed inside the frame, and checks that:
    * no placeholder grey is left outside the window (no grey halo), and
    * no ring / border pixel falls inside it (the printed frame stays whole).
It prints the window and text values that belong in PLATES in the HTML.
Requires Pillow and NumPy.
"""
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "src"
OUT = ROOT / "templates"

# Native-pixel boxes [x0, y0, x1, y1) around each printed placeholder line.
# They are generous on purpose: the masking step only touches real text pixels.
PLATES = {
    "diya": {
        "src": "navratri-diya-source.png",
        "text_boxes": [(440, 962, 684, 1010), (388, 1014, 738, 1058)],
        # text-vs-paper colour distance that counts as ink, and mask growth
        "ink": 9, "spread": 4, "grain": 1.0,
        "window_search": (330, 500, 792, 980),
        "shape": "ellipse",
        # pink ring starts ~8 px outside the grey disc
        "grow": 1.5,
    },
    "durga": {
        "src": "navratri-durga-source.png",
        # the name box starts below the red flower ornament (ends at row 1268)
        # so the fill never borrows its colour
        "text_boxes": [(404, 1274, 620, 1311), (428, 1311, 600, 1351)],
        # this artwork gives its lettering a soft light halo; catch it too
        "ink": 7, "spread": 4, "grain": 0.5,
        "window_search": (398, 1026, 626, 1236),
        "shape": "rrect",
        # gold border sits only ~2 px outside the grey panel
        "grow": 1.0,
    },
}

# "grow" above: extra native pixels the punched window reaches past the fitted
# grey edge, so the grey's antialiased rim is covered by the photo. It must stay
# smaller than the gap to the printed frame; verify_window() checks both.


def load(name):
    return np.asarray(Image.open(SRC / name).convert("RGB")).astype(np.float64)


def save_rgb(arr, path, **kw):
    Image.fromarray(np.clip(arr + 0.5, 0, 255).astype(np.uint8), "RGB").save(path, **kw)


def save_rgba(rgb, alpha, path):
    out = np.dstack([np.clip(rgb + 0.5, 0, 255), np.clip(alpha * 255 + 0.5, 0, 255)]).astype(np.uint8)
    Image.fromarray(out, "RGBA").save(path, optimize=True)


def dilate(mask, px):
    img = Image.fromarray((mask * 255).astype(np.uint8))
    return np.asarray(img.filter(ImageFilter.MaxFilter(px * 2 + 1))) > 0


def blur(arr, radius):
    chans = [np.asarray(Image.fromarray(np.clip(arr[..., c], 0, 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(radius))).astype(np.float64) for c in range(3)]
    return np.dstack(chans)


# --------------------------------------------------------------------------
# Placeholder text removal
# --------------------------------------------------------------------------
def text_mask(img, box, ink):
    """Pixels inside box that differ from the background interpolated between
    the clean rows just above and just below the box."""
    x0, y0, x1, y1 = box
    top = img[y0 - 4:y0 - 1, x0:x1].mean(0)
    bot = img[y1 + 1:y1 + 4, x0:x1].mean(0)
    t = np.linspace(0, 1, y1 - y0)[:, None, None]
    bg = top[None] * (1 - t) + bot[None] * t
    diff = np.abs(img[y0:y1, x0:x1] - bg).sum(2)
    mask = np.zeros(img.shape[:2], bool)
    mask[y0:y1, x0:x1] = diff > ink
    return mask


def inpaint(img, mask, iters=900):
    """Harmonic fill: start from a column-wise blend, then repeatedly replace
    every masked pixel by the mean of its four neighbours. Unmasked pixels act
    as fixed boundary values, so the fill meets the artwork seamlessly."""
    out = img.copy()
    ys, xs = np.nonzero(mask)
    y0, y1, x0, x1 = ys.min() - 2, ys.max() + 3, xs.min() - 2, xs.max() + 3
    sub = out[y0:y1, x0:x1]
    m = mask[y0:y1, x0:x1]
    # initial guess: per column, blend the first clean pixel above and below
    for cx in range(sub.shape[1]):
        col = m[:, cx]
        if not col.any():
            continue
        rows = np.nonzero(col)[0]
        a, b = rows.min() - 1, rows.max() + 1
        for ry in rows:
            w = (ry - a) / max(1, (b - a))
            sub[ry, cx] = sub[a, cx] * (1 - w) + sub[b, cx] * w
    for _ in range(iters):
        nb = (np.roll(sub, 1, 0) + np.roll(sub, -1, 0) + np.roll(sub, 1, 1) + np.roll(sub, -1, 1)) / 4
        sub[m] = nb[m]
    out[y0:y1, x0:x1] = sub
    return out


def add_grain(clean, orig, mask, seed, amount=1.0):
    """Copy the artwork's fine grain into the filled pixels so the patch does
    not read as an unnaturally smooth smear."""
    # High-pass of the already-filled image, so the dark text (and the bright
    # halo a blur leaves beside it) never leaks into the grain. Sample only
    # plain, low-saturation paper well clear of the text and of any ornament.
    hp = clean - blur(clean, 1.5)
    sat = orig.max(2) - orig.min(2)
    ring = dilate(mask, 22) & ~dilate(mask, 8) & (sat < 30)
    pool = np.clip(hp[ring], -8, 8)
    if len(pool) == 0:
        return clean
    pool = pool - pool.mean(0)
    rng = np.random.default_rng(seed)
    picks = pool[rng.integers(0, len(pool), int(mask.sum()))]
    out = clean.copy()
    out[mask] += picks * amount
    return out


def build_clean(pid, img):
    cfg = PLATES[pid]
    mask = np.zeros(img.shape[:2], bool)
    for b in cfg["text_boxes"]:
        mask |= text_mask(img, b, cfg["ink"])
    mask = dilate(mask, cfg["spread"])
    clean = inpaint(img, mask)
    clean = add_grain(clean, img, mask, seed=7, amount=cfg["grain"])
    return clean, mask


# --------------------------------------------------------------------------
# Photo window fitting and verification
# --------------------------------------------------------------------------
def placeholder_mask(img, search, shape):
    x0, y0, x1, y1 = search
    sub = img[y0:y1, x0:x1]
    mean = sub.mean(2)
    sat = sub.max(2) - sub.min(2)
    if shape == "ellipse":
        # flat light grey disc (about 220, 218, 219)
        m = (sat < 12) & (mean > 200) & (mean < 236)
    else:
        # light grey panel (about 241) plus the darker person silhouette
        m = (sat < 9) & (mean > 150) & (mean < 247)
    full = np.zeros(img.shape[:2], bool)
    full[y0:y1, x0:x1] = m
    # keep the component around the search centre: drop stray specks by
    # requiring a solid neighbourhood
    solid = np.asarray(Image.fromarray((full * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(5))) > 0
    keep = dilate(solid, 3) & full
    return keep


def frame_mask(img, shape):
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    if shape == "ellipse":
        return (r - g > 60) & (r > 170)          # pink ring
    return (r > 190) & (r - b > 90) & (b < 150)  # gold border


def shape_coverage(shape, p, h, w, ss=4):
    """Fraction of every pixel inside the analytic shape (supersampled)."""
    ys = (np.arange(h * ss) + 0.5) / ss
    xs = (np.arange(w * ss) + 0.5) / ss
    X, Y = np.meshgrid(xs, ys)
    if shape == "ellipse":
        cx, cy, rx, ry = p
        inside = ((X - cx) / rx) ** 2 + ((Y - cy) / ry) ** 2 <= 1
    else:
        x, y, ww, hh, rr = p
        qx = np.abs(X - (x + ww / 2)) - (ww / 2 - rr)
        qy = np.abs(Y - (y + hh / 2)) - (hh / 2 - rr)
        d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - rr
        inside = d <= 0
    return inside.reshape(h, ss, w, ss).mean((1, 3))


def fit_window(img, pid):
    cfg = PLATES[pid]
    shape = cfg["shape"]
    pm = placeholder_mask(img, cfg["window_search"], shape)
    ys, xs = np.nonzero(pm)
    # pixel i covers [i, i+1); the grey's outer antialias pixel is half-covered
    x0, x1 = xs.min(), xs.max() + 1
    y0, y1 = ys.min(), ys.max() + 1
    if shape == "ellipse":
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
        # refine the radii against the mask area row by row
        best = None
        for drx in np.arange(-1.5, 1.6, 0.25):
            for dry in np.arange(-1.5, 1.6, 0.25):
                p = (cx, cy, rx + drx, ry + dry)
                sx0, sy0, sx1, sy1 = cfg["window_search"]
                cov = shape_coverage(shape, (p[0] - sx0, p[1] - sy0, p[2], p[3]), sy1 - sy0, sx1 - sx0, ss=2)
                err = np.abs(cov - pm[sy0:sy1, sx0:sx1]).sum()
                if best is None or err < best[0]:
                    best = (err, p)
        params = best[1]
    else:
        best = None
        for rr in np.arange(4, 16.5, 0.5):
            p = (x0, y0, x1 - x0, y1 - y0, rr)
            sx0, sy0, sx1, sy1 = cfg["window_search"]
            cov = shape_coverage(shape, (p[0] - sx0, p[1] - sy0, p[2], p[3], p[4]), sy1 - sy0, sx1 - sx0, ss=2)
            err = np.abs(cov - pm[sy0:sy1, sx0:sx1]).sum()
            if best is None or err < best[0]:
                best = (err, p)
        params = best[1]
    return params, pm


def grow(shape, p, g):
    if shape == "ellipse":
        cx, cy, rx, ry = p
        return (cx, cy, rx + g, ry + g)
    x, y, w, h, r = p
    return (x - g, y - g, w + 2 * g, h + 2 * g, r + g)


def verify_window(img, pid, params, pm):
    cfg = PLATES[pid]
    shape = cfg["shape"]
    h, w = img.shape[:2]
    win = grow(shape, params, cfg["grow"])
    cov = shape_coverage(shape, win, h, w, ss=4)
    # Any placeholder pixel must be (almost) fully inside the window.
    leftover = pm & (cov < 0.98)
    # The frame must stay outside: count frame pixels the window would eat.
    fm = frame_mask(img, shape)
    eaten = fm & (cov > 0.02)
    ok = leftover.sum() == 0 and eaten.sum() == 0
    # Margin between the window edge and the inner edge of the frame.
    return ok, int(leftover.sum()), int(eaten.sum()), win


# --------------------------------------------------------------------------
# Header assets
# --------------------------------------------------------------------------
def ink_alpha(rgb, lo, hi, bg=255.0):
    """Alpha from how far a pixel is from white paper, with the colour
    un-premultiplied so it keeps its true hue on any background."""
    d = (bg - rgb).max(2)
    a = np.clip((d - lo) / (hi - lo), 0, 1)
    safe = np.maximum(a, 1e-3)[..., None]
    col = bg - (bg - rgb) / safe
    col = np.clip(col, 0, 255)
    col[a == 0] = 255
    return col, a


def trim(rgb, a, pad=4):
    ys, xs = np.nonzero(a > 0.02)
    y0, y1 = max(0, ys.min() - pad), min(a.shape[0], ys.max() + 1 + pad)
    x0, x1 = max(0, xs.min() - pad), min(a.shape[1], xs.max() + 1 + pad)
    return rgb[y0:y1, x0:x1], a[y0:y1, x0:x1]


def resize_rgba(rgb, a, height):
    img = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), a * 255]).astype(np.uint8), "RGBA")
    # premultiplied resampling avoids dark fringes
    pm = img.convert("RGBa")
    k = height / img.height
    pm = pm.resize((max(1, round(img.width * k)), height), Image.LANCZOS)
    return pm.convert("RGBA")


def build_header_assets(durga):
    # Durga eyes, tilak, bindi, nath and lips. The faint peach mandala behind
    # them sits well under the alpha threshold and drops out.
    face = durga[228:528, 360:668]
    col, a = ink_alpha(face, 70, 150)
    col, a = trim(col, a)
    resize_rgba(col, a, 240).save(OUT / "header-durga.png", optimize=True)

    # Favicon: the face on a cream disc.
    fav = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    yy, xx = np.mgrid[0:256, 0:256]
    dd = np.clip(124 - np.hypot(xx - 127.5, yy - 127.5), 0, 1)
    disc = Image.fromarray((dd * 255).astype(np.uint8))
    fav.paste(Image.new("RGBA", (256, 256), (255, 248, 238, 255)), (0, 0), disc)
    face_img = Image.open(OUT / "header-durga.png")
    k = 200 / max(face_img.size)
    face_img = face_img.resize((round(face_img.width * k), round(face_img.height * k)), Image.LANCZOS)
    fav.alpha_composite(face_img, ((256 - face_img.width) // 2, (256 - face_img.height) // 2 + 6))
    fav.resize((64, 64), Image.LANCZOS).save(OUT / "favicon.png", optimize=True)


def main():
    OUT.mkdir(exist_ok=True)
    report_ok = True
    for pid, cfg in PLATES.items():
        img = load(cfg["src"])
        h, w = img.shape[:2]
        save_rgb(img, OUT / f"navratri-{pid}.png", optimize=True)
        clean, mask = build_clean(pid, img)
        save_rgb(clean, OUT / f"navratri-{pid}-clean.png", optimize=True)

        params, pm = fit_window(img, pid)
        ok, leftover, eaten, win = verify_window(img, pid, params, pm)
        report_ok &= ok
        print(f"[{pid}] {w}x{h}  text pixels cleared: {int(mask.sum())}")
        print(f"[{pid}] fitted {cfg['shape']}: {tuple(round(float(v), 2) for v in params)}")
        print(f"[{pid}] window (+{cfg['grow']}px): {tuple(round(float(v), 2) for v in win)}")
        print(f"[{pid}] grey left outside window: {leftover}   frame pixels inside window: {eaten}   -> {'PASS' if ok else 'FAIL'}")

    durga = load(PLATES["durga"]["src"])
    build_header_assets(durga)
    print("ALL WINDOW CHECKS PASS" if report_ok else "WINDOW CHECK FAILED")
    return 0 if report_ok else 1


if __name__ == "__main__":
    sys.exit(main())
