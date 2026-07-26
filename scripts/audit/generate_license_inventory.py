#!/usr/bin/env python3
"""Capture license evidence for Go modules and installed npm packages.

The report records declared licenses and hashes of discovered license files. It is
not a legal opinion; unknown/missing entries must block incorporation until reviewed.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "audit-artifacts"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_json_stream(raw: str) -> list[dict]:
    decoder = json.JSONDecoder()
    index = 0
    values = []
    while index < len(raw):
        while index < len(raw) and raw[index].isspace():
            index += 1
        if index >= len(raw):
            break
        value, index = decoder.raw_decode(raw, index)
        values.append(value)
    return values


def license_files(directory: Path) -> list[dict[str, str]]:
    if not directory.is_dir():
        return []
    result = []
    for child in sorted(directory.iterdir()):
        upper = child.name.upper()
        if child.is_file() and (upper.startswith("LICENSE") or upper.startswith("COPYING") or upper.startswith("NOTICE")):
            first = ""
            try:
                first = child.read_text(encoding="utf-8", errors="replace").splitlines()[0][:200]
            except Exception:
                pass
            result.append({"file": child.name, "sha256": sha256(child), "first_line": first})
    return result


def go_inventory() -> list[dict]:
    raw = subprocess.run(
        ["go", "list", "-m", "-json", "all"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout
    modules = []
    for item in parse_json_stream(raw):
        directory = Path(item.get("Dir", ""))
        modules.append(
            {
                "path": item.get("Path"),
                "version": item.get("Version", "workspace"),
                "sum": item.get("Sum", ""),
                "replace": item.get("Replace", {}).get("Path", "") if isinstance(item.get("Replace"), dict) else "",
                "license_evidence": license_files(directory),
            }
        )
    return modules


def npm_inventory() -> list[dict]:
    node_modules = ROOT / "client" / "node_modules"
    packages = []
    if not node_modules.is_dir():
        return packages
    seen: set[tuple[str, str]] = set()
    for package_json in sorted(node_modules.glob("**/package.json")):
        if ".bin" in package_json.parts:
            continue
        try:
            item = json.loads(package_json.read_text(encoding="utf-8"))
        except Exception:
            continue
        name = item.get("name")
        version = item.get("version")
        if not name or not version or (name, version) in seen:
            continue
        seen.add((name, version))
        packages.append(
            {
                "name": name,
                "version": version,
                "declared_license": item.get("license") or item.get("licenses") or "",
                "license_evidence": license_files(package_json.parent),
            }
        )
    return sorted(packages, key=lambda row: (row["name"], row["version"]))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "go_modules": go_inventory(),
        "npm_packages": npm_inventory(),
    }
    report["summary"] = {
        "go_module_count": len(report["go_modules"]),
        "go_without_license_file": sum(not row["license_evidence"] for row in report["go_modules"]),
        "npm_package_count": len(report["npm_packages"]),
        "npm_without_declared_license": sum(not row["declared_license"] for row in report["npm_packages"]),
        "npm_without_license_file": sum(not row["license_evidence"] for row in report["npm_packages"]),
    }
    (OUT / "wacalls-license-inventory.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
