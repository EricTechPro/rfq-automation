#!/usr/bin/env python3
"""Generate a generic fill-in-the-blank Freelancer NDA PDF.

Usage:
    python3 generate_nda.py

Outputs Freelancer_NDA.pdf with blank lines for the freelancer to fill in.
EricTech Solutions Inc. is pre-filled as the Company.

DISCLAIMER: This generates a template document, not legal advice.
Have the output reviewed by a lawyer before use.
"""

import os
import platform
import sys
from pathlib import Path


def _ensure_homebrew_libs() -> None:
    """On macOS, ensure Homebrew lib path is in DYLD_LIBRARY_PATH for WeasyPrint."""
    if platform.system() != "Darwin":
        return
    brew_lib = "/opt/homebrew/lib"
    if not os.path.isdir(brew_lib):
        brew_lib = "/usr/local/lib"  # Intel Mac fallback
    if not os.path.isdir(brew_lib):
        return
    current = os.environ.get("DYLD_LIBRARY_PATH", "")
    if brew_lib not in current:
        os.environ["DYLD_LIBRARY_PATH"] = (
            "%s:%s" % (brew_lib, current) if current else brew_lib
        )


_ensure_homebrew_libs()

TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATE_FILE = TEMPLATE_DIR / "freelancer_nda.html"
OUTPUT_FILE = "Freelancer_NDA.pdf"


def main() -> None:
    try:
        from weasyprint import HTML
    except ImportError:
        print("ERROR: weasyprint is not installed. Run: pip3 install weasyprint", file=sys.stderr)
        sys.exit(1)

    html_content = TEMPLATE_FILE.read_text(encoding="utf-8")

    print("Generating NDA PDF...")
    html_doc = HTML(string=html_content, base_url=str(TEMPLATE_DIR))
    html_doc.write_pdf(OUTPUT_FILE)

    size_kb = os.path.getsize(OUTPUT_FILE) / 1024
    print("NDA generated: %s (%.1f KB)" % (OUTPUT_FILE, size_kb))


if __name__ == "__main__":
    main()
