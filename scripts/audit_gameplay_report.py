#!/usr/bin/env python3
"""Audit GDD-derived gameplay coverage and a bot's hash-bound evidence report."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any


CATEGORIES = {"success", "failure", "boundary"}


def finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


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


def bot_file(project: Path, value: Any, problems: list[str]) -> Path | None:
    if value == "skill:run_gameplay_runtime.js":
        path = Path(__file__).resolve().parent / "run_gameplay_runtime.js"
        if path.is_file() and path.stat().st_size > 0:
            return path
        problems.append("skill gameplay runner is missing or empty")
        return None
    return rel_file(project, value, "GAMEPLAY_CONTRACT.bot", problems)


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
    bot_path = bot_file(project, contract.get("bot"), problems)

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
    grouped_outcomes: dict[tuple[str, str], list[tuple[str, str]]] = {}
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
        expected = case.get("expected")
        if not isinstance(expected, str) or not expected.strip():
            problems.append(f"{label}.expected must be a non-empty semantic result string")
        driver = case.get("driver")
        if not isinstance(driver, dict):
            problems.append(f"{label}.driver must define runner-owned seed, fixed steps, setup, and inputs")
        else:
            seed = driver.get("seed")
            if not (
                (isinstance(seed, int) and not isinstance(seed, bool))
                or (isinstance(seed, str) and seed.strip())
            ):
                problems.append(f"{label}.driver.seed must be an integer or non-empty string")
            dt = driver.get("dt")
            if not finite_number(dt) or not 0 < dt <= 0.1:
                problems.append(f"{label}.driver.dt must be finite in (0, 0.1]")
            max_frames = driver.get("max_frames")
            if not isinstance(max_frames, int) or isinstance(max_frames, bool) or not 1 <= max_frames <= 1800:
                problems.append(f"{label}.driver.max_frames must be an integer in [1, 1800]")
            setup = driver.get("setup", {})
            if not isinstance(setup, dict):
                problems.append(f"{label}.driver.setup must be an object")
            inputs = driver.get("inputs")
            if not isinstance(inputs, list) or not inputs:
                problems.append(f"{label}.driver.inputs must contain runner-dispatched browser input")
            else:
                for input_index, item in enumerate(inputs):
                    input_label = f"{label}.driver.inputs[{input_index}]"
                    if not isinstance(item, dict):
                        problems.append(f"{input_label} must be an object")
                        continue
                    if not (
                        isinstance(item.get("frame"), int)
                        and not isinstance(item.get("frame"), bool)
                        and isinstance(max_frames, int)
                        and 1 <= item["frame"] <= max_frames
                    ):
                        problems.append(f"{input_label}.frame must stay inside fixed-step range")
                    if not isinstance(item.get("action"), str) or not item["action"].strip():
                        problems.append(f"{input_label}.action must be non-empty")
                    if item.get("phase") not in {"press", "release", "pressed", "released", "down", "up", "keydown", "keyup"}:
                        problems.append(f"{input_label}.phase must be a supported press/release phase")
                    if item.get("code") not in {"ArrowLeft", "ArrowUp", "ArrowRight", "ArrowDown", "Space", "KeyA", "KeyD", "KeyW", "KeyS"}:
                        problems.append(f"{input_label}.code must be a supported browser KeyboardEvent.code")
        rule, side = case.get("rule"), case.get("side")
        if category in {"failure", "boundary"}:
            if not isinstance(rule, str) or not rule.strip():
                problems.append(f"{label}.rule is required for {category}")
            if not isinstance(side, str) or not side.strip():
                problems.append(f"{label}.side is required for {category}")
            if isinstance(rule, str) and rule.strip() and isinstance(side, str) and side.strip():
                covered_rule_sides.add((category, rule.strip(), side.strip()))
                if isinstance(expected, str) and expected.strip():
                    grouped_outcomes.setdefault((category, rule.strip()), []).append((side.strip(), expected.strip()))
    for (category, rule), outcomes in grouped_outcomes.items():
        sides = {side for side, _ in outcomes}
        expected_values = [expected for _, expected in outcomes]
        if len(sides) > 1 and len(expected_values) != len(set(expected_values)):
            problems.append(
                f"{category}/{rule} has multiple sides but repeated expected values; "
                "each side must expose a distinct semantic outcome"
            )
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
    if report.get("driver_protocol") != "runner-controlled-v1":
        problems.append("gameplay report must use runner-controlled-v1")
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
        if actual.get("driver_protocol") != "runner-controlled-v1":
            problems.append(f"case {expected_case['name']} must be runner-controlled-v1")
        if actual.get("input_source") != "chromium-cdp":
            problems.append(f"case {expected_case['name']} must record chromium-cdp input source")
        if "actual" not in actual:
            problems.append(f"case {expected_case['name']} must record actual result")
        elif actual.get("actual") != expected_case.get("expected"):
            problems.append(f"case {expected_case['name']} actual result does not equal expected")
        trace = actual.get("trace")
        if not isinstance(trace, list) or len(trace) < 2:
            problems.append(f"case {expected_case['name']} must include at least two real trace samples")
        else:
            previous_frame = -1
            for index, sample in enumerate(trace):
                label = f"case {expected_case['name']} trace[{index}]"
                if not isinstance(sample, dict):
                    problems.append(f"{label} must be an object")
                    continue
                frame = sample.get("frame")
                if not isinstance(frame, int) or isinstance(frame, bool) or frame <= previous_frame:
                    problems.append(f"{label}.frame must be a strictly increasing non-negative integer")
                else:
                    previous_frame = frame
                if not isinstance(sample.get("state"), str) or not sample["state"].strip():
                    problems.append(f"{label}.state must be a non-empty string")
                position = sample.get("position")
                coords = [key for key in ("x", "y", "z") if isinstance(position, dict) and key in position]
                if not coords or not all(finite_number(position[key]) for key in coords):
                    problems.append(f"{label}.position must contain finite x/y/z evidence")
        seed = actual.get("seed")
        if not (
            (isinstance(seed, int) and not isinstance(seed, bool))
            or (isinstance(seed, str) and seed.strip())
        ):
            problems.append(f"case {expected_case['name']} must record a deterministic seed")
        dt = actual.get("dt")
        if not finite_number(dt) or not 0 < dt <= 0.1:
            problems.append(f"case {expected_case['name']} dt must be finite in (0, 0.1]")
        inputs = actual.get("inputs")
        if not isinstance(inputs, list) or not inputs:
            problems.append(f"case {expected_case['name']} must record semantic inputs")
        else:
            for index, item in enumerate(inputs):
                if not (
                    isinstance(item, dict)
                    and isinstance(item.get("frame"), int)
                    and not isinstance(item.get("frame"), bool)
                    and item["frame"] >= 0
                    and isinstance(item.get("action"), str)
                    and item["action"].strip()
                    and isinstance(item.get("phase"), str)
                    and item["phase"].strip()
                ):
                    problems.append(
                        f"case {expected_case['name']} inputs[{index}] must record frame/action/phase"
                    )
        terminal = actual.get("terminal")
        if not (
            isinstance(terminal, dict)
            and isinstance(terminal.get("state"), str)
            and terminal["state"].strip()
            and isinstance(terminal.get("reason"), str)
            and terminal["reason"].strip()
        ):
            problems.append(f"case {expected_case['name']} must record terminal state and reason")
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
                {"name": "short", "category": "failure", "rule": "strength", "side": "short", "expected": "gameover:short"},
                {"name": "long", "category": "failure", "rule": "strength", "side": "long", "expected": "gameover:long"},
                {"name": "inside", "category": "boundary", "rule": "hitbox", "side": "inside", "expected": "ready"},
                {"name": "outside", "category": "boundary", "rule": "hitbox", "side": "outside", "expected": "gameover"},
            ],
        }
        for item in contract["cases"]:
            item["driver"] = {
                "seed": 4242,
                "dt": 1 / 60,
                "max_frames": 6,
                "setup": {},
                "inputs": [
                    {"frame": 1, "action": "jump", "phase": "press", "code": "Space"},
                    {"frame": 2, "action": "jump", "phase": "release", "code": "Space"},
                ],
            }
        cp = project / "GAMEPLAY_CONTRACT.json"
        cp.write_text(json.dumps(contract), encoding="utf-8")
        def evidence(item: dict[str, Any]) -> dict[str, Any]:
            return {
                **item,
                "actual": item["expected"],
                "pass": True,
                "seed": 4242,
                "dt": 1 / 60,
                "inputs": [
                    {"frame": 0, "action": "jump", "phase": "press"},
                    {"frame": 6, "action": "jump", "phase": "release"},
                ],
                "trace": [
                    {"frame": 0, "state": "start", "position": {"x": 0, "y": 0}},
                    {"frame": 7, "state": item["expected"], "position": {"x": 64, "y": 0}},
                ],
                "terminal": {"state": item["expected"], "reason": "fixture rule result"},
                "assertions": ["actual terminal state equals expected"],
                "driver_protocol": "runner-controlled-v1",
                "input_source": "chromium-cdp",
            }
        cases = []
        for item in contract["cases"]:
            cases.append(evidence(item))
        report = {
            "version": 1, "status": "PASS", "driver_protocol": "runner-controlled-v1",
            "contract_sha256": sha256(cp),
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
            "driver": {
                "seed": 4242, "dt": 1 / 60, "max_frames": 6, "setup": {},
                "inputs": [
                    {"frame": 1, "action": "wait", "phase": "press", "code": "Space"},
                    {"frame": 2, "action": "wait", "phase": "release", "code": "Space"},
                ],
            },
        })
        cp.write_text(json.dumps(single_contract), encoding="utf-8")
        single_cases = [evidence(item) for item in single_contract["cases"]]
        single_report = {
            "version": 1, "status": "PASS", "driver_protocol": "runner-controlled-v1",
            "contract_sha256": sha256(cp),
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
        fake_hook_report = json.loads(json.dumps(report))
        for item in fake_hook_report["cases"]:
            item.pop("seed", None)
            item.pop("dt", None)
            item.pop("inputs", None)
            item.pop("terminal", None)
            item["trace"] = [{"state": "start"}, {"state": item["expected"]}]
        rp.write_text(json.dumps(fake_hook_report), encoding="utf-8")
        fake_hook_rejected = any(
            "deterministic seed" in problem or "semantic inputs" in problem
            for problem in audit(project, rp)
        )
        duplicate_contract = json.loads(json.dumps(contract))
        duplicate_contract["cases"][1]["expected"] = "gameover"
        duplicate_contract["cases"][2]["expected"] = "gameover"
        cp.write_text(json.dumps(duplicate_contract), encoding="utf-8")
        duplicate_outcome = any(
            "repeated expected values" in problem
            for problem in audit(project, rp, contract_only=True)
        )
    if (good and single_side and empty_rejected and missing_side and missing_case and
            wrong_actual and fake_hook_rejected and duplicate_outcome):
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
