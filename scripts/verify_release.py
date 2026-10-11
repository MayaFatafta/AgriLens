#!/usr/bin/env python3
"""Check downloaded AgriLens release files against frozen SHA-256 manifest.

Run from the extracted package root: python scripts/verify_release.py
Do not mistake these hashes for scientific model validation.
"""
import csv, hashlib, sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
manifest = root / "RELEASE_SHA256_manifest.csv"
problems = []
with manifest.open(newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
for row in rows:
    path = root / row["relative_path"]
    if not path.is_file():
        problems.append("MISSING: " + row["relative_path"])
        continue
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    if path.stat().st_size != int(row["bytes"]) or h.hexdigest() != row["sha256"]:
        problems.append("MISMATCH: " + row["relative_path"])
print(f"AgriLens SHA-256 verification: {len(rows) - len(problems)}/{len(rows)} OK")
for item in problems:
    print(item, file=sys.stderr)
if problems:
    print("Note: rerunning the model regenerates derived outputs; their hashes will change.",file=sys.stderr)
    sys.exit(1)
