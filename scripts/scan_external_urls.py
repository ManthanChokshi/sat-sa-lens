"""Fail the build if any shipped file reaches outside the machine.

Scans source, configuration and the built frontend for http(s) URLs that are not
localhost. Documentation and this script's own allow-list are exempt, as is
scripts/download_model.py, which is the one place allowed to use the network and
only when a human runs it explicitly.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

URL_RE = re.compile(r"https?://[^\s\"'`)<>\\]+", re.IGNORECASE)

LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1", "backend", "frontend")

SCAN_DIRS = ["backend/app", "generator", "frontend/src", "frontend/dist", "scripts"]
SCAN_FILES = [
    "docker-compose.yml",
    "docker-compose.offline.yml",
    "frontend/vite.config.ts",
    "frontend/index.html",
    "frontend/nginx.conf",
]
SKIP_SUFFIXES = {".woff", ".woff2", ".ttf", ".png", ".jpg", ".ico", ".duckdb", ".pdf"}
SKIP_FILES = {"scan_external_urls.py", "download_model.py"}

#: XML namespace identifiers. These are names, not addresses - nothing is fetched.
NAMESPACES = (
    "http://www.w3.org/",
    "http://json-schema.org/",
    "https://json-schema.org/",
)

#: Documentation links that appear inside third-party libraries' console warning
#: text (React, React Router, prop-types). They are printed to the console, never
#: requested. Listed explicitly so a reviewer can confirm each one.
INFORMATIONAL_PREFIXES = (
    "https://reactjs.org/docs/error-decoder.html",
    "https://react.dev/",
    "https://reactrouter.com/",
    "http://fb.me/",
    "https://fb.me/",
    "https://github.com/recharts/",
)

#: Markup that would actually pull a resource over the network.
FETCHING_MARKUP = re.compile(
    r"""(?:<script[^>]+src=|<link[^>]+href=|<img[^>]+src=|@import\s+url\()\s*["']?(https?://[^"'\s>)]+)""",
    re.IGNORECASE,
)


def is_local(url: str) -> bool:
    return any(f"//{h}" in url or f"//{h}:" in url for h in LOCAL_HOSTS)


def scan_file(path: Path) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Return (blocking hits, informational hits) for one file."""
    try:
        text = path.read_text(errors="ignore")
    except Exception:
        return [], []
    blocking: list[tuple[int, str]] = []
    informational: list[tuple[int, str]] = []
    for i, line in enumerate(text.splitlines(), 1):
        # Anything inside resource-loading markup is always blocking.
        for url in FETCHING_MARKUP.findall(line):
            if not is_local(url):
                blocking.append((i, f"[resource load] {url}"))
        for url in URL_RE.findall(line):
            clean = url.rstrip('.,;:)"\'')
            if is_local(clean) or clean.startswith(NAMESPACES):
                continue
            if clean.startswith(INFORMATIONAL_PREFIXES):
                informational.append((i, clean))
                continue
            blocking.append((i, clean))
    return blocking, informational


def main() -> int:
    targets: list[Path] = []
    for d in SCAN_DIRS:
        p = ROOT / d
        if p.exists():
            targets += [f for f in p.rglob("*") if f.is_file()]
    targets += [ROOT / f for f in SCAN_FILES if (ROOT / f).exists()]

    failures: list[str] = []
    notes: set[str] = set()
    scanned = 0
    for path in targets:
        if path.suffix.lower() in SKIP_SUFFIXES or path.name in SKIP_FILES:
            continue
        if "node_modules" in path.parts or "__pycache__" in path.parts:
            continue
        scanned += 1
        blocking, informational = scan_file(path)
        for line_no, url in blocking:
            failures.append(f"{path.relative_to(ROOT)}:{line_no}  {url}")
        for _, url in informational:
            notes.add(url)

    print(f"Scanned {scanned} files for outbound URLs.")
    if notes:
        print(
            "\nDocumentation links found inside third-party console-warning text. "
            "These are printed to the browser console, never requested:"
        )
        for url in sorted(notes):
            print(f"  {url}")
    if failures:
        print("\nEXTERNAL URLS FOUND - the build is not air-gapped:\n")
        for f in failures:
            print(f"  {f}")
        return 1
    print("\nNo fetchable external URL. Everything the running system loads is local.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
