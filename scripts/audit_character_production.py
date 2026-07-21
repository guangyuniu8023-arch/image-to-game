#!/usr/bin/env python3
"""Audit the reference-character image-generation approval gate.

Projects using an identifiable uploaded character as an A/B gameplay role must
record the Seedream (or equivalent reference-image editor) path in
CHARACTER_PRODUCTION.json.  This script deliberately checks artifacts and
approval state instead of trusting prose in GDD.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


MANIFEST = "CHARACTER_PRODUCTION.json"
FORMAL_METHOD = "reference-image-generation"
FORMAL_ROLES = {"A", "B"}


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


def audit(project: Path, phase: str) -> list[str]:
    data, problems = load_manifest(project)
    if data is None:
        return problems

    if data.get("version") != 1:
        problems.append("version must equal 1")

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
    require_artifact(project, seed.get("frame"), "seed.frame", problems)
    require_artifact(project, seed.get("composition_preview"), "seed.composition_preview", problems)
    require_artifact(project, seed.get("action_beat_preview"), "seed.action_beat_preview", problems)

    approval = seed.get("approval")
    if not isinstance(approval, dict):
        problems.append("seed.approval must be an object")
        return problems
    status = require_text(approval, "status", "seed.approval.status", problems)
    if phase == "seed":
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
    parser.add_argument("--phase", required=True, choices=("seed", "production"))
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
