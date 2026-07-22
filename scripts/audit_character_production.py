#!/usr/bin/env python3
"""Audit the reference-character image-generation approval gate.

Projects using an identifiable uploaded character as an A/B gameplay role must
record the Seedream (or equivalent reference-image editor) path in
CHARACTER_PRODUCTION.json.  This script deliberately checks artifacts and
approval state instead of trusting prose in GDD.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


MANIFEST = "CHARACTER_PRODUCTION.json"
FORMAL_METHOD = "reference-image-generation"
FORMAL_ROLES = {"A", "B"}
PIPELINE_CONTROLLER_FILE = Path("/etc/pi/pipeline-controller.json")


def fail(message: str) -> None:
    print(f"FAIL: {message}")


def load_manifest(project: Path) -> tuple[dict[str, Any] | None, list[str]]:
    problems: list[str] = []
    path = project / MANIFEST
    if not path.is_file():
        return None, [f"missing {MANIFEST}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"invalid {MANIFEST}: {exc}"]
    if not isinstance(data, dict):
        problems.append(f"{MANIFEST} root must be an object")
        return None, problems
    return data, problems


def require_text(container: dict[str, Any], key: str, label: str, problems: list[str]) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        problems.append(f"{label} must be a non-empty string")
        return ""
    return value.strip()


def require_artifact(project: Path, value: Any, label: str, problems: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        problems.append(f"{label} must name a project-relative file")
        return
    rel = Path(value)
    if rel.is_absolute() or ".." in rel.parts:
        problems.append(f"{label} must stay inside the project: {value}")
        return
    path = project / rel
    if not path.is_file():
        problems.append(f"{label} artifact missing: {value}")
        return
    if path.stat().st_size <= 0:
        problems.append(f"{label} artifact is empty: {value}")


def require_project_path(value: Any, label: str, problems: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        problems.append(f"{label} must name a project-relative path")
        return ""
    rel = Path(value)
    if rel.is_absolute() or ".." in rel.parts:
        problems.append(f"{label} must stay inside the project: {value}")
        return ""
    return value.strip()


def artifact_path(project: Path, value: Any, label: str, problems: list[str]) -> Path | None:
    before = len(problems)
    require_artifact(project, value, label, problems)
    if len(problems) != before:
        return None
    return project / Path(value)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json_artifact(path: Path, label: str, problems: list[str]) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"{label} is not valid JSON: {exc}")
        return None
    if not isinstance(value, dict):
        problems.append(f"{label} root must be an object")
        return None
    return value


def audit_attempt_ledger(
    project: Path,
    report: dict[str, Any],
    phase: str,
    problems: list[str],
) -> None:
    ledger_value = report.get("attempt_ledger")
    ledger_path: Path | None
    if isinstance(ledger_value, str) and ledger_value.startswith("controller://"):
        controller: dict[str, Any] | None = None
        if PIPELINE_CONTROLLER_FILE.is_file():
            controller = load_json_artifact(
                PIPELINE_CONTROLLER_FILE, "pipeline controller identity", problems
            )
        state_dir = controller.get("audit_state_dir") if controller else os.environ.get("VISUAL_AUDIT_STATE_DIR")
        run_id = controller.get("task_id") if controller else os.environ.get("VISUAL_AUDIT_RUN_ID")
        ledger_id = ledger_value.removeprefix("controller://")
        if not state_dir or not run_id:
            problems.append("controller attempt ledger requires controller audit-state environment")
            return
        expected = hashlib.sha256(
            f"{run_id}\0{project.resolve()}".encode("utf-8")
        ).hexdigest()
        if ledger_id != expected:
            problems.append("controller attempt ledger id does not match this run/project")
            return
        ledger_path = Path(state_dir).resolve() / f"{ledger_id}.jsonl"
        if not ledger_path.is_file() or ledger_path.stat().st_size <= 0:
            problems.append("controller attempt ledger is missing or empty")
            return
    else:
        ledger_path = artifact_path(
            project, ledger_value, "visual audit attempt_ledger", problems
        )
    if ledger_path is None:
        return
    latest = 0
    try:
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        problems.append(f"visual audit attempt_ledger cannot be read: {exc}")
        return
    for index, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            problems.append(f"visual audit attempt_ledger is corrupt at line {index}")
            return
        if (
            isinstance(item, dict)
            and item.get("version") == 1
            and item.get("phase") == phase
            and isinstance(item.get("attempt"), int)
            and not isinstance(item.get("attempt"), bool)
        ):
            latest = max(latest, item["attempt"])
    if latest <= 0:
        problems.append(f"visual audit attempt_ledger has no {phase} entry")
    if report.get("attempt") != latest:
        problems.append(
            f"visual audit report attempt is stale ({report.get('attempt')!r} != ledger {latest})"
        )


def audit_visual_evidence(
    project: Path,
    data: dict[str, Any],
    seed: dict[str, Any],
    phase: str,
    problems: list[str],
) -> None:
    visual = data.get("visual")
    if not isinstance(visual, dict):
        problems.append("visual must be an object")
        return
    contract_path = artifact_path(project, visual.get("contract"), "visual.contract", problems)
    baseline_path = artifact_path(project, visual.get("baseline"), "visual.baseline", problems)
    audit_key = "seed_audit" if phase == "seed" else "production_audit"
    report_path = artifact_path(project, visual.get(audit_key), f"visual.{audit_key}", problems)
    index_path = project / "index.html"
    if not index_path.is_file():
        problems.append("index.html is required before visual approval")
    if not contract_path or not baseline_path or not report_path or not index_path.is_file():
        return
    report = load_json_artifact(report_path, f"visual.{audit_key}", problems)
    if report is None:
        return
    contract = load_json_artifact(contract_path, "visual.contract", problems)
    if contract is not None:
        approval_artifacts = contract.get("approval_artifacts")
        if not isinstance(approval_artifacts, list) or seed.get("frame") not in approval_artifacts:
            problems.append("seed.frame must be listed in VISUAL_CONTRACT.json approval_artifacts")
    if report.get("status") != "PASS":
        problems.append(f"visual.{audit_key} must record status=PASS")
    if report.get("phase") != phase:
        problems.append(f"visual.{audit_key}.phase must equal {phase}")
    audit_attempt_ledger(project, report, phase, problems)
    if report.get("contract_sha256") != sha256(contract_path):
        problems.append(f"visual.{audit_key} is stale: contract hash mismatch")
    if report.get("index_sha256") != sha256(index_path):
        problems.append(f"visual.{audit_key} is stale: index.html hash mismatch")
    if report.get("baseline_sha256") != sha256(baseline_path):
        problems.append(f"visual.{audit_key} is stale: baseline hash mismatch")
    preview_report = report
    if phase == "production":
        seed_report_path = artifact_path(
            project, visual.get("seed_audit"), "visual.seed_audit", problems
        )
        if seed_report_path:
            loaded_seed_report = load_json_artifact(
                seed_report_path, "visual.seed_audit", problems
            )
            if loaded_seed_report is not None:
                preview_report = loaded_seed_report
                if loaded_seed_report.get("status") != "PASS" or loaded_seed_report.get("phase") != "seed":
                    problems.append("visual.seed_audit must record a PASS seed audit")
                audit_attempt_ledger(project, loaded_seed_report, "seed", problems)
                if loaded_seed_report.get("contract_sha256") != sha256(contract_path):
                    problems.append("visual.seed_audit contract hash mismatch")
                if loaded_seed_report.get("baseline_sha256") != sha256(baseline_path):
                    problems.append("visual.seed_audit baseline hash mismatch")
    preview = seed.get("composition_preview")
    cases = preview_report.get("cases")
    screenshots = {
        item.get("screenshot")
        for item in cases
        if isinstance(cases, list) and isinstance(item, dict)
    } if isinstance(cases, list) else set()
    if preview not in screenshots:
        problems.append("seed.composition_preview must be a screenshot produced by the current visual audit")


def audit(project: Path, phase: str) -> list[str]:
    data, problems = load_manifest(project)
    if data is None:
        return problems

    if data.get("version") != 2:
        problems.append("version must equal 2")

    reference_character = data.get("reference_character")
    if not isinstance(reference_character, bool):
        problems.append("reference_character must be boolean")
        return problems

    role = require_text(data, "role", "role", problems).upper()
    if role not in {"A", "B", "C"}:
        problems.append("role must be A, B or C")

    code_only = data.get("user_requested_code_only", False)
    if not isinstance(code_only, bool):
        problems.append("user_requested_code_only must be boolean")
        return problems

    gate_active = reference_character and role in FORMAL_ROLES
    if not gate_active:
        print(f"INFO: reference-character hard gate not active (role={role or '?'})")
        return problems

    if code_only:
        require_text(data, "exception_evidence", "exception_evidence", problems)
        print("INFO: explicit user code-only exception recorded")
        return problems

    method = require_text(data, "formal_visual_method", "formal_visual_method", problems)
    if method != FORMAL_METHOD:
        problems.append(
            f"formal_visual_method must be {FORMAL_METHOD}; Canvas/placeholder art cannot be the formal hero"
        )

    references = data.get("reference_images")
    if not isinstance(references, list) or not references:
        problems.append("reference_images must contain at least one project-relative file")
    else:
        for index, value in enumerate(references):
            require_artifact(project, value, f"reference_images[{index}]", problems)

    generator = data.get("generator")
    if not isinstance(generator, dict):
        problems.append("generator must be an object")
    else:
        require_text(generator, "tool", "generator.tool", problems)
        if generator.get("reference_used") is not True:
            problems.append("generator.reference_used must be true")

    seed = data.get("seed")
    if not isinstance(seed, dict):
        problems.append("seed must be an object")
        return problems
    if phase == "draft":
        require_project_path(seed.get("frame"), "seed.frame", problems)
        require_project_path(seed.get("composition_preview"), "seed.composition_preview", problems)
        require_project_path(seed.get("action_beat_preview"), "seed.action_beat_preview", problems)
        if seed.get("action_beat_preview_method") != "diagram-from-seed":
            problems.append("seed.action_beat_preview_method must equal diagram-from-seed")
        approval = seed.get("approval")
        if not isinstance(approval, dict) or approval.get("status") != "pending":
            problems.append("draft phase requires seed.approval.status=pending")
        actions = data.get("actions")
        if not isinstance(actions, list) or actions:
            problems.append("draft phase requires actions=[]")
        planned = data.get("planned_actions")
        if not isinstance(planned, list):
            problems.append("planned_actions must be an array")
        visual = data.get("visual")
        if not isinstance(visual, dict):
            problems.append("visual must be an object")
        else:
            require_artifact(project, visual.get("contract"), "visual.contract", problems)
            for key in ("baseline", "seed_audit", "production_audit"):
                require_project_path(visual.get(key), f"visual.{key}", problems)
        return problems
    require_artifact(project, seed.get("frame"), "seed.frame", problems)
    require_artifact(project, seed.get("composition_preview"), "seed.composition_preview", problems)
    require_artifact(project, seed.get("action_beat_preview"), "seed.action_beat_preview", problems)
    if seed.get("action_beat_preview_method") != "diagram-from-seed":
        problems.append("seed.action_beat_preview_method must equal diagram-from-seed")
    audit_visual_evidence(project, data, seed, phase, problems)

    approval = seed.get("approval")
    if not isinstance(approval, dict):
        problems.append("seed.approval must be an object")
        return problems
    status = require_text(approval, "status", "seed.approval.status", problems)
    if phase == "seed":
        actions = data.get("actions")
        if not isinstance(actions, list) or actions:
            problems.append("seed phase requires actions=[]; planned actions belong in planned_actions until approval")
        if status not in {"pending", "approved"}:
            problems.append("seed phase approval status must be pending or approved")
        return problems

    if status != "approved":
        problems.append("production phase requires seed.approval.status=approved")
    require_text(approval, "evidence", "seed.approval.evidence", problems)

    actions = data.get("actions")
    if not isinstance(actions, list) or not actions:
        problems.append("production phase requires at least one whitelisted action")
        return problems
    seen: set[str] = set()
    for index, action in enumerate(actions):
        label = f"actions[{index}]"
        if not isinstance(action, dict):
            problems.append(f"{label} must be an object")
            continue
        name = require_text(action, "name", f"{label}.name", problems)
        if name in seen:
            problems.append(f"duplicate action name: {name}")
        seen.add(name)
        for key in ("strip", "frames_dir", "meta", "preview"):
            value = action.get(key)
            if key == "frames_dir":
                if not isinstance(value, str) or not value.strip():
                    problems.append(f"{label}.{key} must name a project-relative directory")
                    continue
                rel = Path(value)
                if rel.is_absolute() or ".." in rel.parts or not (project / rel).is_dir():
                    problems.append(f"{label}.{key} directory missing or outside project: {value}")
            else:
                require_artifact(project, value, f"{label}.{key}", problems)
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit reference-character Seed/production gates")
    parser.add_argument("--project", required=True, type=Path, help="project root")
    parser.add_argument("--phase", required=True, choices=("draft", "seed", "production"))
    args = parser.parse_args()

    project = args.project.resolve()
    if not project.is_dir():
        fail(f"project directory missing: {project}")
        return 1

    problems = audit(project, args.phase)
    if problems:
        for problem in problems:
            fail(problem)
        print(f"CHARACTER_PRODUCTION_AUDIT: FAIL ({len(problems)} problem(s))")
        return 1
    print(f"CHARACTER_PRODUCTION_AUDIT: PASS phase={args.phase}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
