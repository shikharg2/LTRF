#!/usr/bin/env python3
"""
Generate 15 static webpages, each ~5 MB, that load a variety of object types
at variable sizes. Every object is a real, browser-loadable file so the page
actually fetches ~5 MB of resources when opened.

Object types produced:
  - BMP images        (24-bit, browser-renderable)
  - PNG images        (valid, zlib-compressed uncompressed blocks -> big files)
  - WAV audio         (PCM, browser-playable)
  - SVG vector art    (inline-referenced, renderable)
  - CSS stylesheets
  - JS scripts
  - JSON data         (fetched via <script> loader)
  - TTF-ish font blob (referenced via @font-face; falls back gracefully)
  - Binary blob       (fetched via XHR)
  - Plain text        (fetched)

Run:  python3 generate.py
Output: ./webpages/page-01.html ... page-15.html  +  ./webpages/assets/<page>/...
"""

import os
import struct
import zlib
import random

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webpages")
ASSETS = os.path.join(ROOT, "assets")
TARGET = 5 * 1024 * 1024  # 5 MiB per page

# ----------------------------------------------------------------------------
# Individual object generators. Each returns the number of bytes written.
# ----------------------------------------------------------------------------

def _fill_pattern(n, seed):
    """Deterministic pseudo-random-ish bytes without exhausting entropy."""
    rnd = random.Random(seed)
    return bytes(rnd.getrandbits(8) for _ in range(n))


def gen_bmp(path, target, seed=0):
    """Write a valid 24-bit BMP of approximately `target` bytes."""
    width = 256
    rowsize = ((width * 3 + 3) // 4) * 4
    height = max(1, (target - 54) // rowsize)
    pixels_size = rowsize * height
    filesize = 54 + pixels_size

    rnd = random.Random(seed)
    # BMP file header (14) + DIB header (40)
    fh = b"BM" + struct.pack("<IHHI", filesize, 0, 0, 54)
    dib = struct.pack("<IiiHHIIiiII",
                      40, width, height, 1, 24, 0, pixels_size, 2835, 2835, 0, 0)
    with open(path, "wb") as f:
        f.write(fh)
        f.write(dib)
        # Write a gradient + noise pattern row by row.
        base = bytearray(rowsize)
        for y in range(height):
            for x in range(width):
                i = x * 3
                base[i] = (x + y) & 0xFF
                base[i + 1] = (x * 2 + rnd.getrandbits(4)) & 0xFF
                base[i + 2] = (y * 3) & 0xFF
            f.write(base)
    return filesize


def gen_png(path, target, seed=0):
    """Write a valid PNG. Uses a truecolor image sized to hit ~target bytes."""
    # Estimate pixels: PNG here stores near-random data so compression ~1:1.
    # bytes/pixel = 3, plus 1 filter byte per row. Pick square-ish dims.
    approx_pixels = max(16, target // 3)
    width = max(1, int(approx_pixels ** 0.5))
    height = max(1, approx_pixels // width)

    rnd = random.Random(seed)
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type 0 (none)
        raw.extend(rnd.getrandbits(8) for _ in range(width * 3))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 6)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
           chunk(b"IDAT", idat) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


def gen_wav(path, target, seed=0):
    """Write a valid 16-bit mono PCM WAV of ~target bytes."""
    sample_rate = 44100
    n_samples = max(1, (target - 44) // 2)
    data_size = n_samples * 2
    rnd = random.Random(seed)

    with open(path, "wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate,
                            sample_rate * 2, 2, 16))
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        # A tone with drifting frequency + a little noise.
        import math
        buf = bytearray()
        freq = 220.0 + (seed % 8) * 55.0
        for i in range(n_samples):
            v = int(12000 * math.sin(2 * math.pi * freq * i / sample_rate))
            v += rnd.randint(-800, 800)
            v = max(-32768, min(32767, v))
            buf += struct.pack("<h", v)
            if len(buf) >= 1 << 16:
                f.write(buf)
                buf = bytearray()
        f.write(buf)
    return 44 + data_size


def gen_svg(path, target, seed=0):
    """Write a valid SVG with many shapes to reach ~target bytes."""
    rnd = random.Random(seed)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600" '
             'viewBox="0 0 800 600">']
    parts.append('<rect width="800" height="600" fill="#0b1021"/>')
    size = len(parts[0]) + len(parts[1])
    i = 0
    while size < target - 20:
        x, y = rnd.randint(0, 800), rnd.randint(0, 600)
        r = rnd.randint(2, 40)
        c = f"#{rnd.randint(0,0xFFFFFF):06x}"
        if i % 3 == 0:
            s = f'<circle cx="{x}" cy="{y}" r="{r}" fill="{c}" opacity="0.6"/>'
        elif i % 3 == 1:
            s = (f'<rect x="{x}" y="{y}" width="{r*2}" height="{r}" '
                 f'fill="{c}" transform="rotate({rnd.randint(0,90)} {x} {y})"/>')
        else:
            s = (f'<line x1="{x}" y1="{y}" x2="{rnd.randint(0,800)}" '
                 f'y2="{rnd.randint(0,600)}" stroke="{c}" stroke-width="2"/>')
        parts.append(s)
        size += len(s)
        i += 1
    parts.append("</svg>")
    data = "".join(parts)
    with open(path, "w") as f:
        f.write(data)
    return len(data.encode())


def gen_css(path, target, seed=0):
    rnd = random.Random(seed)
    parts = [":root{--brand:#4f8cff;}\nbody{font-family:sans-serif;}\n"]
    size = len(parts[0])
    i = 0
    while size < target:
        c1 = f"#{rnd.randint(0,0xFFFFFF):06x}"
        c2 = f"#{rnd.randint(0,0xFFFFFF):06x}"
        s = (f".g{i}{{background:linear-gradient(45deg,{c1},{c2});"
             f"padding:{rnd.randint(1,40)}px;margin:{rnd.randint(1,20)}px;"
             f"border-radius:{rnd.randint(0,24)}px;"
             f"box-shadow:0 {rnd.randint(1,8)}px {rnd.randint(4,24)}px {c1};}}\n")
        parts.append(s)
        size += len(s)
        i += 1
    data = "".join(parts)
    with open(path, "w") as f:
        f.write(data)
    return len(data.encode())


def gen_js(path, target, seed=0):
    rnd = random.Random(seed)
    parts = ["// generated script module\n"
             "export const DATA = [\n"]
    size = len(parts[0])
    i = 0
    while size < target - 60:
        s = (f'  {{id:{i},k:"item_{rnd.randint(0,1<<30):x}",'
             f'v:{rnd.random():.9f},t:{rnd.randint(0,1<<40)}}},\n')
        parts.append(s)
        size += len(s)
        i += 1
    parts.append("];\nexport function sum(){return DATA.reduce((a,b)=>a+b.v,0);}\n")
    data = "".join(parts)
    with open(path, "w") as f:
        f.write(data)
    return len(data.encode())


def gen_json(path, target, seed=0):
    rnd = random.Random(seed)
    with open(path, "w") as f:
        f.write('{"records":[')
        size = 12
        i = 0
        first = True
        while size < target - 20:
            rec = ('' if first else ',') + \
                  (f'{{"id":{i},"name":"rec_{rnd.randint(0,1<<28):x}",'
                   f'"score":{rnd.random():.6f},'
                   f'"tags":["{rnd.randint(0,999)}","{rnd.randint(0,999)}"]}}')
            f.write(rec)
            size += len(rec)
            first = False
            i += 1
        f.write(']}')
        size += 2
    return size


def gen_font(path, target, seed=0):
    """Write a blob with a TTF signature. Not a fully valid font (browser will
    reject glyphs), but it is a real downloaded object referenced via
    @font-face, contributing to page weight like a real font would."""
    data = b"\x00\x01\x00\x00" + _fill_pattern(max(0, target - 4), seed)
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def gen_bin(path, target, seed=0):
    data = _fill_pattern(target, seed)
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def gen_txt(path, target, seed=0):
    rnd = random.Random(seed)
    words = ["lorem", "ipsum", "dolor", "sit", "amet", "consectetur",
             "adipiscing", "elit", "sed", "do", "eiusmod", "tempor"]
    parts = []
    size = 0
    while size < target:
        line = " ".join(rnd.choice(words) for _ in range(12)) + "\n"
        parts.append(line)
        size += len(line)
    data = "".join(parts)
    with open(path, "w") as f:
        f.write(data)
    return len(data.encode())


# ----------------------------------------------------------------------------
# Page composition
# ----------------------------------------------------------------------------

# (type key, generator, file extension, how it is referenced in HTML)
TYPES = {
    "bmp":  (gen_bmp,  "bmp",  "img"),
    "png":  (gen_png,  "png",  "img"),
    "wav":  (gen_wav,  "wav",  "audio"),
    "svg":  (gen_svg,  "svg",  "img"),
    "css":  (gen_css,  "css",  "css"),
    "js":   (gen_js,   "js",   "js"),
    "json": (gen_json, "json", "fetch"),
    "font": (gen_font, "ttf",  "font"),
    "bin":  (gen_bin,  "bin",  "fetch"),
    "txt":  (gen_txt,  "txt",  "fetch"),
}


def plan_objects(page_idx):
    """Return a list of (typekey, target_bytes) summing to ~TARGET.

    Each page uses a different mix and different variable object sizes.
    """
    rnd = random.Random(1000 + page_idx)
    all_keys = list(TYPES.keys())
    # Every page includes at least one of several core visual/audio types,
    # then a rotating emphasis so the 15 pages differ.
    rnd.shuffle(all_keys)
    # Emphasis: pick 3-4 types this page leans on.
    n_types = rnd.randint(6, len(all_keys))
    chosen = all_keys[:n_types]
    # Ensure a renderable image type is always present.
    if not any(k in chosen for k in ("bmp", "png", "svg")):
        chosen[0] = "bmp"

    objects = []
    remaining = TARGET
    # Number of objects varies per page -> "variable object sizes".
    n_objects = rnd.randint(8, 22)
    for i in range(n_objects):
        k = rnd.choice(chosen)
        # Give each object a variable slice of what's left.
        if i == n_objects - 1:
            size = remaining
        else:
            # Random fraction of remaining, bounded so we don't run out early.
            hi = max(1, remaining - (n_objects - i - 1) * 8 * 1024)
            lo = min(hi, 8 * 1024)
            size = rnd.randint(lo, max(lo, int(hi * 0.5)))
        size = max(2 * 1024, size)
        objects.append((k, size))
        remaining -= size
        if remaining <= 8 * 1024:
            break
    # If we still have a shortfall, pad with a final binary blob.
    used = sum(s for _, s in objects)
    if used < TARGET:
        objects.append(("bin", TARGET - used))
    return objects


def build_page(page_idx):
    page_name = f"page-{page_idx:02d}"
    page_dir = os.path.join(ASSETS, page_name)
    os.makedirs(page_dir, exist_ok=True)

    objects = plan_objects(page_idx)
    manifest = []  # (typekey, relpath, bytes)

    for i, (k, size) in enumerate(objects):
        gen, ext, _ref = TYPES[k]
        fname = f"{k}-{i:02d}.{ext}"
        fpath = os.path.join(page_dir, fname)
        written = gen(fpath, size, seed=page_idx * 100 + i)
        rel = f"assets/{page_name}/{fname}"
        manifest.append((k, rel, written))

    html = render_html(page_idx, manifest)
    html_path = os.path.join(ROOT, f"{page_name}.html")
    with open(html_path, "w") as f:
        f.write(html)

    total = sum(b for _, _, b in manifest) + len(html.encode())
    return page_name, total, manifest


def render_html(page_idx, manifest):
    page_name = f"page-{page_idx:02d}"

    imgs, audios, css_links, js_srcs, fetches, fonts = [], [], [], [], [], []
    for k, rel, b in manifest:
        ref = TYPES[k][2]
        if ref == "img":
            imgs.append((rel, b, k))
        elif ref == "audio":
            audios.append((rel, b))
        elif ref == "css":
            css_links.append(rel)
        elif ref == "js":
            js_srcs.append(rel)
        elif ref == "font":
            fonts.append(rel)
        elif ref == "fetch":
            fetches.append((rel, b, k))

    def kb(n):
        return f"{n/1024:.0f} KB" if n < 1024 * 1024 else f"{n/1024/1024:.2f} MB"

    total = sum(b for _, _, b in manifest)

    css_tags = "\n".join(f'  <link rel="stylesheet" href="{c}">'
                         for c in css_links)
    font_faces = "\n".join(
        f'    @font-face {{ font-family: "GenFont{i}"; '
        f'src: url("{fp}") format("truetype"); font-display: swap; }}'
        for i, fp in enumerate(fonts))

    img_tags = "\n".join(
        f'      <figure class="obj"><img loading="eager" src="{rel}" '
        f'alt="{k} object" width="256">'
        f'<figcaption>{k.upper()} &middot; {kb(b)}</figcaption></figure>'
        for rel, b, k in imgs)

    audio_tags = "\n".join(
        f'      <figure class="obj"><audio controls preload="auto" '
        f'src="{rel}"></audio><figcaption>WAV &middot; {kb(b)}</figcaption>'
        f'</figure>' for rel, b in audios)

    js_tags = "\n".join(f'  <script type="module" src="{src}"></script>'
                        for src in js_srcs)

    # Data objects fetched at runtime.
    fetch_list = ", ".join(
        f'{{url:"{rel}",type:"{k}",bytes:{b}}}' for rel, b, k in fetches)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page_name} — ~{total/1024/1024:.2f} MB object load test</title>
{css_tags}
<style>
  {font_faces}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:#0b1021; color:#e6ecff;
         font-family:"GenFont0", system-ui, sans-serif; }}
  header {{ padding:24px; background:linear-gradient(135deg,#12204a,#0b1021);
           border-bottom:1px solid #24345f; }}
  h1 {{ margin:0 0 6px; font-size:22px; }}
  .meta {{ opacity:.7; font-size:13px; }}
  main {{ padding:20px; }}
  .grid {{ display:grid; gap:16px;
          grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); }}
  .obj {{ margin:0; padding:12px; background:#141a33; border:1px solid #24345f;
         border-radius:12px; text-align:center; }}
  .obj img {{ max-width:100%; height:auto; border-radius:6px; }}
  figcaption {{ margin-top:8px; font-size:12px; opacity:.8; }}
  section h2 {{ font-size:16px; margin:24px 0 12px; }}
  #status {{ font-size:13px; opacity:.85; white-space:pre-wrap;
            background:#141a33; padding:12px; border-radius:8px;
            border:1px solid #24345f; }}
</style>
</head>
<body>
<header>
  <h1>{page_name} &mdash; object load test (~{total/1024/1024:.2f} MB)</h1>
  <div class="meta">{len(manifest)} objects &middot; variable sizes &middot;
    types: images, audio, css, js, json, fonts, binary, text</div>
</header>
<main>
  <section>
    <h2>Rendered visual objects</h2>
    <div class="grid">
{img_tags}
{audio_tags}
    </div>
  </section>

  <section>
    <h2>Runtime-fetched data objects</h2>
    <div id="status">loading fetched objects…</div>
  </section>
</main>

{js_tags}
<script>
  const FETCHES = [{fetch_list}];
  const status = document.getElementById("status");
  let loaded = 0, bytes = 0;
  const t0 = performance.now();
  Promise.all(FETCHES.map(o =>
    fetch(o.url).then(r => r.arrayBuffer()).then(buf => {{
      loaded++; bytes += buf.byteLength;
      status.textContent =
        `fetched ${{loaded}}/${{FETCHES.length}} objects, ` +
        `${{(bytes/1024/1024).toFixed(2)}} MB of runtime data`;
    }}).catch(e => {{ status.textContent += "\\nerror: " + o.url; }})
  )).then(() => {{
    const dt = (performance.now() - t0).toFixed(0);
    status.textContent +=
      `\\nall runtime objects loaded in ${{dt}} ms. ` +
      `total page weight ≈ {total/1024/1024:.2f} MB.`;
  }});
</script>
</body>
</html>
"""


def main():
    os.makedirs(ASSETS, exist_ok=True)
    print(f"Target per page: {TARGET/1024/1024:.2f} MB\n")
    grand = 0
    index_rows = []
    for idx in range(1, 16):
        name, total, manifest = build_page(idx)
        grand += total
        counts = {}
        for k, _, _ in manifest:
            counts[k] = counts.get(k, 0) + 1
        mix = ", ".join(f"{k}×{v}" for k, v in sorted(counts.items()))
        print(f"{name}: {total/1024/1024:5.2f} MB  ({len(manifest)} objs)  {mix}")
        index_rows.append((name, total, len(manifest), mix))

    # Build an index page linking all 15.
    rows = "\n".join(
        f'    <li><a href="{n}.html">{n}</a> &mdash; '
        f'{t/1024/1024:.2f} MB, {c} objects <span class="mix">{m}</span></li>'
        for n, t, c, m in index_rows)
    index = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>15 object-load test pages (~5 MB each)</title>
<style>
 body{{font-family:system-ui,sans-serif;background:#0b1021;color:#e6ecff;
      max-width:820px;margin:40px auto;padding:0 20px;}}
 h1{{font-size:24px;}} a{{color:#7fb0ff;}}
 li{{margin:10px 0;line-height:1.5;}}
 .mix{{display:block;opacity:.6;font-size:12px;}}
</style></head>
<body>
<h1>15 static webpages &mdash; ~5 MB each</h1>
<p>Each page loads a different mix of object types at variable sizes.
Total across all pages: {grand/1024/1024:.1f} MB.</p>
<ul>
{rows}
</ul>
</body></html>
"""
    with open(os.path.join(ROOT, "index.html"), "w") as f:
        f.write(index)

    print(f"\nTotal generated: {grand/1024/1024:.1f} MB across 15 pages")
    print(f"Output dir: {ROOT}")
    print(f"Open: {os.path.join(ROOT, 'index.html')}")


if __name__ == "__main__":
    main()
