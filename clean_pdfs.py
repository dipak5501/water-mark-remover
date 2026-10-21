#!/usr/bin/env python3
"""Strip AI/provenance metadata from PDFs using watermarks-remover.

Cleaned copies are written to an output folder; originals are never modified.
Each output is verified (page count unchanged, qpdf structural check passes,
no AI/C2PA markers left, optional text extract match) and a summary plus
report.json are produced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "watermarks-remover" / "service" / "scripts"
TOOLS_BIN = ROOT / ".tools" / "env" / "bin"
DEFAULT_IN = ROOT / "pdfs-in"
DEFAULT_OUT = ROOT / "pdfs-out"
REQUIRED_TOOLS = ("exiftool", "qpdf", "gs", "c2patool")
VERSION = "1.1.0"


def env() -> dict[str, str]:
    e = dict(os.environ)
    e["PATH"] = f"{TOOLS_BIN}{os.pathsep}{e.get('PATH', '')}"
    return e


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, env=env(), timeout=timeout)


def run_json(script: str, *args: str) -> dict:
    r = run([sys.executable, str(SCRIPTS / script), "--json", *args], timeout=600)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"error": (r.stderr or r.stdout).strip() or f"rc={r.returncode}"}


def tool_version(name: str) -> str | None:
    if not shutil.which(name, path=env()["PATH"]):
        return None
    flags = {
        "exiftool": ["-ver"],
        "qpdf": ["--version"],
        "gs": ["--version"],
        "c2patool": ["--version"],
    }
    r = run([name, *flags[name]])
    line = (r.stdout or r.stderr).strip().splitlines()
    return line[0] if line else "present"


def page_count(pdf: Path) -> int | None:
    r = run(["qpdf", "--show-npages", str(pdf)])
    try:
        return int(r.stdout.strip())
    except ValueError:
        return None


def outline_count(pdf: Path) -> int | None:
    """Count outline (bookmark) destinations via qpdf JSON, if available."""
    r = run(["qpdf", "--json", "--json-key=outlines", str(pdf)])
    if r.returncode not in (0, 3) or not r.stdout.strip():
        return None
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None

    def walk(node) -> int:
        if isinstance(node, list):
            return sum(walk(x) for x in node)
        if isinstance(node, dict):
            n = 1 if any(k in node for k in ("title", "Title", "dest", "/Title")) else 0
            for v in node.values():
                n += walk(v)
            return n
        return 0

    outlines = data.get("outlines") or data.get("qpdf") or data
    return walk(outlines)


def qpdf_ok(pdf: Path) -> bool:
    # rc 0 = clean, 3 = warnings only; both mean the file is readable.
    r = run(["qpdf", "--check", str(pdf)])
    return r.returncode in (0, 3)


def text_fingerprint(pdf: Path) -> str | None:
    """Ghostscript text extract hashed — detects content loss after clean."""
    if not shutil.which("gs", path=env()["PATH"]):
        return None
    with tempfile.TemporaryDirectory(prefix="wm-txt-") as td:
        out = Path(td) / "page.txt"
        r = run([
            "gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=txtwrite",
            f"-sOutputFile={out}", str(pdf),
        ], timeout=300)
        if r.returncode != 0 or not out.exists():
            return None
        return hashlib.sha256(out.read_bytes()).hexdigest()


def markers(report: dict) -> list[str]:
    found = []
    if report.get("has_c2pa") or report.get("still_has_c2pa"):
        found.append("C2PA")
    if report.get("has_ai_metadata") or report.get("still_has_ai_metadata"):
        found.append("AI metadata")
    if report.get("suspicious_total"):
        found.append(f"{report['suspicious_total']} invisible chars")
    return found


def collect(paths: list[str], recursive: bool) -> list[Path]:
    pdfs: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            it = p.rglob("*") if recursive else p.iterdir()
            pdfs += sorted(
                f for f in it
                if f.is_file() and f.suffix.lower() == ".pdf"
                and not f.name.endswith(".cleaned.pdf")
            )
        elif p.is_file():
            pdfs.append(p)
        else:
            print(f"warning: not found: {p}", file=sys.stderr)
    return pdfs


def unique_dest(out_dir: Path, stem: str) -> Path:
    """Avoid clobbering when two inputs share the same basename."""
    dest = out_dir / f"{stem}.cleaned.pdf"
    if not dest.exists():
        return dest
    n = 2
    while True:
        cand = out_dir / f"{stem}.cleaned.{n}.pdf"
        if not cand.exists():
            return cand
        n += 1


def process(pdf: Path, out_dir: Path, check_only: bool, thorough: bool,
            verify_text: bool) -> dict:
    row: dict = {"file": str(pdf)}
    if page_count(pdf) is None and not qpdf_ok(pdf):
        row.update(status="ERROR", detail="not a readable PDF; skipped")
        return row
    before = run_json("inspect_file.py", str(pdf))
    if "error" in before:
        row.update(status="ERROR", detail=before["error"])
        return row
    row["before"] = markers(before)
    row["findings"] = [
        f.get("label", f) if isinstance(f, dict) else f
        for f in before.get("findings", [])
    ]
    row["pages"] = page_count(pdf)
    row["outlines"] = outline_count(pdf)
    text_before = text_fingerprint(pdf) if verify_text else None
    if check_only:
        row["status"] = "MARKED" if row["before"] else "NONE FOUND"
        return row

    dest = unique_dest(out_dir, pdf.stem)
    cleaned = run_json(
        "clean_file.py", str(pdf), "-o", str(dest),
        "--deep-images", "always" if thorough else "auto",
        "--clean-attachments", "always",
    )
    if "error" in cleaned or not dest.exists():
        row.update(status="ERROR", detail=cleaned.get("error", "no output written"))
        return row

    after = run_json("inspect_file.py", str(dest))
    row.update(
        output=str(dest),
        after=markers(after) + markers(cleaned),
        actions=cleaned.get("actions", []),
        pages_after=page_count(dest),
        outlines_after=outline_count(dest),
        valid=qpdf_ok(dest),
        size_in=pdf.stat().st_size,
        size_out=dest.stat().st_size,
    )
    problems = []
    if row["pages"] != row["pages_after"]:
        problems.append(f"page count changed {row['pages']} -> {row['pages_after']}")
    if not row["valid"]:
        problems.append("qpdf structural check failed")
    if row["after"]:
        problems.append("residual: " + ", ".join(sorted(set(row["after"]))))
    if (
        row["outlines"] is not None
        and row["outlines_after"] is not None
        and row["outlines"] != row["outlines_after"]
    ):
        problems.append(
            f"outline count changed {row['outlines']} -> {row['outlines_after']}"
        )
    if verify_text and text_before:
        text_after = text_fingerprint(dest)
        row["text_match"] = text_after == text_before
        if text_after is None:
            problems.append("could not extract text from cleaned PDF")
        elif text_after != text_before:
            problems.append("extracted text differs from original")
    row["status"] = "CHECK" if problems else "OK"
    row["detail"] = "; ".join(problems)
    return row


def kb(n: int | None) -> str:
    return "-" if n is None else f"{n / 1024:.0f}K"


def doctor() -> int:
    print(f"watermarks-remover local wrapper v{VERSION}")
    print(f"ROOT: {ROOT}")
    print(f"scripts: {SCRIPTS} {'OK' if SCRIPTS.is_dir() else 'MISSING'}")
    print(f"tools PATH: {TOOLS_BIN}")
    print()
    ok = True
    for name in REQUIRED_TOOLS:
        ver = tool_version(name)
        if ver:
            print(f"  {name:10} {ver}")
        else:
            print(f"  {name:10} MISSING")
            ok = False
    py = sys.version.split()[0]
    print(f"  {'python':10} {py}")
    upstream = ROOT / "watermarks-remover"
    if (upstream / ".git").is_dir():
        r = subprocess.run(
            ["git", "-C", str(upstream), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True,
        )
        branch = subprocess.run(
            ["git", "-C", str(upstream), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True,
        )
        print(f"  {'upstream':10} {branch.stdout.strip()}@{r.stdout.strip()}")
    print()
    print("Status:", "ready" if ok and SCRIPTS.is_dir() else "degraded")
    return 0 if ok and SCRIPTS.is_dir() else 1


def update_upstream() -> int:
    upstream = ROOT / "watermarks-remover"
    if not (upstream / ".git").is_dir():
        print("watermarks-remover is not a git checkout", file=sys.stderr)
        return 1
    before = subprocess.run(
        ["git", "-C", str(upstream), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True,
    ).stdout.strip()
    r = subprocess.run(
        ["git", "-C", str(upstream), "pull", "--ff-only"],
        capture_output=True, text=True,
    )
    print(r.stdout or r.stderr, end="")
    after = subprocess.run(
        ["git", "-C", str(upstream), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True,
    ).stdout.strip()
    if before == after:
        print(f"Already up to date ({after})")
    else:
        print(f"Updated {before} -> {after}")
    return r.returncode


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("paths", nargs="*",
                    help=f"PDF files or folders (default: {DEFAULT_IN})")
    ap.add_argument("-o", "--out", default=str(DEFAULT_OUT), help="output folder")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="search folders recursively")
    ap.add_argument("-c", "--check", action="store_true",
                    help="only report markers; write nothing")
    ap.add_argument("--thorough", action="store_true",
                    help="also rebuild the PDF with Ghostscript to clear EXIF inside "
                         "embedded images (may recompress images and change file size)")
    ap.add_argument("--verify-text", action="store_true",
                    help="fail CHECK if Ghostscript text extract changes after clean")
    ap.add_argument("--doctor", action="store_true",
                    help="print tool versions and exit")
    ap.add_argument("--update-upstream", action="store_true",
                    help="git pull --ff-only on watermarks-remover/")
    ap.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    args = ap.parse_args()

    if args.doctor:
        return doctor()
    if args.update_upstream:
        return update_upstream()

    missing = [t for t in REQUIRED_TOOLS if not shutil.which(t, path=env()["PATH"])]
    if missing:
        print(f"warning: missing tools {missing}; results will be weaker",
              file=sys.stderr)

    DEFAULT_IN.mkdir(exist_ok=True)
    pdfs = collect(args.paths or [str(DEFAULT_IN)], args.recursive)
    if not pdfs:
        print(f"No PDFs found. Drop files into {DEFAULT_IN} or pass paths as arguments.")
        return 1

    out_dir = Path(args.out).expanduser().resolve()
    if not args.check:
        out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for i, pdf in enumerate(pdfs, 1):
        print(f"... [{i}/{len(pdfs)}] {pdf.name}", flush=True)
        rows.append(process(
            pdf.resolve(), out_dir, args.check, args.thorough, args.verify_text,
        ))

    print()
    for r in rows:
        name = Path(r["file"]).name
        before = ", ".join(r.get("before") or []) or "none"
        if r["status"] == "ERROR":
            print(f"[ERROR] {name}  ! {r.get('detail')}")
        elif args.check:
            print(f"[{r['status']:>10}] {name}  markers: {before}  "
                  f"pages: {r.get('pages')}")
            for f in r.get("findings", []):
                print(f"               - {f}")
        else:
            line = (
                f"[{r['status']:>5}] {name}  markers before: {before}  "
                f"pages: {r.get('pages')}->{r.get('pages_after')}  "
                f"size: {kb(r.get('size_in'))}->{kb(r.get('size_out'))}"
            )
            print(line)
            if r.get("detail"):
                print(f"        ! {r['detail']}")

    if not args.check:
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "wrapper_version": VERSION,
            "files": rows,
            "summary": {
                "total": len(rows),
                "ok": sum(1 for r in rows if r["status"] == "OK"),
                "check": sum(1 for r in rows if r["status"] == "CHECK"),
                "error": sum(1 for r in rows if r["status"] == "ERROR"),
            },
        }
        (out_dir / "report.json").write_text(json.dumps(report, indent=2))
        s = report["summary"]
        print(f"\n{s['ok']} OK, {s['check']} CHECK, {s['error']} ERROR "
              f"— cleaned files and report.json are in {out_dir}")
    return 0 if all(r["status"] in ("OK", "NONE FOUND", "MARKED") for r in rows) else 2


if __name__ == "__main__":
    sys.exit(main())
