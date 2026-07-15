# Bird Assets

Bird illustration PNGs in `assets/birds/illustrations/` are runtime assets for
the BirdNET screens and are stored with Git LFS.

Fetch the real image bytes after cloning:

```bash
git lfs install
git lfs pull
```

If these files are still Git LFS pointer text, the app can keep running, but bird
screens fall back to missing-art placeholders.

## Provenance

These illustrations were created by Sam Broner with Gemini image generation for
this project. The art direction is black-and-white Thomas Bewick-style wood
engraving, chosen for legibility on grayscale e-ink.
This repo keeps the curated runtime assets needed by the display; generation
working files and QA scratch output are not required at runtime.
