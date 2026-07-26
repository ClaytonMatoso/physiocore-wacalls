#!/usr/bin/env python3
"""Generate the Phase 0 file-by-file inventory for the pinned WaCalls snapshot.

The output is deterministic and contains no file contents, credentials or runtime data.
It classifies every tracked source file for the PhysioCore migration decision.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "audit-artifacts"
PINNED_SOURCE_COMMIT = "2ce896ad31fe2915ef0d599c83c62dc966eda7b9"


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    )
    return sorted(p.decode("utf-8") for p in result.stdout.split(b"\0") if p)


def language(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".go": "Go",
        ".tsx": "TypeScript/React",
        ".ts": "TypeScript",
        ".js": "JavaScript",
        ".mjs": "JavaScript",
        ".json": "JSON",
        ".md": "Markdown",
        ".sql": "SQL",
        ".sh": "Shell",
        ".ps1": "PowerShell",
        ".yml": "YAML",
        ".yaml": "YAML",
        ".html": "HTML",
        ".css": "CSS",
        ".bin": "Binary data",
        ".raw": "Binary test data",
        ".png": "Image",
        ".jpg": "Image",
        ".jpeg": "Image",
    }.get(suffix, "Other")


def module(path: str) -> str:
    p = path.lower()
    if p.startswith("client/src/components/domain/chat/") or p.endswith("/chatspage.tsx"):
        return "agent-console/chat"
    if p.startswith("client/src/components/domain/session/") or p.endswith("/connectionspage.tsx"):
        return "agent-console/connections"
    if p.startswith("client/src/components/auth/") or p.endswith("/loginpage.tsx") or "/services/auth." in p:
        return "legacy-auth-ui"
    if p.startswith("client/src/pages/"):
        return "agent-console/pages"
    if p.startswith("client/src/services/"):
        return "agent-console/api-clients"
    if p.startswith("client/src/stores/"):
        return "agent-console/state"
    if p.startswith("client/src/components/ui/"):
        return "agent-console/ui-primitives"
    if p.startswith("client/src/"):
        return "agent-console/shared"
    if p.startswith("client/"):
        return "frontend-tooling"
    if p.startswith("cmd/server/auth") or p.endswith("authstore.go"):
        return "legacy-iam"
    if p.startswith("cmd/server/session") or p.endswith("/whatsapp.go"):
        return "connect/session-management"
    if p.startswith("cmd/server/message") or p.endswith("chatmetastore.go"):
        return "connect/inbox-messages"
    if "cloudapi" in p or p.startswith("internal/wa/cloudapi"):
        return "connect/whatsapp-cloud-api"
    if p.startswith("internal/wa/"):
        return "connect/whatsapp-transport"
    if "queue" in p or "tag" in p or "contact" in p or "report" in p:
        return "connect/supporting-domain"
    if "broker" in p or "bridge" in p:
        return "connect/realtime-events"
    if "flow" in p:
        return "legacy-automation"
    if "kanban" in p:
        return "legacy-kanban"
    if "billing" in p or "freetier" in p or "cart" in p or "campaign" in p or "broadcast" in p:
        return "legacy-commercial"
    if p.startswith("internal/voip/") or "call" in Path(p).name or "webrtc" in p:
        return "legacy-voip"
    if p.startswith("internal/storage") or p.startswith("cmd/migrate") or p.endswith("db_test.go"):
        return "legacy-persistence"
    if p.startswith("internal/cache"):
        return "legacy-cache"
    if p.startswith("cmd/server/"):
        return "legacy-server-composition"
    if p in {"go.mod", "go.sum", "client/package.json", "client/package-lock.json"}:
        return "dependency-manifest"
    if "license" in p:
        return "license"
    if p.endswith("_test.go") or "/testdata/" in p:
        return "tests"
    return "repository-support"


def disposition(path: str, mod: str) -> tuple[str, str, str]:
    p = path.lower()
    name = Path(p).name

    if "license" in p:
        return "KEEP", "THIRD_PARTY_NOTICES", "Preserve mandatory attribution and license text."
    if p.startswith("internal/voip/"):
        return "ISOLATE", "archive/legacy-voip", "Large experimental VoIP stack is outside the Academy Connect MVP and increases security/licensing surface."
    if mod == "legacy-iam":
        return "REMOVE", "services/core-api/iam", "Replace local password, raw-token and ParentID tenancy with the Academy IAM/OIDC/RBAC foundation."
    if mod == "legacy-commercial":
        return "REMOVE", "services/core-api", "Billing/free-tier/campaign concepts belong to dedicated Academy domains; do not migrate implementation."
    if mod == "legacy-automation":
        return "ISOLATE", "services/automation", "Retain only as behavioral reference until a durable, tenant-safe automation engine is designed."
    if mod == "legacy-kanban":
        return "REWRITE", "services/core-api/crm", "Pipeline belongs to the Academy CRM and requires canonical lead/opportunity entities."
    if mod == "legacy-persistence" or mod == "legacy-cache":
        return "REWRITE", "services/connect/internal/platform", "Replace SQLite/startup ALTERs and optional in-memory cache with PostgreSQL, migrations, object storage and shared event infrastructure."
    if mod == "connect/session-management":
        return "ADAPT", "services/connect", "Extract WhatsApp connection lifecycle behind transport interfaces; replace ownership and persistence."
    if mod in {"connect/inbox-messages", "connect/supporting-domain", "connect/realtime-events"}:
        return "ADAPT", "services/connect", "Preserve useful behavior through ports/adapters, tenant IDs, durable events and PostgreSQL repositories."
    if mod in {"connect/whatsapp-cloud-api", "connect/whatsapp-transport"}:
        return "ADAPT", "services/connect/internal/transports", "Separate official and QR transports behind versioned connectors with idempotency and observability."
    if mod.startswith("agent-console/"):
        if mod == "agent-console/ui-primitives":
            return "KEEP", "packages/ui", "Reusable UI primitives can be retained after accessibility and design-system review."
        return "ADAPT", "apps/agent-console", "Preserve interaction knowledge but split oversized components, replace legacy API/auth/state contracts and add tests."
    if mod == "legacy-auth-ui":
        return "REWRITE", "apps/agent-console/auth", "Replace local login/session assumptions with OIDC Authorization Code + PKCE and MFA UX."
    if mod == "frontend-tooling":
        if name == "instalador_wacalls.sh":
            return "REMOVE", "infra/deployment", "Replace mutable root/systemd installer with immutable images and controlled deployment."
        return "ADAPT", "apps/agent-console", "Rebuild under monorepo tooling with lint, typecheck, tests and locked dependency policy."
    if mod == "legacy-server-composition":
        return "REWRITE", "services/connect", "Decompose the package-main god object into modules, repositories, handlers and workers."
    if mod == "tests":
        return "KEEP", "tests/characterization", "Retain behavior tests where portable; rewrite fixtures to remove network and local-path coupling."
    if mod == "dependency-manifest":
        return "ADAPT", "workspace dependency manifests", "Pin reviewed dependencies, generate SBOM and apply automated vulnerability/license checks."
    if p in {"readme.md", "setup.md"}:
        return "ADAPT", "docs/legacy/wacalls", "Keep as historical operational reference, not as production runbook."
    if p == ".gitignore":
        return "ADAPT", ".gitignore", "Merge protections into the private monorepo ignore policy."
    return "REVIEW", "docs/audit/wacalls", "No automatic migration; explicit owner decision required before incorporation."


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for rel in tracked_files():
        if rel.startswith("audit-artifacts/"):
            continue
        full = ROOT / rel
        if not full.is_file():
            continue
        data = full.read_bytes()
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
