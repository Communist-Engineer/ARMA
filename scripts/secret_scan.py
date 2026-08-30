#!/usr/bin/env python3
"""Fail on common committed secret forms without printing captured values."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "AWS access key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "GitHub token": re.compile(rb"gh[pousr]_[A-Za-z0-9_]{30,}"),
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def main() -> None:
    git = shutil.which("git")
    if git is None:
        raise SystemExit("git executable is required for tracked-file secret scanning")
    paths = subprocess.check_output(  # noqa: S603 - fixed git argv from trusted executable lookup
        [git, "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    findings: list[str] = []
    for relative in paths:
        path = ROOT / relative
        if not path.is_file() or path.stat().st_size > 5_000_000:
            continue
        content = path.read_bytes()
        for label, pattern in PATTERNS.items():
            if pattern.search(content):
                findings.append(f"{relative}: {label}")
    if findings:
        raise SystemExit("potential secrets detected:\n" + "\n".join(findings))


if __name__ == "__main__":
    main()
