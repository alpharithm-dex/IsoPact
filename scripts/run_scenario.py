from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from isopact.simulator import ScenarioRunner, build_scenario


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a deterministic IsoPact scenario")
    parser.add_argument(
        "scenario",
        choices=["missing_order_unmanaged", "missing_order_preexisting_divergence"],
    )
    parser.add_argument("--json", action="store_true", help="print canonical replay JSON")
    parser.add_argument("--output", type=Path, help="write replay JSON to this path")
    args = parser.parse_args()

    replay = ScenarioRunner().run(build_scenario(args.scenario))
    rendered = json.dumps(replay, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    output = args.output or ROOT / "artifacts" / "replays" / f"{args.scenario}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    if args.json:
        sys.stdout.write(rendered)
    else:
        position = replay["checkpoints"]["contradiction"]["economic_position"]
        print(f"scenario={args.scenario}")
        print(f"semantic_digest={replay['semantic_digest']}")
        print(f"projected_total_minor_units={position['projected_total_minor_units']}")
        print(f"projected_excess_minor_units={position['projected_excess_minor_units']}")
        print(f"artifact={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
