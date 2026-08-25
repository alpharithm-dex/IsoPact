from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "release"


def main() -> int:
    python = []
    for line in (ROOT / "requirements-lock.txt").read_text(encoding="utf-8").splitlines():
        if "==" in line:
            name, version = line.split("==", 1)
            python.append({"type": "library", "name": name, "version": version, "purl": f"pkg:pypi/{name}@{version}"})
    lock = json.loads((ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    npm = []
    for key, item in lock.get("packages", {}).items():
        if not key.startswith("node_modules/") or not item.get("version"):
            continue
        name = key.removeprefix("node_modules/")
        npm.append({"type": "library", "name": name, "version": item["version"], "purl": f"pkg:npm/{name}@{item['version']}"})
    document = {"bomFormat": "CycloneDX", "specVersion": "1.5", "serialNumber": "urn:uuid:isopact-v0.1.0-hackathon",
                "version": 1, "metadata": {"timestamp": datetime.now(UTC).isoformat(), "component": {"type": "application", "name": "IsoPact", "version": "v0.1.0-hackathon"}},
                "components": python + npm, "scope_note": "Dependency transparency SBOM; not formal supply-chain certification."}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sbom.cdx.json").write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "frontend-dependencies.json").write_text(json.dumps({"lockfileVersion": lock.get("lockfileVersion"), "components": npm}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"python_components": len(python), "frontend_components": len(npm), "format": "CycloneDX 1.5"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
