#!/usr/bin/env python3
"""Self-tests for the local clean_pdfs wrapper (stdlib unittest)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLEAN = ROOT / "clean_pdfs.py"
TOOLS = ROOT / ".tools" / "env" / "bin"


def env() -> dict:
    import os
    e = dict(os.environ)
    e["PATH"] = f"{TOOLS}{os.pathsep}{e.get('PATH', '')}"
    return e


def make_pdf(path: Path, pages: int = 1, text: str = "Hello") -> None:
    cmds = []
    for i in range(pages):
        cmds.append(
            f"/Helvetica findfont 24 scalefont setfont "
            f"72 700 moveto ({text} page {i + 1}) show showpage"
        )
    subprocess.run(
        ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pdfwrite",
         f"-sOutputFile={path}", "-c", " ".join(cmds)],
        check=True, env=env(),
    )


class CleanPdfsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for t in ("gs", "qpdf", "exiftool"):
            if not shutil.which(t, path=env()["PATH"]):
                raise unittest.SkipTest(f"missing {t}")

    def test_doctor_ready(self):
        r = subprocess.run(
            [sys.executable, str(CLEAN), "--doctor"],
            capture_output=True, text=True, env=env(),
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ready", r.stdout)

    def test_check_and_clean_ai_tagged(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "ai tagged.pdf"
            out = td / "out"
            make_pdf(src, pages=2, text="Secret")
            subprocess.run(
                ["exiftool", "-q", "-overwrite_original",
                 "-Creator=ChatGPT", "-Producer=OpenAI GPT-4o", str(src)],
                check=True, env=env(),
            )
            check = subprocess.run(
                [sys.executable, str(CLEAN), "--check", str(src)],
                capture_output=True, text=True, env=env(),
            )
            self.assertEqual(check.returncode, 0, check.stdout)
            self.assertIn("MARKED", check.stdout)
            self.assertIn("AI metadata", check.stdout)

            clean = subprocess.run(
                [sys.executable, str(CLEAN), "--verify-text", "-o", str(out), str(src)],
                capture_output=True, text=True, env=env(),
            )
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
            self.assertIn("[   OK]", clean.stdout)
            dest = out / "ai tagged.cleaned.pdf"
            self.assertTrue(dest.exists())
            report = json.loads((out / "report.json").read_text())
            self.assertEqual(report["summary"]["ok"], 1)
            blob = dest.read_bytes().lower()
            self.assertNotIn(b"chatgpt", blob)
            self.assertNotIn(b"openai", blob)

    def test_skips_broken_pdf(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            bad = td / "broken.pdf"
            bad.write_text("not a pdf")
            r = subprocess.run(
                [sys.executable, str(CLEAN), "-o", str(td / "out"), str(bad)],
                capture_output=True, text=True, env=env(),
            )
            self.assertEqual(r.returncode, 2)
            self.assertIn("ERROR", r.stdout)
            self.assertFalse((td / "out" / "broken.cleaned.pdf").exists())

    def test_unique_dest_no_clobber(self):
        import clean_pdfs as cp
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / "doc.cleaned.pdf").write_bytes(b"%PDF")
            dest = cp.unique_dest(td, "doc")
            self.assertEqual(dest.name, "doc.cleaned.2.pdf")


if __name__ == "__main__":
    unittest.main()
