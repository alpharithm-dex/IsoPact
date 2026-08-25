from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "release" / "final-verification.json"


def run(name, command, cwd=ROOT):
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    return {"name": name, "returncode": result.returncode, "stdout_tail": result.stdout[-2000:], "stderr_tail": result.stderr[-2000:]}


def main() -> int:
    python = sys.executable
    npm = shutil.which("npm.cmd") or shutil.which("npm") or "npm"
    steps = [
        run("secret_scan", [python, "scripts/secret_scan.py"]),
        run("backend_tests", [python, "-m", "pytest", "-q"]),
        run("frontend_tests", [npm, "test", "--", "--run"], ROOT / "frontend"),
        run("frontend_build", [npm, "run", "build"], ROOT / "frontend"),
        run("inventory", [python, "scripts/collect_stage13_inventory.py"]),
        run("deployment", [python, "scripts/verify_deployment.py"]),
        run("receipt", [python, "scripts/verify_settlement_receipt.py", "artifacts/security/final-settlement-receipt.json"]),
        run("benchmark_smoke", [python, "scripts/run_scenario.py", "missing_order_unmanaged"]),
        run("vulnerability_audit", [python, "scripts/vulnerability_audit.py"]),
        run("sbom", [python, "scripts/generate_sbom.py"]),
    ]
    status = "PASS" if all(step["returncode"] == 0 for step in steps) else "BLOCKED"
    result = {"status": status, "non_destructive": True, "steps": steps,
              "failed": [step["name"] for step in steps if step["returncode"] != 0]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "steps": [{"name": s["name"], "returncode": s["returncode"]} for s in steps]}, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
