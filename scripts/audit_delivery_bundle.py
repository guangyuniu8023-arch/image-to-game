#!/usr/bin/env python3
"""Verify that a staged/public game bundle is the exact audited build with all formal character assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


BUILD_META = re.compile(
    r'<meta\s+name=["\']game-build["\']\s+content=["\']([^"\']+)["\']\s*/?>',
    re.IGNORECASE,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, label: str, problems: list[str]) -> dict[str, Any]:
    if not path.is_file():
        problems.append(f"missing {label}: {path}")
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


def safe_rel(value: Any, label: str, problems: list[str]) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        problems.append(f"{label} must be a non-empty relative path")
        return None
    rel = Path(value)
    if rel.is_absolute() or ".." in rel.parts:
        problems.append(f"{label} must stay inside the bundle")
        return None
    return rel


def required_runtime_artifacts(source: Path, problems: list[str]) -> set[Path]:
    required = {Path("index.html")}
    visual = load(source / "VISUAL_CONTRACT.json", "VISUAL_CONTRACT.json", problems)
    for index, value in enumerate(visual.get("artifacts", [])):
        rel = safe_rel(value, f"VISUAL_CONTRACT.artifacts[{index}]", problems)
        if rel:
            required.add(rel)
    character_path = source / "CHARACTER_PRODUCTION.json"
    if character_path.is_file():
        character = load(character_path, "CHARACTER_PRODUCTION.json", problems)
        seed = character.get("seed") if isinstance(character.get("seed"), dict) else {}
        rel = safe_rel(seed.get("frame"), "CHARACTER_PRODUCTION.seed.frame", problems)
        if rel:
            required.add(rel)
        for index, action in enumerate(character.get("actions", [])):
            if not isinstance(action, dict):
                problems.append(f"CHARACTER_PRODUCTION.actions[{index}] must be an object")
                continue
            for key in ("strip", "meta"):
                if key in action:
                    rel = safe_rel(action.get(key), f"actions[{index}].{key}", problems)
                    if rel:
                        required.add(rel)
            frames_rel = safe_rel(action.get("frames_dir"), f"actions[{index}].frames_dir", problems)
            if frames_rel:
                frames_dir = source / frames_rel
                if not frames_dir.is_dir():
                    problems.append(f"actions[{index}].frames_dir missing: {frames_rel}")
                else:
                    frames = sorted(path for path in frames_dir.rglob("*") if path.is_file())
                    if not frames:
                        problems.append(f"actions[{index}].frames_dir is empty: {frames_rel}")
                    required.update(path.relative_to(source) for path in frames)
    for rel in sorted(required):
        path = source / rel
        if not path.is_file() or path.stat().st_size <= 0:
            problems.append(f"required source runtime artifact missing or empty: {rel}")
    return required


def meta_build_id(index_path: Path) -> str | None:
    try:
        match = BUILD_META.search(index_path.read_text(encoding="utf-8"))
    except OSError:
        return None
    return match.group(1).strip() if match else None


def audit(source: Path, delivery: Path) -> list[str]:
    problems: list[str] = []
    required = required_runtime_artifacts(source, problems)
    manifest = load(delivery / "DELIVERY_MANIFEST.json", "DELIVERY_MANIFEST.json", problems)
    if not manifest:
        return problems
    if manifest.get("version") != 1:
        problems.append("DELIVERY_MANIFEST.version must equal 1")
    build_id = manifest.get("build_id")
    if not isinstance(build_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{5,126}", build_id):
        problems.append("DELIVERY_MANIFEST.build_id must be a stable 6..127 character build identifier")
        build_id = ""
    if not isinstance(manifest.get("skill_commit"), str) or not manifest["skill_commit"].strip():
        problems.append("DELIVERY_MANIFEST.skill_commit is required for release provenance")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        problems.append("DELIVERY_MANIFEST.artifacts must be an object of relative-path to sha256")
        artifacts = {}
    manifest_paths: set[Path] = set()
    for raw_rel, digest in artifacts.items():
        rel = safe_rel(raw_rel, "DELIVERY_MANIFEST.artifacts key", problems)
        if not rel:
            continue
        manifest_paths.add(rel)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            problems.append(f"invalid sha256 for delivery artifact: {rel}")
            continue
        source_file, delivery_file = source / rel, delivery / rel
        if not source_file.is_file() or not delivery_file.is_file():
            problems.append(f"artifact missing from source or delivery: {rel}")
            continue
        if sha256(source_file) != digest:
            problems.append(f"manifest hash does not match source artifact: {rel}")
        if sha256(delivery_file) != digest:
            problems.append(f"delivery artifact differs from audited source: {rel}")
    missing = required - manifest_paths
    for rel in sorted(missing):
        problems.append(f"required runtime artifact missing from DELIVERY_MANIFEST: {rel}")
    source_index = source / "index.html"
    delivery_index = delivery / "index.html"
    if source_index.is_file() and manifest.get("source_index_sha256") != sha256(source_index):
        problems.append("DELIVERY_MANIFEST.source_index_sha256 does not match audited source")
    if build_id:
        if meta_build_id(source_index) != build_id:
            problems.append("source index.html game-build meta does not match DELIVERY_MANIFEST.build_id")
        if meta_build_id(delivery_index) != build_id:
            problems.append("delivery index.html game-build meta does not match DELIVERY_MANIFEST.build_id")
    return problems


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="delivery-audit-") as raw:
        root = Path(raw)
        source, delivery = root / "source", root / "delivery"
        for base in (source, delivery):
            (base / "assets" / "jump").mkdir(parents=True)
        build_id = "fixture-20260722"
        index = f'<!doctype html><meta name="game-build" content="{build_id}"><title>fixture</title>'
        for base in (source, delivery):
            (base / "index.html").write_text(index, encoding="utf-8")
            (base / "assets" / "seed.png").write_bytes(b"seed")
            (base / "assets" / "jump" / "01.png").write_bytes(b"frame")
            (base / "assets" / "jump" / "meta.json").write_text("{}", encoding="utf-8")
        (source / "VISUAL_CONTRACT.json").write_text(json.dumps({
            "artifacts": ["index.html", "assets/seed.png"]
        }), encoding="utf-8")
        (source / "CHARACTER_PRODUCTION.json").write_text(json.dumps({
            "seed": {"frame": "assets/seed.png"},
            "actions": [{"frames_dir": "assets/jump", "meta": "assets/jump/meta.json"}],
        }), encoding="utf-8")
        rels = [Path("index.html"), Path("assets/seed.png"), Path("assets/jump/01.png"), Path("assets/jump/meta.json")]
        manifest = {
            "version": 1, "build_id": build_id, "skill_commit": "fixture-commit",
            "source_index_sha256": sha256(source / "index.html"),
            "artifacts": {str(rel): sha256(source / rel) for rel in rels},
        }
        mp = delivery / "DELIVERY_MANIFEST.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        good = not audit(source, delivery)
        (delivery / "assets" / "jump" / "01.png").write_bytes(b"stale")
        stale = any("differs from audited source" in problem for problem in audit(source, delivery))
        (delivery / "assets" / "jump" / "01.png").write_bytes(b"frame")
        (delivery / "index.html").write_text(index.replace(build_id, "wrong-build"), encoding="utf-8")
        wrong_build = any("game-build meta" in problem for problem in audit(source, delivery))
    if good and stale and wrong_build:
        print("DELIVERY_BUNDLE_SELFTEST: PASS")
        return 0
    print("DELIVERY_BUNDLE_SELFTEST: FAIL")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a staged delivery against the audited source build")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--delivery", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.source or not args.delivery or not args.source.is_dir() or not args.delivery.is_dir():
        print("FAIL: --source and --delivery must be existing directories")
        return 2
    problems = audit(args.source.resolve(), args.delivery.resolve())
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        print(f"DELIVERY_BUNDLE_AUDIT: FAIL ({len(problems)} problem(s))")
        return 1
    print("DELIVERY_BUNDLE_AUDIT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
