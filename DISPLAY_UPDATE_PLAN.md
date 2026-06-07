# Display Updates: Behavior, Findings, and Research Directions

A reference for improving e-ink render quality — **clarity** (no smudging/ghosting),
**latency**, and **precision** (crisp lines/text). It records how the panel is driven
today, what investigation has established, and the open directions worth exploring.
No direction is chosen here; this is a map, not a decision.

## Current behavior

- **Render:** `getImage` composes an 825×1200 **`'L'` (8-bit grayscale)** image
  (panes → tiles → chrome), rotated 180°.
- **Throttle:** `Display` keeps only the latest frame; a background thread pushes at
  most **one update per second**.
- **Cadence:** the runner's main loop ticks every 1 s and on data changes. The header
  clock shows **seconds**, so something changes essentially every second.
- **Diff & dispatch (`EInkDisplay.update`):** computes a **single union bounding box**
  of changed pixels vs. the previous frame; if either dimension exceeds 50 px it does
  a full-frame update, otherwise a cropped partial.

### Waveforms by circumstance

| Circumstance | Waveform |
|---|---|
| Boot / init clear | **GC16** (full, clears ghosting) |
| Hourly clear (`minute == 0`, ≥ ~58 min since last) | **GLR16** (full) |
| Normal change, diff ≤ 50 px in both dims | **DU** (partial, cropped to bbox) |
| Normal change > 50 px, or first frame | **DU** (full) |

Steady-state operation is almost entirely **DU**; GC16 only at boot, GLR16 only at the
hourly clear.

### Dirty-region sizing

- One **union bbox** = `ImageChops.difference(prev, cur).getbbox()` over the whole
  composited frame, with a **50 px escalation** to full-frame.
- Computed on the **final image, not per pane** — so two small changes in distant
  regions (clock + a train minute) form one large union box that usually escalates to
  a full-screen DU.

## Root cause of the quality issues

Symptoms: **fuzzy** text/icons and **ghosting/smudge**. The rendered image itself is
crisp (debug PNGs confirm); the degradation is in **panel presentation**, from
pushing **anti-aliased grayscale content through `DU`**, a ~2-level waveform:

- DU resolves only black/white, so anti-aliased gray edges threshold unpredictably →
  **fuzz**.
- DU never fully resets pixels → residue accumulates between clears → **ghosting**.

These are **two independent axes**: per-frame fuzz (content↔waveform mismatch) and
temporal ghosting (accumulates over time; needs a periodic full clear). A fix for one
does not fix the other.

## Established findings

- **No regression to recover.** The deployed predecessor and current `main` share an
  **identical display pipeline** (driver, cadence, waveforms, seconds-in-clock). There
  is no lost/hand-tuned configuration; improving this is forward design.
- **Nothing in the current UI needs grayscale.** All 197 icons are monochrome line art
  (no gradients, no opacity, only black fill). The only gray anywhere is anti-aliasing.
- **GLR16 for full updates is too noisy** (tried on hardware): the 16-level grayscale
  flash on a full-screen refresh is visually disruptive. Rejected as the full-update
  waveform.
- **Whole-frame binarize works but is blunt** (tried on branch `crisp-1bit-rendering`):
  thresholding the final frame to pure black/white made text/icons crisper *and* made
  DU full updates quiet (no grayscale to flash). But it only tunes stroke **weight**
  (not smoothness — jagged curves remain), and doing it in the render boundary
  **globally locks the render to B&W**. Set aside, not adopted; branch retained for
  reference.

## Research directions

Grouped by what they target. None are mutually exclusive; several compose.

### A. Match content to the waveform (per-frame fuzz / precision)

| # | Direction | Trade-off | Depends on |
|---|---|---|---|
| A1 | **Binarize content** (threshold, no dither) | blunt — weight only, can't fix jagged curves | choice of locus (B) |
| A2 | **Render crisp at the source** — mode-`'1'` tiles and/or a **bitmap/pixel font** for small text | asset work; native `'1'` text can be chunky for some fonts | a 1-bit-friendly font |
| A3 | **16-level waveform** (GC16/GL16) for grayscale content | full-screen is noisy (see findings) | per-region application (D1) |
| A4 | **Mid quantization** (DU4, 4 levels) | smoother than binary, less noisy than 16-level | panel DU4 support (unverified) |

### B. Where the 1-bit / output mapping lives (render lock-in)

| # | Direction | Trade-off |
|---|---|---|
| B1 | Map at the **render boundary** (`getImage`) | simplest, but locks the render scheme to B&W (current binarize) |
| B2 | Map at the **display boundary** (`EInkDisplay` output adapter) — render stays grayscale/device-independent, 1-bit is this panel's output mapping | debug PNG ≠ panel unless mirrored; goldens stay grayscale (they test composition, not device adaptation) |
| B3 | **Per-pane color mode** (`monochrome` flag) — color depth is a pane property | needs per-pane handling (the tile substrate already provides it) |

### C. Reduce temporal ghosting (smudge over time)

| # | Direction | Trade-off |
|---|---|---|
| C1 | **Periodic full GC16 flush** (every N min / N partials; today the periodic clear is GLR16) | occasional flash; cadence needs tuning |
| C2 | **Cut clock churn** — drop seconds, or repaint only the seconds glyph | far fewer DU updates → slower ghost buildup; losing seconds is a UX/product call |
| C3 | **GLR16 / Regal anti-ghost for content** | rejected full-screen (noisy); possibly viable per-region |

### D. Targeted updates (latency + enabler)

| # | Direction | Trade-off |
|---|---|---|
| D1 | **Per-pane dirty regions + update classes** (replace the union bbox) | real machinery (rect↔rotation mapping, multiple `draw_partial`, per-pane signatures); the **keystone** that makes B3, A3/C3-per-region, and per-pane waveforms viable |
| D2 | **1bpp transfer / `spi_hz` / VCOM calibration** | transfer-latency and contrast wins; signal-integrity / stability risk |
| D3 | **A2 for tiny frequent partials** | fastest, but more ghosting; not latency-bound at 1 Hz, so low priority today |

**Synergy.** D1 is the enabler: with per-pane update classes, monochrome panes can use
1-bit + DU (crisp, fast) while a grayscale pane uses a 16-level waveform on **its own
rect only** — a small localized flash instead of the noisy full-screen GLR16. One
coherent (not chosen) end-state: per-pane update classes + a periodic GC16 flush for
ghosting + crisp small text via a pixel font.

## How to evaluate any direction

- **Latency timing** — wrap `draw_full`/`draw_partial` with `perf_counter`; log ms per
  update type; also wall-clock "data-change → panel updated."
- **Ghosting soak** — alternate two frames ×K under the candidate config, flush to
  white, **photograph residual ink** (rate 0–5).
- **Precision macro photo** — hold one text-heavy frame; macro photo; compare edge
  crispness.
- **One-hour live soak** — run the real service for an hour; photograph end-state smudge
  (this is the temporal-ghosting axis).
- **Flash-annoyance count** — instrument and count full-flash events per minute.
- **Golden regression gate** — waveform/transfer-only changes leave the rendered image
  unchanged → `pytest tests/golden` stays green. Content changes (binarize, drop-seconds)
  change the image → re-baseline and eyeball. (The binarize re-baseline was verified
  benign: only anti-aliased pixels changed, 0 structural, across all 24 scenarios.)

## What's been tried

| Attempt | Result |
|---|---|
| GLR16 for full updates | Rejected — full-screen grayscale flash too noisy |
| Whole-frame binarize (`crisp-1bit-rendering`) | Crisper + quiet DU full updates, but blunt and globally locks the render to B&W; set aside |
| A2 for frequent partials | Deferred — not latency-bound at 1 Hz; adds ghosting |

## Open questions

- Which `DisplayModes` the 9.7" IT8951 actually supports (A2 / DU4 / GL16 / GLD16) —
  print `constants.DisplayModes` and cross-check the Waveshare mode-declaration spec.
- Correct **VCOM** for this panel vs. the value on its flex-cable sticker.
- Is a **per-region** 16-level refresh acceptable, given a full-screen one is not?
- The predecessor and current `main` share an identical pipeline, yet the new build was
  perceived as worse. Unresolved — perception, larger per-frame diffs, or temporal
  ghosting (aging)? Capture a like-for-like A/B if it recurs.
