from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "submission" / "asset-validation.json"

REQUIRED = [
    "README.md",
    "devpost-submission.md",
    "docs/submission/devpost.md",
    "docs/submission/demo-script.md",
    "docs/submission/hostile-judge-audit.md",
    "docs/submission/claims-ledger.md",
    "docs/submission/evidence-map.md",
    "docs/submission/public-article.md",
    "docs/submission/social-post.md",
    "artifacts/submission/claims-ledger.json",
    "artifacts/submission/devpost-fields.json",
    "artifacts/submission/isopact-architecture.svg",
    "artifacts/submission/isopact-architecture.png",
    "artifacts/submission/isopact-architecture.pdf",
    "artifacts/submission/external-browser-audit.json",
]


def main() -> int:
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    claims = json.loads((ROOT / "artifacts/submission/claims-ledger.json").read_text(encoding="utf-8"))
    counts = {kind: sum(c["classification"] == kind for c in claims["claims"])
              for kind in ("VERIFIED", "QUALIFIED", "DO_NOT_CLAIM")}
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    hostile = (ROOT / "docs/submission/hostile-judge-audit.md").read_text(encoding="utf-8")
    devpost_fields = json.loads(
        (ROOT / "artifacts/submission/devpost-fields.json").read_text(encoding="utf-8")
    )
    checks = {
        "required_assets": not missing,
        "claims_have_all_classes": all(counts.values()),
        "hostile_questions_68": "| 68 |" in hostile,
        "readme_canonical_economics": all(value in readme for value in ("$200", "$650", "$450", "$250", "$400")),
        "readme_disclaims_acid": "does **not** claim cross-SaaS ACID" in readme,
        "readme_agent_gateway_qualified": "not bound to canonical traffic" in readme,
        "architecture_png_nonempty": (ROOT / "artifacts/submission/isopact-architecture.png").stat().st_size > 50_000,
        "architecture_pdf_valid": (ROOT / "artifacts/submission/isopact-architecture.pdf").read_bytes().startswith(b"%PDF-"),
    }
    status = "PASS" if all(checks.values()) else "BLOCKED"
    user_blockers = ["final video URL", "exact project start date", "user-specific Devpost fields"]
    if not str(devpost_fields.get("repository_url", "")).startswith("https://github.com/"):
        user_blockers.insert(0, "public repository URL")
    report = {"status": status, "checks": checks, "missing": missing, "claim_counts": counts,
              "user_blockers": user_blockers}
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
