"""Download the sentence-transformers model ONCE, then never again.

Run this on a machine with internet access:

    python scripts/download_model.py

It writes models/all-MiniLM-L6-v2/ into the repository. After that the
application loads only from that folder with HF_HUB_OFFLINE=1 and
TRANSFORMERS_OFFLINE=1 set, so the running system never touches the network.
This script is the ONLY place in the project that is allowed to.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "all-MiniLM-L6-v2"
MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"


def main() -> int:
    if TARGET.exists() and any(TARGET.iterdir()):
        print(f"Model already present at {TARGET} - nothing to do.")
        return 0
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print(
            "sentence-transformers is not installed. Install the optional ML extras "
            "first:\n    pip install -r backend/requirements-ml.txt",
            file=sys.stderr,
        )
        return 2

    print(f"Downloading {MODEL_ID} (about 90 MB)...")
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    try:
        model = SentenceTransformer(MODEL_ID, device="cpu")
        model.save(str(TARGET))
    except Exception as exc:  # network or hub failure
        print(f"Download failed: {exc}", file=sys.stderr)
        if TARGET.exists():
            shutil.rmtree(TARGET, ignore_errors=True)
        return 1

    size = sum(f.stat().st_size for f in TARGET.rglob("*") if f.is_file())
    print(f"Saved to {TARGET} ({size / 1e6:.1f} MB).")
    print(
        "\nThe application will now use it automatically. To make a missing model a "
        "hard error instead of falling back to the lexical method, set "
        "SATSA_REQUIRE_MODEL=1."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
