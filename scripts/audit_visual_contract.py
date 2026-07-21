#!/usr/bin/env python3
"""Validate a requirement-derived visual/camera contract.

The contract records an agent's reasoning and runtime assertions.  It is not a
form that selects a camera preset.  This audit intentionally rejects routing
fields that turn a game label or user form choice into a camera decision.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


CONTRACT = "VISUAL_CONTRACT.json"
BEHAVIORS = {"static", "locked", "transition", "settled"}
MEASUREMENTS = {"visible-pixels", "geometry"}
SPACES = {"world", "hud"}
FORBIDDEN_KEYS = {
    "camera_type",
    "selected_camera_type",
    "game_type_route",
    "template_camera",
    "form_selection",
    "user_selected_camera",
}


def fail(message: str) -> None:
    print(f"FAIL: {message}")


def text(value: Any, label: str, problems: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        problems.append(f"{label} must be a non-empty string")
        return ""
    return value.strip()


def string_list(
    value: Any,
    label: str,
    problems: list[str],
    *,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        problems.append(f"{label} must be an array")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            problems.append(f"{label}[{index}] must be a non-empty string")
            continue
        result.append(item.strip())
    if not allow_empty and not result:
        problems.append(f"{label} must not be empty")
    if len(result) != len(set(result)):
        problems.append(f"{label} must not contain duplicates")
    return result


def find_forbidden_keys(value: Any, path: str, problems: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in FORBIDDEN_KEYS:
                problems.append(
                    f"{child_path} is forbidden: derive a composed policy from requirements, not a form/type route"
                )
            find_forbidden_keys(child, child_path, problems)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            find_forbidden_keys(child, f"{path}[{index}]", problems)


def project_file(project: Path, value: Any, label: str, problems: list[str]) -> Path | None:
    rel_text = text(value, label, problems)
    if not rel_text:
        return None
    rel = Path(rel_text)
    if rel.is_absolute() or ".." in rel.parts:
        problems.append(f"{label} must stay inside project: {rel_text}")
        return None
    path = project / rel
    if not path.is_file() or path.stat().st_size <= 0:
        problems.append(f"{label} missing or empty: {rel_text}")
        return None
    return path


def audit(project: Path) -> tuple[dict[str, Any] | None, list[str]]:
    problems: list[str] = []
    path = project / CONTRACT
    if not path.is_file():
        return None, [f"missing {CONTRACT}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"invalid {CONTRACT}: {exc}"]
    if not isinstance(data, dict):
        return None, [f"{CONTRACT} root must be an object"]

    find_forbidden_keys(data, "", problems)
    if data.get("version") != 1:
        problems.append("version must equal 1")
    if data.get("source") != "requirement-analysis":
        problems.append("source must equal requirement-analysis")

    reasoning = data.get("reasoning")
    if not isinstance(reasoning, dict):
        problems.append("reasoning must be an object")
        reasoning = {}
    text(reasoning.get("player_decision"), "reasoning.player_decision", problems)
    must_see = string_list(reasoning.get("must_see"), "reasoning.must_see", problems)
    sensitive = string_list(
        reasoning.get("reference_sensitive_states"),
        "reasoning.reference_sensitive_states",
        problems,
        allow_empty=True,
    )
    retarget_events = string_list(
        reasoning.get("retarget_events"),
        "reasoning.retarget_events",
        problems,
        allow_empty=True,
    )

    entities = data.get("entities")
    if not isinstance(entities, dict) or not entities:
        problems.append("entities must be a non-empty object")
        entities = {}
    for name, entity in entities.items():
        label = f"entities.{name}"
        if not isinstance(entity, dict):
            problems.append(f"{label} must be an object")
            continue
        role = text(entity.get("role"), f"{label}.role", problems)
        if entity.get("space") not in SPACES:
            problems.append(f"{label}.space must be world or hud")
        if entity.get("measurement") not in MEASUREMENTS:
            problems.append(f"{label}.measurement must be visible-pixels or geometry")
        for key in ("min_visible_width_px", "min_visible_height_px"):
            if key in entity and (
                not isinstance(entity[key], (int, float))
                or isinstance(entity[key], bool)
                or entity[key] <= 0
            ):
                problems.append(f"{label}.{key} must be a positive number")
        if role == "primary" and not any(
            isinstance(entity.get(key), (int, float))
            and not isinstance(entity.get(key), bool)
            and entity.get(key) > 0
            for key in ("min_visible_width_px", "min_visible_height_px")
        ):
            problems.append(
                f"{label} primary entity must derive min_visible_width_px or min_visible_height_px for the target device"
            )
    for name in must_see:
        if name not in entities:
            problems.append(f"reasoning.must_see references unknown entity: {name}")

    policy = data.get("policy")
    if not isinstance(policy, dict):
        problems.append("policy must be an object")
        policy = {}
    framing_subjects = string_list(
        policy.get("framing_subjects"), "policy.framing_subjects", problems
    )
    lock_states = string_list(
        policy.get("lock_states"), "policy.lock_states", problems, allow_empty=True
    )
    retarget_on = string_list(
        policy.get("retarget_on"), "policy.retarget_on", problems, allow_empty=True
    )
    settle_before = string_list(
        policy.get("settle_before_states"),
        "policy.settle_before_states",
        problems,
        allow_empty=True,
    )
    text(policy.get("rationale"), "policy.rationale", problems)
    for name in framing_subjects:
        if name not in entities:
            problems.append(f"policy.framing_subjects references unknown entity: {name}")
        elif entities[name].get("space") != "world":
            problems.append(f"policy.framing_subjects may only reference world entities: {name}")
    for state in sensitive:
        if state not in lock_states and state not in settle_before:
            problems.append(
                f"reference-sensitive state {state!r} has no stability policy in lock_states/settle_before_states"
            )
    if set(retarget_events) != set(retarget_on):
        problems.append("policy.retarget_on must account for every reasoning.retarget_events item")

    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        problems.append("cases must be a non-empty array")
        cases = []
    case_names: set[str] = set()
    case_required: dict[str, list[str]] = {}
    case_states: set[str] = set()
    stable_case_states: set[str] = set()
    visible_coverage: set[str] = set()
    covered_retarget_events: set[str] = set()
    for index, case in enumerate(cases):
        label = f"cases[{index}]"
        if not isinstance(case, dict):
            problems.append(f"{label} must be an object")
            continue
        name = text(case.get("name"), f"{label}.name", problems)
        state = text(case.get("state"), f"{label}.state", problems)
        if name in case_names:
            problems.append(f"duplicate case name: {name}")
        case_names.add(name)
        case_states.add(state)
        behavior = case.get("behavior")
        if behavior not in BEHAVIORS:
            problems.append(f"{label}.behavior must be one of {sorted(BEHAVIORS)}")
        if behavior in {"static", "locked", "settled"}:
            stable_case_states.add(state)
        if behavior == "transition":
            trigger = text(case.get("trigger_event"), f"{label}.trigger_event", problems)
            if trigger:
                covered_retarget_events.add(trigger)
                if trigger not in retarget_events:
                    problems.append(f"{label}.trigger_event is not declared by reasoning.retarget_events: {trigger}")
        required = string_list(case.get("required_visible"), f"{label}.required_visible", problems)
        if name:
            case_required[name] = required
        for entity in required:
            visible_coverage.add(entity)
            if entity not in entities:
                problems.append(f"{label}.required_visible references unknown entity: {entity}")
        max_frames = case.get("max_frames")
        if not isinstance(max_frames, int) or isinstance(max_frames, bool) or not 1 <= max_frames <= 600:
            problems.append(f"{label}.max_frames must be an integer in 1..600")
        for key in (
            "min_visible_ratio",
            "max_hud_overlap_ratio",
            "lock_tolerance_px",
            "lock_tolerance_zoom",
            "settle_tolerance_px",
            "settle_tolerance_zoom",
        ):
            if key in case and (
                not isinstance(case[key], (int, float))
                or isinstance(case[key], bool)
                or case[key] < 0
            ):
                problems.append(f"{label}.{key} must be a non-negative number")

    for state in sensitive:
        if state not in case_states:
            problems.append(f"reference-sensitive state has no runtime case: {state}")
        elif state not in stable_case_states:
            problems.append(f"reference-sensitive state has no stable runtime assertion: {state}")
    for state in settle_before:
        if state not in stable_case_states:
            problems.append(f"settle-before state has no settled/locked/static runtime case: {state}")
    for entity in must_see:
        if entity not in visible_coverage:
            problems.append(f"must-see entity is never asserted by a runtime case: {entity}")
    for event in retarget_events:
        if event not in covered_retarget_events:
            problems.append(f"retarget event has no transition runtime case: {event}")

    baseline = data.get("baseline")
    if not isinstance(baseline, dict):
        problems.append("baseline must be an object")
        baseline = {}
    primary = text(baseline.get("primary_entity"), "baseline.primary_entity", problems)
    if primary and primary not in entities:
        problems.append(f"baseline.primary_entity references unknown entity: {primary}")
    elif primary and entities[primary].get("space") != "world":
        problems.append("baseline.primary_entity must reference a world entity")
    capture_cases = string_list(
        baseline.get("capture_cases"), "baseline.capture_cases", problems
    )
    for name in capture_cases:
        if name not in case_names:
            problems.append(f"baseline.capture_cases references unknown case: {name}")
        elif primary and primary not in case_required.get(name, []):
            problems.append(f"baseline capture case {name} must require primary entity {primary}")
    for key in ("max_primary_area_delta_ratio", "max_group_area_delta_ratio"):
        value = baseline.get(key)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not 0 <= value <= 1
        ):
            problems.append(f"baseline.{key} must be a number in 0..1")

    artifacts = string_list(data.get("artifacts"), "artifacts", problems)
    if "index.html" not in artifacts:
        problems.append("artifacts must include index.html")
    for index, artifact in enumerate(artifacts):
        project_file(project, artifact, f"artifacts[{index}]", problems)
    approval_artifacts = string_list(
        data.get("approval_artifacts", []),
        "approval_artifacts",
        problems,
        allow_empty=True,
    )
    for index, artifact in enumerate(approval_artifacts):
        if artifact not in artifacts:
            problems.append(f"approval_artifacts[{index}] must also appear in artifacts: {artifact}")
        project_file(project, artifact, f"approval_artifacts[{index}]", problems)

    viewport = data.get("viewport")
    if not isinstance(viewport, dict):
        problems.append("viewport must be an object")
    else:
        for key in ("width", "height"):
            value = viewport.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                problems.append(f"viewport.{key} must be a positive integer")

    return data, problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit requirement-derived visual contract")
    parser.add_argument("--project", required=True, type=Path, help="project root")
    args = parser.parse_args()
    project = args.project.resolve()
    if not project.is_dir():
        fail(f"project directory missing: {project}")
        return 1
    _, problems = audit(project)
    if problems:
        for problem in problems:
            fail(problem)
        print(f"VISUAL_CONTRACT_AUDIT: FAIL ({len(problems)} problem(s))")
        return 1
    print("VISUAL_CONTRACT_AUDIT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
