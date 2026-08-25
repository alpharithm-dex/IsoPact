from __future__ import annotations

import importlib.metadata
import json
import platform
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    distributions = sorted(
        ((dist.metadata.get("Name") or "").strip(), dist.version)
        for dist in importlib.metadata.distributions()
        if (dist.metadata.get("Name") or "").strip()
        and (dist.metadata.get("Name") or "").strip().lower() not in {"pip", "setuptools", "wheel"}
    )
    lock = [f"{name}=={version}" for name, version in distributions]
    (ROOT / "requirements-lock.txt").write_text("\n".join(lock) + "\n", encoding="utf-8")
    node = subprocess.run(["node", "--version"], text=True, capture_output=True, check=True).stdout.strip()
    npm_executable = shutil.which("npm.cmd") or shutil.which("npm") or "npm"
    npm = subprocess.run([npm_executable, "--version"], text=True, capture_output=True, check=True).stdout.strip()
    direct = {}
    for name in ["google-adk", "opentelemetry-api", "opentelemetry-sdk", "opentelemetry-exporter-otlp-proto-grpc",
                 "google-genai", "google-cloud-firestore", "google-cloud-pubsub", "google-cloud-kms",
                 "google-cloud-secret-manager", "google-cloud-modelarmor", "cryptography"]:
        try:
            direct[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            direct[name] = "NOT_INSTALLED"
    inventory = {"python": platform.python_version(), "node": node, "npm": npm,
                 "python_direct": direct, "python_locked_distributions": len(lock),
                 "frontend_lockfile": "frontend/package-lock.json", "install": "npm ci"}
    out = ROOT / "artifacts" / "release"
    out.mkdir(parents=True, exist_ok=True)
    (out / "dependency-inventory.json").write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(inventory, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
