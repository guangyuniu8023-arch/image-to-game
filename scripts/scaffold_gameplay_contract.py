#!/usr/bin/env python3
"""Create a schema-correct gameplay contract from GDD-derived cases.

This is a structural scaffold, not a game-design form.  The caller must derive
the rules, sides, names, and expected results from GDD module 8.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path


def parse_success(raw: str) -> dict[str, str]:
    if "=" not in raw:
        raise ValueError("success must use NAME=EXPECTED")
    name, expected = raw.split("=", 1)
    if not name.strip() or not expected.strip():
        raise ValueError("success name and expected value must be non-empty")
    return {"name": name.strip(), "category": "success", "expected": expected.strip()}


def parse_sided(raw: str, category: str) -> dict[str, str]:
    if "=" not in raw:
        raise ValueError(f"{category} must use RULE:SIDE:NAME=EXPECTED")
    left, expected = raw.split("=", 1)
    parts = left.split(":", 2)
    if len(parts) != 3 or not all(part.strip() for part in parts) or not expected.strip():
        raise ValueError(f"{category} must use RULE:SIDE:NAME=EXPECTED")
    rule, side, name = (part.strip() for part in parts)
    return {
        "name": name,
        "category": category,
        "rule": rule,
        "side": side,
        "expected": expected.strip(),
    }


def build_contract(bot: str, success: list[str], failure: list[str], boundary: list[str]) -> dict:
    cases = [parse_success(item) for item in success]
    cases.extend(parse_sided(item, "failure") for item in failure)
    cases.extend(parse_sided(item, "boundary") for item in boundary)
    if not success or not failure or not boundary:
        raise ValueError("at least one success, failure, and boundary case is required")
    names = [case["name"] for case in cases]
    if len(names) != len(set(names)):
        raise ValueError("case names must be unique")

    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for case in cases:
        if case["category"] in {"failure", "boundary"}:
            key = (case["category"], case["rule"])
            if case["side"] not in grouped[key]:
                grouped[key].append(case["side"])
    coverage = [
        {"category": category, "rule": rule, "required_sides": sides}
        for (category, rule), sides in grouped.items()
    ]
    return {
        "version": 1,
        "source": "gdd-module-8",
        "bot": bot,
        "required_categories": ["success", "failure", "boundary"],
        "coverage": coverage,
        "cases": cases,
    }


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="gameplay-scaffold-") as raw:
        project = Path(raw)
        (project / "scripts").mkdir()
        (project / "scripts/bot.js").write_text("// fixture\n", encoding="utf-8")
        (project / "index.html").write_text("<!doctype html>\n", encoding="utf-8")
        contract = build_contract(
            "scripts/bot.js",
            ["win=ready"],
            ["strength:short:too-short=gameover", "strength:long:too-long=gameover"],
            ["hitbox:inside:edge-in=ready", "hitbox:outside:edge-out=gameover"],
        )
        (project / "GAMEPLAY_CONTRACT.json").write_text(
            json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from audit_gameplay_report import audit  # pylint: disable=import-outside-toplevel

        good = not audit(project, None, contract_only=True)
        rejected = False
        try:
            build_contract("scripts/bot.js", ["win=ready"], [], ["r:s:n=x"])
        except ValueError:
            rejected = True
    if good and rejected:
        print("GAMEPLAY_CONTRACT_SCAFFOLD_SELFTEST: PASS")
        return 0
    print("GAMEPLAY_CONTRACT_SCAFFOLD_SELFTEST: FAIL")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--bot")
    parser.add_argument("--success", action="append", default=[])
    parser.add_argument("--failure", action="append", default=[])
    parser.add_argument("--boundary", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.project or not args.bot:
        parser.error("--project and --bot are required")
    project = args.project.resolve()
    if not project.is_dir():
        raise ValueError(f"project directory does not exist: {project}")
    output = project / "GAMEPLAY_CONTRACT.json"
    if output.exists() and not args.force:
        raise FileExistsError(f"refusing to overwrite {output}; pass --force explicitly")
    contract = build_contract(args.bot, args.success, args.failure, args.boundary)
    output.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - CLI boundary
        print(f"GAMEPLAY_CONTRACT_SCAFFOLD: FAIL {exc}", file=sys.stderr)
        raise SystemExit(1)
