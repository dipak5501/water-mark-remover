#!/usr/bin/env bash
# Clean AI/provenance metadata from PDFs. See ./clean_pdfs.sh --help
exec python3 "$(cd "$(dirname "$0")" && pwd)/clean_pdfs.py" "$@"
