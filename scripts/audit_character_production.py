#!/usr/bin/env python3
"""Audit recorded reference-character and Sprite production artifacts.

This is a post-generation diagnostic.  It never authorizes image generation and
does not require a user-approval state or visual-audit report.
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


def load_manifest(project: Path, problems: list[str]) -> dict[str, Any] | None:
    path = project / MANIFEST
    if not path.is_file():
        problems.append(f"missing {MANIFEST}")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"invalid {MANIFEST}: {exc}")
        return None
    if not isinstance(value, dict):
        problems.append(f"{MANIFEST} root must be an object")
        return None
    return value


def text(container: dict[str, Any], key: str, label: str, problems: list[str]) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        problems.append(f"{label} must be a non-empty string")
        return ""
    return value.strip()


def relative(project: Path, value: Any, label: str, problems: list[str], directory: bool = False) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        problems.append(f"{label} must name a project-relative {'directory' if directory else 'file'}")
        return None
    rel = Path(value)
    if rel.is_absolute() or ".." in rel.parts:
        problems.append(f"{label} must stay inside project: {value}")
        return None
    target = project / rel
    valid = target.is_dir() if directory else target.is_file() and target.stat().st_size > 0
    if not valid:
        problems.append(f"{label} missing or empty: {value}")
        return None
    return target


def optional_file(project: Path, value: Any, label: str, problems: list[str]) -> None:
    if value not in {None, ""}:
        relative(project, value, label, problems)


def audit(project: Path, phase: str) -> list[str]:
    problems: list[str] = []
    data = load_manifest(project, problems)
    if data is None:
        return problems
    if data.get("version") != 2:
        problems.append("version must equal 2")
    reference_character = data.get("reference_character")
    if not isinstance(reference_character, bool):
        problems.append("reference_character must be boolean")
        return problems
    role = text(data, "role", "role", problems).upper()
    if role not in {"A", "B", "C"}:
        problems.append("role must be A, B or C")
    code_only = data.get("user_requested_code_only", False)
    if not isinstance(code_only, bool):
        problems.append("user_requested_code_only must be boolean")
        return problems
    if not reference_character or role not in FORMAL_ROLES or code_only:
        return problems

    if text(data, "formal_visual_method", "formal_visual_method", problems) != FORMAL_METHOD:
        problems.append(f"formal_visual_method must be {FORMAL_METHOD}")
    references = data.get("reference_images")
    if not isinstance(references, list) or not references:
        problems.append("reference_images must contain at least one project-relative file")
    else:
        for index, value in enumerate(references):
            relative(project, value, f"reference_images[{index}]", problems)
    generator = data.get("generator")
    if not isinstance(generator, dict):
        problems.append("generator must be an object")
    else:
        text(generator, "tool", "generator.tool", problems)
        if generator.get("reference_used") is not True:
            problems.append("generator.reference_used must be true")

    seed = data.get("seed")
    if not isinstance(seed, dict):
        problems.append("seed must be an object")
        return problems
    if phase == "draft":
        frame = seed.get("frame")
        if not isinstance(frame, str) or not frame.strip():
            problems.append("seed.frame must name the planned project-relative file")
        return problems
    relative(project, seed.get("frame"), "seed.frame", problems)
    optional_file(project, seed.get("composition_preview"), "seed.composition_preview", problems)
    optional_file(project, seed.get("action_beat_preview"), "seed.action_beat_preview", problems)
    if phase == "seed":
        return problems

    planned = data.get("planned_actions", [])
    actions = data.get("actions", [])
    if not isinstance(planned, list):
        problems.append("planned_actions must be an array")
        planned = []
    if not isinstance(actions, list):
        problems.append("actions must be an array")
        return problems
    planned_names = {
        item.get("name") for item in planned
        if isinstance(item, dict) and isinstance(item.get("name"), str) and item.get("name").strip()
    }
    seen: set[str] = set()
    for index, action in enumerate(actions):
        label = f"actions[{index}]"
        if not isinstance(action, dict):
            problems.append(f"{label} must be an object")
            continue
        name = text(action, "name", f"{label}.name", problems)
        if name in seen:
            problems.append(f"duplicate action name: {name}")
        seen.add(name)
        relative(project, action.get("strip"), f"{label}.strip", problems)
        relative(project, action.get("frames_dir"), f"{label}.frames_dir", problems, directory=True)
        relative(project, action.get("meta"), f"{label}.meta", problems)
        relative(project, action.get("preview"), f"{label}.preview", problems)
    missing = sorted(planned_names - seen)
    if missing:
        problems.append(f"planned actions missing production records: {', '.join(missing)}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--phase", required=True, choices=("draft", "seed", "production"))
    args = parser.parse_args()
    project = args.project.resolve()
    if not project.is_dir():
        print(f"FAIL: project directory missing: {project}")
        return 2
    problems = audit(project, args.phase)
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        print(f"CHARACTER_PRODUCTION_AUDIT: FAIL ({len(problems)} problem(s))")
        return 1
    print(f"CHARACTER_PRODUCTION_AUDIT: PASS phase={args.phase}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
