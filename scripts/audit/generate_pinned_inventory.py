#!/usr/bin/env python3
"""Generate the official inventory from the immutable pre-audit WaCalls commit."""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from generate_inventory import OUT, PINNED_SOURCE_COMMIT, disposition, language, module

ROOT = Path(__file__).resolve().parents[2]


def git_bytes(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def source_paths() -> list[str]:
    raw = git_bytes("ls-tree", "-r", "--name-only", "-z", PINNED_SOURCE_COMMIT)
    return sorted(path.decode("utf-8") for path in raw.split(b"\0") if path)


def source_content(path: str) -> bytes:
    return git_bytes("show", f"{PINNED_SOURCE_COMMIT}:{path}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for rel in source_paths():
        data = source_content(rel)
        mod = module(rel)
        decision, target, rationale = disposition(rel, mod)
        rows.append(
            {
                "source_commit": PINNED_SOURCE_COMMIT,
                "path": rel,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "language": language(rel),
                "module": mod,
                "decision": decision,
                "target": target,
                "rationale": rationale,
            }
        )

    fields = list(rows[0].keys()) if rows else []
    with (OUT / "wacalls-file-inventory.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "source_commit": PINNED_SOURCE_COMMIT,
        "file_count": len(rows),
        "total_bytes": sum(int(row["bytes"]) for row in rows),
        "by_module": dict(sorted(Counter(str(row["module"]) for row in rows).items())),
        "by_decision": dict(sorted(Counter(str(row["decision"]) for row in rows).items())),
        "by_language": dict(sorted(Counter(str(row["language"]) for row in rows).items())),
    }
    (OUT / "wacalls-inventory-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
