# Enhancement log

Dated notes from the daily improvement loop. Newest first.

## 2026-10-21 — wrapper v1.1.0

- **`--doctor`**: reports exiftool / qpdf / gs / c2patool / Python / upstream git SHA and ready/degraded status.
- **`--verify-text`**: Ghostscript `txtwrite` SHA-256 fingerprint before/after; flags `CHECK` if content extract changes.
- **Outline check**: compares qpdf outline/bookmark tree size when available.
- **Collision-safe outputs**: second clean of the same stem becomes `name.cleaned.2.pdf` instead of overwriting.
- **`--update-upstream`**: fast-forward pull of `watermarks-remover/`.
- **Richer `report.json`**: UTC timestamp, wrapper version, OK/CHECK/ERROR summary.
- **Progress**: `[i/n]` while processing batches.
- **Self-tests**: `test_clean_pdfs.py` (doctor, AI-tagged clean, broken skip, unique dest).
- **Docs**: root `README.md`.
- **Daily loop**: armed to wake every 24h and ship the next enhancement.
- **Upstream sync**: pulled `watermarks-remover` `258cf20` → `980c0b4` (DeepSeek bench, frontmatter/relationship XML hardening).
- **Publish policy**: after each enhancement, commit and push to GitHub as **Dipak Yadav (`dipak5501`) only** — no co-authors.

## 2026-10-05 — wrapper v1.0

- Gentler default (no forced Ghostscript rebuild).
- Page-count + qpdf integrity verification.
- Skip unreadable “PDFs”.
- `--check` / `--thorough` / `report.json`.
- Installed local `c2patool` 0.27.22 via GitHub release.
