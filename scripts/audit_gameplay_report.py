#!/usr/bin/env python3
"""Audit GDD-derived gameplay coverage and a bot's hash-bound evidence report."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


CATEGORIES = {"success", "failure", "boundary"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_object(path: Path, label: str, problems: list[str]) -> dict[str, Any]:
    if not path.is_file():
        problems.append(f"missing {label}: {path.name}")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"invalid {label}: {exc}")
        return {}
    if not isinstance(value, dict):
        problems.append(f"{label} root must be an object")
        return {}
    return value


def rel_file(project: Path, value: Any, label: str, problems: list[str]) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        problems.append(f"{label} must be a non-empty project-relative path")
        return None
    rel = Path(value)
    if rel.is_absolute() or ".." in rel.parts:
        problems.append(f"{label} must stay inside project")
        return None
    path = project / rel
    if not path.is_file() or path.stat().st_size <= 0:
        problems.append(f"{label} missing or empty: {value}")
        return None
    return path


def audit_contract(project: Path) -> tuple[dict[str, Any], list[str], Path | None]:
    problems: list[str] = []
    path = project / "GAMEPLAY_CONTRACT.json"
    contract = load_object(path, "GAMEPLAY_CONTRACT.json", problems)
    if not contract:
        return contract, problems, None
    if contract.get("version") != 1:
        problems.append("GAMEPLAY_CONTRACT.version must equal 1")
    if contract.get("source") != "gdd-module-8":
        problems.append("GAMEPLAY_CONTRACT.source must equal gdd-module-8")
    if not (project / "index.html").is_file() or (project / "index.html").stat().st_size <= 0:
        problems.append("project index.html is missing or empty")
    bot_path = rel_file(project, contract.get("bot"), "GAMEPLAY_CONTRACT.bot", problems)

    required = contract.get("required_categories")
    if not isinstance(required, list) or set(required) != CATEGORIES:
        problems.append("required_categories must contain success, failure, and boundary exactly once")
    elif len(required) != len(set(required)):
        problems.append("required_categories must not contain duplicates")

    cases = contract.get("cases")
    if not isinstance(cases, list) or not cases:
        problems.append("GAMEPLAY_CONTRACT.cases must be a non-empty array")
        cases = []
    names: set[str] = set()
    covered_categories: set[str] = set()
    covered_rule_sides: set[tuple[str, str, str]] = set()
    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        if not isinstance(case, dict):
            problems.append(f"{label} must be an object")
            continue
        name = case.get("name")
        category = case.get("category")
        if not isinstance(name, str) or not name.strip():
            problems.append(f"{label}.name must be a non-empty string")
        elif name in names:
            problems.append(f"duplicate gameplay case: {name}")
        else:
            names.add(name)
        if category not in CATEGORIES:
            problems.append(f"{label}.category must be success, failure, or boundary")
        else:
            covered_categories.add(category)
        if "expected" not in case:
            problems.append(f"{label}.expected is required")
        rule, side = case.get("rule"), case.get("side")
        if category in {"failure", "boundary"}:
            if not isinstance(rule, str) or not rule.strip():
                problems.append(f"{label}.rule is required for {category}")
            if not isinstance(side, str) or not side.strip():
                problems.append(f"{label}.side is required for {category}")
            if isinstance(rule, str) and rule.strip() and isinstance(side, str) and side.strip():
                covered_rule_sides.add((category, rule.strip(), side.strip()))
    if covered_categories != CATEGORIES:
        problems.append("cases must cover success, failure, and boundary")

    coverage = contract.get("coverage")
    if not isinstance(coverage, list) or not coverage:
        problems.append("coverage must declare GDD-derived failure and boundary sides")
        coverage = []
    coverage_categories: set[str] = set()
    for index, item in enumerate(coverage):
        label = f"coverage[{index}]"
        if not isinstance(item, dict):
            problems.append(f"{label} must be an object")
            continue
        category, rule, sides = item.get("category"), item.get("rule"), item.get("required_sides")
        if category not in {"failure", "boundary"}:
            problems.append(f"{label}.category must be failure or boundary")
            continue
        coverage_categories.add(category)
        if not isinstance(rule, str) or not rule.strip():
            problems.append(f"{label}.rule must be a non-empty string")
            continue
        if not isinstance(sides, list) or not sides or len(sides) != len(set(sides)) or not all(
            isinstance(side, str) and side.strip() for side in sides
        ):
            problems.append(f"{label}.required_sides must contain every GDD-declared side as unique non-empty strings")
            continue
        for side in sides:
            key = (category, rule.strip(), side.strip())
            if key not in covered_rule_sides:
                problems.append(f"coverage side has no executable case: {category}/{rule}/{side}")
    if coverage_categories != {"failure", "boundary"}:
        problems.append("coverage must include at least one failure rule and one boundary rule")
    return contract, problems, bot_path


def audit(project: Path, report_path: Path | None, contract_only: bool = False) -> list[str]:
    contract, problems, bot_path = audit_contract(project)
    if contract_only or problems:
        return problems
    report_path = report_path or project / "evidence" / "gameplay-audit.json"
    report = load_object(report_path, "gameplay report", problems)
    if not report:
        return problems
    if report.get("version") != 1:
        problems.append("gameplay report version must equal 1")
    if report.get("status") != "PASS":
        problems.append("gameplay report status must equal PASS")
    expected_hashes = {
        "contract_sha256": sha256(project / "GAMEPLAY_CONTRACT.json"),
        "index_sha256": sha256(project / "index.html"),
        "bot_sha256": sha256(bot_path) if bot_path else "",
    }
    for key, expected in expected_hashes.items():
        if report.get(key) != expected:
            problems.append(f"gameplay report {key} does not match current project")

    report_cases = report.get("cases")
    if not isinstance(report_cases, list):
        problems.append("gameplay report cases must be an array")
        report_cases = []
    by_name = {
        case.get("name"): case for case in report_cases
        if isinstance(case, dict) and isinstance(case.get("name"), str)
    }
    if len(by_name) != len(report_cases):
        problems.append("gameplay report case names must be unique non-empty strings")
    contract_names = {case["name"] for case in contract["cases"] if isinstance(case, dict) and "name" in case}
    if set(by_name) != contract_names:
        problems.append("gameplay report must contain exactly the contract cases")
    for expected_case in contract["cases"]:
        if not isinstance(expected_case, dict) or expected_case.get("name") not in by_name:
            continue
        actual = by_name[expected_case["name"]]
        for key in ("category", "rule", "side", "expected"):
            if key in expected_case and actual.get(key) != expected_case.get(key):
                problems.append(f"case {expected_case['name']} {key} does not match contract")
        if actual.get("pass") is not True:
            problems.append(f"case {expected_case['name']} did not pass")
        if "actual" not in actual:
            problems.append(f"case {expected_case['name']} must record actual result")
        elif actual.get("actual") != expected_case.get("expected"):
            problems.append(f"case {expected_case['name']} actual result does not equal expected")
        trace = actual.get("trace")
        if not isinstance(trace, list) or len(trace) < 2:
            problems.append(f"case {expected_case['name']} must include at least two real trace samples")
        assertions = actual.get("assertions")
        if not isinstance(assertions, list) or not assertions or not all(
            isinstance(item, str) and item.strip() for item in assertions
        ):
            problems.append(f"case {expected_case['name']} must include non-empty assertions")
    return problems


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="gameplay-audit-") as raw:
        project = Path(raw)
        (project / "scripts").mkdir()
        (project / "evidence").mkdir()
        (project / "index.html").write_text("<!doctype html><title>fixture</title>", encoding="utf-8")
        bot = project / "scripts" / "bot.js"
        bot.write_text("console.log('fixture')", encoding="utf-8")
        contract = {
            "version": 1, "source": "gdd-module-8", "bot": "scripts/bot.js",
            "required_categories": ["success", "failure", "boundary"],
            "coverage": [
                {"category": "failure", "rule": "strength", "required_sides": ["short", "long"]},
                {"category": "boundary", "rule": "hitbox", "required_sides": ["inside", "outside"]},
            ],
            "cases": [
                {"name": "success", "category": "success", "expected": "ready"},
                {"name": "short", "category": "failure", "rule": "strength", "side": "short", "expected": "gameover"},
                {"name": "long", "category": "failure", "rule": "strength", "side": "long", "expected": "gameover"},
                {"name": "inside", "category": "boundary", "rule": "hitbox", "side": "inside", "expected": "ready"},
                {"name": "outside", "category": "boundary", "rule": "hitbox", "side": "outside", "expected": "gameover"},
            ],
        }
        cp = project / "GAMEPLAY_CONTRACT.json"
        cp.write_text(json.dumps(contract), encoding="utf-8")
        cases = []
        for item in contract["cases"]:
            cases.append({**item, "actual": item["expected"], "pass": True,
                          "trace": [{"state": "start"}, {"state": item["expected"]}],
                          "assertions": ["actual terminal state equals expected"]})
        report = {
            "version": 1, "status": "PASS", "contract_sha256": sha256(cp),
            "index_sha256": sha256(project / "index.html"), "bot_sha256": sha256(bot),
            "cases": cases,
        }
        rp = project / "evidence" / "gameplay-audit.json"
        rp.write_text(json.dumps(report), encoding="utf-8")
        good = not audit(project, rp)

        single_contract = json.loads(json.dumps(contract))
        single_contract["coverage"][0] = {
            "category": "failure", "rule": "timer", "required_sides": ["time_up"]
        }
        single_contract["cases"] = [
            case for case in single_contract["cases"] if case["name"] not in {"short", "long"}
        ]
        single_contract["cases"].append({
            "name": "time-up", "category": "failure", "rule": "timer",
            "side": "time_up", "expected": "gameover",
        })
        cp.write_text(json.dumps(single_contract), encoding="utf-8")
        single_cases = [
            {**item, "actual": item["expected"], "pass": True,
             "trace": [{"state": "start"}, {"state": item["expected"]}],
             "assertions": ["actual terminal state equals expected"]}
            for item in single_contract["cases"]
        ]
        single_report = {
            "version": 1, "status": "PASS", "contract_sha256": sha256(cp),
            "index_sha256": sha256(project / "index.html"), "bot_sha256": sha256(bot),
            "cases": single_cases,
        }
        rp.write_text(json.dumps(single_report), encoding="utf-8")
        single_side = not audit(project, rp)

        empty_contract = json.loads(json.dumps(single_contract))
        empty_contract["coverage"][0]["required_sides"] = []
        cp.write_text(json.dumps(empty_contract), encoding="utf-8")
        empty_rejected = any(
            "every GDD-declared side" in problem
            for problem in audit(project, rp, contract_only=True)
        )

        bad_contract = json.loads(json.dumps(contract))
        bad_contract["cases"] = [case for case in bad_contract["cases"] if case["name"] != "long"]
        cp.write_text(json.dumps(bad_contract), encoding="utf-8")
        missing_side = any("strength/long" in problem for problem in audit(project, rp, contract_only=True))
        cp.write_text(json.dumps(contract), encoding="utf-8")
        bad_report = json.loads(json.dumps(report))
        bad_report["cases"] = [case for case in bad_report["cases"] if case["name"] != "outside"]
        rp.write_text(json.dumps(bad_report), encoding="utf-8")
        missing_case = any("exactly the contract cases" in problem for problem in audit(project, rp))
        wrong_actual_report = json.loads(json.dumps(report))
        wrong_actual_report["cases"][0]["actual"] = "gameover"
        rp.write_text(json.dumps(wrong_actual_report), encoding="utf-8")
        wrong_actual = any("actual result does not equal expected" in problem for problem in audit(project, rp))
    if good and single_side and empty_rejected and missing_side and missing_case and wrong_actual:
        print("GAMEPLAY_REPORT_SELFTEST: PASS")
        return 0
    print("GAMEPLAY_REPORT_SELFTEST: FAIL")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit gameplay contract and bot evidence")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--contract-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.project or not args.project.is_dir():
        print("FAIL: --project must be an existing directory")
        return 2
    problems = audit(args.project.resolve(), args.report.resolve() if args.report else None, args.contract_only)
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        print(f"GAMEPLAY_REPORT_AUDIT: FAIL ({len(problems)} problem(s))")
        return 1
    print("GAMEPLAY_REPORT_AUDIT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
