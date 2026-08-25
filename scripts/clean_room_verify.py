from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "release" / "clean-room.json"
SOURCE_DIRS = ["src", "services", "scripts", "tests", "frontend", "config", "docs", "artifacts"]
SOURCE_FILES = ["Dockerfile", "requirements.txt", "requirements-lock.txt", ".dockerignore", ".gcloudignore", ".gitignore", "README.md"]
EXCLUDES = {"node_modules", "dist", "__pycache__", ".pytest_cache", ".venv", ".venv-win", "work"}


def ignore(_path, names):
    return [name for name in names if name in EXCLUDES or name.endswith(".pyc")]


def run(command, cwd):
    started = datetime.now(UTC)
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    return {"command": [str(part) for part in command], "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-2000:], "stderr_tail": completed.stderr[-2000:],
            "started": started.isoformat(), "finished": datetime.now(UTC).isoformat()}


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and not any(part in EXCLUDES for part in p.parts)):
        digest.update(path.relative_to(root).as_posix().encode()); digest.update(b"\0"); digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    destination = ROOT.parent / "stage13-clean-room"
    attempt = 1
    while destination.exists():
        destination = ROOT.parent / f"stage13-clean-room-attempt-{attempt}"
        attempt += 1
    destination.mkdir(parents=True)
    for name in SOURCE_DIRS:
        shutil.copytree(ROOT / name, destination / name, ignore=ignore)
    for name in SOURCE_FILES:
        source = ROOT / name
        if source.exists(): shutil.copy2(source, destination / name)
    python = sys.executable
    venv = destination / ".clean-venv"
    steps = [run([python, "-m", "venv", str(venv)], destination)]
    clean_python = venv / "Scripts" / "python.exe"
    steps.append(run([str(clean_python), "-m", "pip", "install", "--timeout", "60", "-r", "requirements-lock.txt"], destination))
    steps.append(run([str(clean_python), "-m", "pytest", "-q"], destination))
    npm = shutil.which("npm.cmd") or shutil.which("npm") or "npm"
    steps.append(run([npm, "ci"], destination / "frontend"))
    steps.append(run([npm, "test", "--", "--run"], destination / "frontend"))
    steps.append(run([npm, "run", "build"], destination / "frontend"))
    steps.append(run([str(clean_python), "scripts/verify_settlement_receipt.py", "artifacts/security/final-settlement-receipt.json"], destination))
    steps.append(run([str(clean_python), "scripts/run_scenario.py", "missing_order_unmanaged"], destination))
    status = "PASS" if all(step["returncode"] == 0 for step in steps) else "BLOCKED"
    result = {"status": status, "clean_directory": destination.name, "source_tree_sha256": tree_hash(destination),
              "excluded_hidden_state": sorted(EXCLUDES), "steps": steps, "docker_local": "UNAVAILABLE; clean source is submitted to Cloud Build separately"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "source_tree_sha256": result["source_tree_sha256"],
                      "steps": [{"command": step["command"], "returncode": step["returncode"]} for step in steps]}, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
