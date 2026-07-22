#!/usr/bin/env python3
"""Run authoritative image-to-game stage gates and emit stable diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable


STAGES = {"design", "seed", "production"}
PIPELINE_CONTROLLER_FILE = Path("/etc/pi/pipeline-controller.json")


def deferred_to_controller(
    stage: str, controller_preflight: bool, controller_path: Path = PIPELINE_CONTROLLER_FILE
) -> bool:
    if not controller_path.is_file():
        return False
    return not (controller_preflight and stage == "design")


def classify(problem: str) -> str:
    lowered = problem.lower()
    if "gameplay" in lowered:
        return "gameplay-contract"
    if "character" in lowered or "seed." in lowered or "reference_" in lowered:
        return "character-production"
    if (
        "visual_runtime" in lowered or "visual-runtime" in lowered
        or "visual runtime" in lowered or "camera" in lowered
    ):
        return "visual-runtime"
    if "visual" in lowered or "viewport" in lowered or "retarget" in lowered:
        return "visual-contract"
    if "index.html" in lowered or "runCase" in problem or "window.__game" in problem:
        return "runtime-harness"
    return "pipeline"


def normalize_problem(project: Path, value: str) -> str:
    text = value.replace(str(project), "<project>").strip()
    text = re.sub(r"\bsample \d+\b", "sample <n>", text)
    text = re.sub(r"\s+", " ", text)
    return text


def signature(project: Path, problems: Iterable[str]) -> str:
    stable = sorted(normalize_problem(project, problem) for problem in problems)
    payload = "\n".join(stable).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def run_command(
    command: list[str], label: str, problems: list[str], checks: list[dict], timeout: float = 45
) -> None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        checks.append({"name": label, "status": "FAIL"})
        problems.append(f"{label}: timed out after {timeout:g}s")
        return
    except OSError as exc:
        checks.append({"name": label, "status": "FAIL"})
        problems.append(f"{label}: could not start: {exc}")
        return
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    checks.append({"name": label, "status": "PASS" if result.returncode == 0 else "FAIL"})
    if result.returncode != 0:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        details = [line for line in lines if line.startswith("FAIL:")]
        if not details:
            details = lines[-5:] or [f"{label} exited {result.returncode}"]
        problems.extend(f"{label}: {line.removeprefix('FAIL:').strip()}" for line in details)


def audit_harness(project: Path, problems: list[str], checks: list[dict]) -> None:
    index = project / "index.html"
    missing: list[str] = []
    if not index.is_file() or index.stat().st_size <= 0:
        missing.append("index.html is missing or empty")
    else:
        source = index.read_text(encoding="utf-8", errors="replace")
        for token in ("window.__game", "visualAudit", "snapshot", "runCase"):
            if token not in source:
                missing.append(f"index.html is missing deterministic harness token {token}")
        readiness_patterns = (
            r"\bready\s*:",
            r"\bget\s+ready\s*\(",
            r"window\.__game\.ready\s*=",
        )
        if not any(re.search(pattern, source) for pattern in readiness_patterns):
            missing.append("index.html is missing window.__game.ready readiness exposure")
    checks.append({"name": "runtime-harness", "status": "FAIL" if missing else "PASS"})
    problems.extend(f"runtime-harness: {item}" for item in missing)


def audit_stage(
    project: Path, stage: str, require_character_draft: bool, run_design_runtime: bool = True,
    run_id: str | None = None,
) -> dict:
    scripts = Path(__file__).resolve().parent
    problems: list[str] = []
    checks: list[dict] = []
    if not (project / "GDD.md").is_file():
        problems.append("design: missing GDD.md")
        checks.append({"name": "gdd", "status": "FAIL"})
    else:
        checks.append({"name": "gdd", "status": "PASS"})
    run_command(
        [sys.executable, str(scripts / "audit_gameplay_report.py"), "--project", str(project), "--contract-only"],
        "gameplay-contract", problems, checks,
    )
    run_command(
        [sys.executable, str(scripts / "audit_visual_contract.py"), "--project", str(project)],
        "visual-contract", problems, checks,
    )
    audit_harness(project, problems, checks)
    manifest_exists = (project / "CHARACTER_PRODUCTION.json").is_file()
    if (stage == "design" and (require_character_draft or manifest_exists)) or stage == "seed":
        phase = "draft"
        run_command(
            [sys.executable, str(scripts / "audit_character_production.py"), "--project", str(project), "--phase", phase],
            f"character-{phase}", problems, checks,
        )
    if stage == "design" and run_design_runtime and not problems:
        command = ["node", str(scripts / "audit_visual_runtime.js"), "--project", str(project),
                   "--phase", "design", "--out", str(project / "evidence/visual-design-audit.json")]
        if run_id:
            command.extend(["--run-id", run_id])
        run_command(
            command,
            "visual-runtime-design", problems, checks,
        )
    if stage == "seed" and not problems:
        command = ["node", str(scripts / "audit_visual_runtime.js"), "--project", str(project), "--phase", "seed",
                   "--out", str(project / "evidence/visual-seed-audit.json")]
        if run_id:
            command.extend(["--run-id", run_id])
        run_command(
            command,
            "visual-runtime-seed", problems, checks,
        )
        if not problems:
            run_command(
                [sys.executable, str(scripts / "audit_character_production.py"), "--project", str(project), "--phase", "seed"],
                "character-seed-final", problems, checks,
            )
    if stage == "production" and not problems:
        command = ["node", str(scripts / "audit_visual_runtime.js"), "--project", str(project), "--phase", "production",
                   "--out", str(project / "evidence/visual-production-audit.json")]
        baseline = project / "evidence/visual-baseline.json"
        if baseline.is_file():
            command.extend(["--baseline", str(baseline)])
        if run_id:
            command.extend(["--run-id", run_id])
        run_command(
            command,
            "visual-runtime-production", problems, checks,
        )
        if not problems:
            run_command(
                [sys.executable, str(scripts / "audit_gameplay_report.py"), "--project", str(project)],
                "gameplay-evidence", problems, checks,
            )
            run_command(
                [sys.executable, str(scripts / "audit_character_production.py"), "--project", str(project), "--phase", "production"],
                "character-production-final", problems, checks,
            )
    problems = list(dict.fromkeys(normalize_problem(project, problem) for problem in problems))
    categories = sorted({classify(problem) for problem in problems})
    return {
        "version": 1,
        "stage": stage,
        "status": "FAIL" if problems else "PASS",
        "failure_signature": signature(project, problems) if problems else None,
        "categories": categories,
        "checks": checks,
        "problems": problems,
    }


def write_report(project: Path, stage: str, report: dict, output: Path | None) -> Path:
    path = output or project / "evidence" / f"pipeline-{stage}-audit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="pipeline-stage-") as raw:
        project = Path(raw)
        (project / "scripts").mkdir()
        (project / "evidence").mkdir()
        (project / "GDD.md").write_text("# fixture\n", encoding="utf-8")
        (project / "scripts/bot.js").write_text("// fixture\n", encoding="utf-8")
        (project / "index.html").write_text(
            "<script>window.__game={ready:true,visualAudit:{snapshot(){},runCase(){}}}</script>",
            encoding="utf-8",
        )
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from scaffold_gameplay_contract import build_contract  # pylint: disable=import-outside-toplevel

        contract = build_contract(
            "scripts/bot.js", ["win=ready"], ["timer:time_up:lose=gameover"],
            ["hitbox:inside:edge=ready"],
        )
        (project / "GAMEPLAY_CONTRACT.json").write_text(json.dumps(contract), encoding="utf-8")
        visual = {
            "version": 1, "source": "requirement-analysis", "viewport": {"width": 400, "height": 700},
            "reasoning": {"player_decision": "judge target", "must_see": ["player"],
                          "reference_sensitive_states": [], "retarget_events": []},
            "entities": {"player": {"role": "primary", "space": "world", "measurement": "visible-pixels",
                                         "min_visible_height_px": 80}},
            "policy": {"framing_subjects": ["player"], "lock_states": [], "retarget_on": [],
                       "settle_before_states": [], "rationale": "keep the player visible"},
            "cases": [{"name": "boot", "entry": "natural", "state": "ready", "behavior": "static",
                       "required_visible": ["player"], "required_render_sources": {
                           "player": {"seed": ["generated-seed"], "production": ["generated-seed"]}},
                       "max_frames": 1}],
            "baseline": {"primary_entity": "player", "capture_cases": ["boot"],
                         "max_primary_area_delta_ratio": 0.2, "max_group_area_delta_ratio": 0.2},
            "artifacts": ["index.html"], "approval_artifacts": [],
        }
        (project / "VISUAL_CONTRACT.json").write_text(json.dumps(visual), encoding="utf-8")
        good = audit_stage(project, "design", False, run_design_runtime=False)
        (project / "index.html").write_text(
            "<script>window.__game={visualAudit:{snapshot(){},runCase(){}}}</script>",
            encoding="utf-8",
        )
        missing_ready = audit_stage(project, "design", False, run_design_runtime=False)
        (project / "index.html").write_text(
            "<script>window.__game={ready:true,visualAudit:{snapshot(){},runCase(){}}}</script>",
            encoding="utf-8",
        )
        contract["source"] = "wrong"
        (project / "GAMEPLAY_CONTRACT.json").write_text(json.dumps(contract), encoding="utf-8")
        bad1 = audit_stage(project, "design", False, run_design_runtime=False)
        bad2 = audit_stage(project, "design", False, run_design_runtime=False)
        timeout_problems: list[str] = []
        timeout_checks: list[dict] = []
        run_command(
            [sys.executable, "-c", "import time; time.sleep(2)"],
            "bounded-command", timeout_problems, timeout_checks, timeout=0.05,
        )
        controller = project / "controller.json"
        controller.write_text("{}\n", encoding="utf-8")
        deferred = deferred_to_controller("seed", False, controller)
        design_preflight_allowed = not deferred_to_controller("design", True, controller)
    passed = (
        good["status"] == "PASS" and bad1["status"] == "FAIL"
        and missing_ready["status"] == "FAIL"
        and "runtime-harness" in missing_ready["categories"]
        and "gameplay-contract" in bad1["categories"]
        and bad1["failure_signature"] == bad2["failure_signature"]
        and timeout_checks == [{"name": "bounded-command", "status": "FAIL"}]
        and timeout_problems == ["bounded-command: timed out after 0.05s"]
        and deferred and design_preflight_allowed
    )
    if passed:
        print("PIPELINE_STAGE_AUDIT_SELFTEST: PASS")
        return 0
    print("PIPELINE_STAGE_AUDIT_SELFTEST: FAIL")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--stage", choices=sorted(STAGES))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--run-id", help="unique local task/build id; reuse only for its one repair retry")
    parser.add_argument("--require-character-draft", action="store_true")
    parser.add_argument("--controller-preflight", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.project or not args.stage:
        parser.error("--project and --stage are required")
    if deferred_to_controller(args.stage, args.controller_preflight):
        print(json.dumps({
            "status": "DEFERRED_TO_CONTROLLER",
            "stage": args.stage,
            "reason": "controller-backed Pi workers produce candidates; the external controller runs this gate",
        }, ensure_ascii=False))
        return 3
    if args.controller_preflight and args.stage != "design":
        parser.error("--controller-preflight is restricted to the design preflight")
    project = args.project.resolve()
    if not project.is_dir():
        print(f"PIPELINE_STAGE_AUDIT: FAIL missing project {project}", file=sys.stderr)
        return 2
    report = audit_stage(
        project, args.stage, args.require_character_draft,
        run_design_runtime=not args.controller_preflight,
        run_id=args.run_id,
    )
    path = write_report(project, args.stage, report, args.out)
    print(json.dumps({"status": report["status"], "stage": args.stage,
                      "failure_signature": report["failure_signature"], "report": str(path)},
                     ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
