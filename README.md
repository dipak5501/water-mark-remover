# Water mark remover (local PDF wrapper)

Local wrapper around [guillaumemeyer/watermarks-remover](https://github.com/guillaumemeyer/watermarks-remover) for stripping AI/provenance **metadata** from PDFs you own.

Originals are never modified. Cleaned copies go to `pdfs-out/`.

## Quick start

```bash
./clean_pdfs.sh --doctor          # verify tools
./clean_pdfs.sh --check file.pdf  # report markers only
./clean_pdfs.sh file.pdf          # clean → pdfs-out/
./clean_pdfs.sh                   # everything in pdfs-in/
```

## Options

| Flag | Meaning |
| --- | --- |
| `-c` / `--check` | Inspect only; write nothing |
| `-o DIR` | Output folder (default `pdfs-out/`) |
| `-r` | Recurse into folders |
| `--thorough` | Ghostscript deep image rebuild (may recompress) |
| `--verify-text` | Fail if extracted text changes after clean |
| `--doctor` | Print tool versions / readiness |
| `--update-upstream` | `git pull --ff-only` on `watermarks-remover/` |

## What it removes

Document Info, XMP, C2PA content credentials, generator tags, and attachment metadata — when present.

## What it does **not** remove

- Visible stamps / logos on the page
- Statistical wording watermarks (SynthID-class text)
- Anything that would make “AI-written” undetectable to style checkers

A clean file is **not** proof the content was never AI-assisted. Use only on files you own or are authorized to process.

## Verify

```bash
./clean_pdfs.sh --doctor
python3 test_clean_pdfs.py
```

## Setup note

`watermarks-remover/` is cloned locally (gitignored). After clone:

```bash
git clone https://github.com/guillaumemeyer/watermarks-remover.git
# install qpdf, ghostscript, exiftool, c2patool into .tools/ (see ENHANCEMENT_LOG)
```

## Daily enhancements

Enhanced daily; each change is committed and pushed as **Dipak Yadav** only. See `ENHANCEMENT_LOG.md`.
