from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "release" / "secret-scan.json"
EXCLUDED = {".venv", ".venv-win", "node_modules", "__pycache__", ".pytest_cache", "dist", "work"}
PATTERNS = {
    "private_key": re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    "google_api_key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9_]{30,}"),
    "bearer_token": re.compile(r"Bearer [A-Za-z0-9._-]{20,}"),
    "credential_url": re.compile(r"(?:postgres(?:ql)?|mysql)://[^\s/:]+:[^\s@]+@"),
    "service_account_private_key": re.compile(r'"private_key"\s*:\s*"-----BEGIN'),
}


def main() -> int:
    candidates = []
    scanned = 0
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in EXCLUDED for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                if label == "bearer_token" and "invalid-" in match.group(0).lower():
                    continue
                candidates.append({"file": path.relative_to(ROOT).as_posix(), "type": label, "line": text.count("\n", 0, match.start()) + 1})
    result = {"schema_version": "stage13-secret-scan-v1", "files_scanned": scanned,
              "candidate_matches": candidates, "genuine_credentials": 0 if not candidates else None,
              "public_project_ids_are_secrets": False, "status": "PASS" if not candidates else "REVIEW"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not candidates else 1


if __name__ == "__main__":
    raise SystemExit(main())
