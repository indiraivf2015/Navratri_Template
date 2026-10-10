# Navratri Creative Studio · Indira IVF

A static, in-browser studio. Each person uploads a photo, picks a design, types their name and designation, and downloads a personalised Navratri greeting as a PNG. The page uses the same simple layout as the World Mental Health Day studio.

Photos and text stay in the browser. Nothing is uploaded to a server.

## What you get

- **Two official designs**, chosen from the Design dropdown in the photo card. The choice is remembered on that device.
  - **Diya & Dandiya:** round photo inside the pink ring. Prints name (in capitals), designation and location.
  - **Maa Durga:** square photo inside the gold border. Prints name and designation.
- The photo fills the **exact printed frame**. The ring or border stays on top, so it is never covered.
- Drag to position the photo. Zoom with the slider or the mouse wheel.
- Printed placeholders ("DR. NAME", "Your Name", "Designation | Location") disappear only for the lines you fill in.
- Downloads at the artwork's native size: 1122×1402 for Diya & Dandiya, 1024×1536 for Maa Durga.
- Optional Excel / ZIP batch mode, off by default.

## Run it

Needs Python 3 on the PATH.

```bat
start.bat
```

That serves the folder at **http://127.0.0.1:8767/** and opens it. It must be served over HTTP, not opened as a file, because the canvas reads the artwork back. Hard-refresh after editing the HTML.

## Deploy

Any static host works. `vercel.json` already rewrites `/` to the studio page. Hard-refresh after a deploy so browsers drop the old page.

## Files

| Path | Role |
|---|---|
| `Indira_Creative_Studio.html` | The whole app: page, theme and canvas drawing |
| `index.html` | Redirects into the studio |
| `templates/navratri-diya.png`, `navratri-durga.png` | Artwork as printed, shown before text is typed |
| `templates/navratri-*-clean.png` | Same artwork with the placeholder text painted out |
| `templates/header-durga.png`, `favicon.png` | Header mark and tab icon, cut from the official artwork |
| `tools/src/*-source.png` | The two official templates, untouched |
| `tools/prepare_navratri.py` | Builds everything in `templates/` from `tools/src/` |
| `start.bat` | Local server |
| `vercel.json` | Host rewrite |

## Rebuilding the artwork

```bat
python tools/prepare_navratri.py
```

The script needs Pillow and NumPy. It does four things.

1. **Removes the stats strip** at the foot of each design and blends the background over it. The image size stays the same.
2. **Builds the clean artwork.** It finds the placeholder text, including its soft halo, and fills it in from the surrounding background. It then adds back matching grain so the patch does not look smooth.
3. **Fits each photo window** to the grey placeholder printed inside the frame. It then checks two things:
   - no placeholder grey is left outside the window, so there is no grey halo;
   - no ring or border pixel falls inside it, so the frame stays whole.
   It prints `PASS` or `FAIL` per design, plus the window values that go into `PLATES`.
4. **Cuts the header mark:** the Durga motif shown in the round header badge, plus the tab icon.

## Geometry (`PLATES` in the HTML)

All values are native template pixels. Measure them on the new artwork; never copy them from another design.

```js
{
  id: 'diya',
  hole: { type: 'ellipse', cx: 561, cy: 737.5, rx: 201, ry: 199.5 },   // or { type: 'rrect', x, y, w, h, r }
  cx: 562,                                                             // centre line of both text lines
  name:  { baseline: 1004, size: 46, weight: 800, fill: '#D9073F', upper: true, maxW: 640 },
  line2: { baseline: 1046, size: 33, weight: 500, fill: '#14213A', maxW: 620,
           loc: { required: true, bar: { fill: '#DC0F45', w: 2, top: -25, h: 30, gap: 16 } } },
  patch: [ [432, 954, 692, 1012], [380, 1012, 746, 1064] ]             // clean-art boxes: name line, line two
}
```

- **hole:** the photo window. It is the fitted grey placeholder, grown just enough to cover the grey's antialiased rim: 1.5px for the circle and 1px for the square. Take these numbers from the script output.
- **name / line2:** baseline, size, weight and colour match the printed placeholder text. Long text shrinks until it fits `maxW`.
- **line2.loc:** present only when the design prints a location. `required: true` keeps Download disabled until a location is typed. `bar` is the pink divider drawn between designation and location.
- **patch:** boxes copied from the clean artwork when that line has text. Outside the painted-out text the clean artwork matches the original, so generous boxes are safe.

## How drawing works

1. The photo is scaled to cover the window, then clipped to it plus `CLIP_BLEED` (1.5px).
2. The artwork, with the window punched out, is drawn on top. The printed ring or border therefore sits over the photo's edge, with no seam.
3. For each filled line, the matching box of clean artwork replaces the printed placeholder.
4. Name and line two are drawn centred in Figtree.
5. The preview scales this down. Download saves it at native size.

## Reuse for another festival

1. Put the new official templates in `tools/src/`.
2. In `tools/prepare_navratri.py`, update `PLATES`:
   - the source file names;
   - the text boxes around each placeholder line;
   - a search box around the photo frame;
   - the window `shape` and `grow`.
3. Run the script until every window check passes. Then check the clean artwork at 300% zoom for smudges.
4. In the HTML, update `PLATES`, `VERSION`, the page copy and the colour tokens.
5. Type a short and a long name on each design, then download and check the PNGs.

## Excel batch (optional)

Set `EXCEL_ENABLE = true` in the HTML. The sheet needs a **Name** column (or Employee Name / Doctor Name), plus **Employee ID** and/or **Document Name** (the photo's file name). Designation and location columns are optional. Photos match when the file name equals Document Name or contains the Employee ID.
