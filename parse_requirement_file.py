#!/usr/bin/env python3
"""
Parse a dependency file and export its contents to a CSV table.

Columns: ecosystem, repo, filename, package, version

Example:
    python parse_requirement_file.py path/to/requirements.txt --repo my-repo \
        --output deps.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Sequence, Tuple


Ecosystem = str


PYTHON_HINTS = {
    "requirements.txt",
    "requirements-dev.txt",
    "requirements.in",
    "constraints.txt",
    "environment.yml",
    "environment.yaml",
    "setup.py",
    "setup.cfg",
    "pyproject.toml",
    "poetry.lock",
    "pdm.lock",
    "pdm.toml",
    "pipfile",
    "pipfile.lock",
}

NODE_HINTS = {
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "pnpm-lock.yml",
    "bun.lockb",
}


def infer_ecosystem(requirement_file: Path) -> Ecosystem:
    lower_name = requirement_file.name.lower()
    if lower_name in PYTHON_HINTS or lower_name.endswith(".txt"):
        return "python"
    if lower_name in NODE_HINTS:
        return "nodejs"
    if lower_name in {"gemfile", "gemfile.lock"}:
        return "ruby"
    if lower_name.endswith((".csproj", ".fsproj", ".vbproj")) or lower_name in {"packages.config"}:
        return "dotnet"
    if lower_name in {"pom.xml", "build.gradle", "build.gradle.kts"}:
        return "java"
    if lower_name in {"cargo.toml", "cargo.lock"}:
        return "rust"
    if lower_name in {"go.mod", "go.sum"}:
        return "go"
    if lower_name in {"composer.json", "composer.lock"}:
        return "php"
    return "unknown"


def detect_repo_root(file_path: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(file_path.parent), "rev-parse", "--show-toplevel"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return Path(result.stdout.decode().strip())


def infer_repo_context(requirement_file: Path, override: str | None = None) -> Tuple[str, Path | None]:
    git_root = detect_repo_root(requirement_file)
    if override:
        return override, git_root
    if git_root:
        return git_root.name, git_root
    return requirement_file.resolve().parents[1].name, None


def relative_filename(requirement_file: Path, repo_root: Path | None) -> str:
    if repo_root:
        try:
            return str(requirement_file.resolve().relative_to(repo_root))
        except ValueError:
            pass
    return str(requirement_file.resolve())


def parse_python_requirements(lines: Iterable[str]) -> Iterator[Tuple[str, str]]:
    req_regex = re.compile(
        r"""
        ^\s*
        (?P<name>[A-Za-z0-9_.-]+)
        (?P<extras>\[.*\])?
        (\s*(?P<op>==|~=|>=|<=|!=|===|>|<)\s*(?P<version>[^;\s]+))?
        """,
        re.VERBOSE,
    )
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-r", "--requirement", "--find-links", "--extra-index-url")):
            continue
        if line.startswith(("--hash", "--only-binary", "--prefer-binary")):
            continue
        line = re.split(r"\s+#", line, maxsplit=1)[0].strip()
        if ";" in line:
            line = line.split(";", 1)[0].strip()
        if " @" in line:
            name, url = [part.strip() for part in line.split("@", 1)]
            pkg = name.split()[0]
            yield pkg, f"@ {url}"
            continue
        match = req_regex.match(line)
        if not match:
            pkg = line
            version = ""
        else:
            pkg = match.group("name")
            if match.group("version"):
                version = match.group("version")
            else:
                version = ""
        yield pkg, version


def parse_package_json(path: Path) -> Iterator[Tuple[str, str]]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    sections = [
        "dependencies",
        "devDependencies",
        "peerDependencies",
        "optionalDependencies",
        "bundledDependencies",
    ]
    for section in sections:
        deps = data.get(section, {})
        if isinstance(deps, dict):
            for pkg, version in deps.items():
                if isinstance(version, str):
                    yield pkg, version


def walk_npm_lock_dependencies(deps: Dict[str, dict]) -> Iterator[Tuple[str, str]]:
    for name, info in deps.items():
        version = ""
        if isinstance(info, dict):
            version = str(info.get("version", ""))
            nested = info.get("dependencies")
            if isinstance(nested, dict):
                yield from walk_npm_lock_dependencies(nested)
        yield name, version


def parse_package_lock(path: Path) -> Iterator[Tuple[str, str]]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    deps = data.get("dependencies", {})
    if isinstance(deps, dict):
        yield from walk_npm_lock_dependencies(deps)


def parse_yarn_lock(path: Path) -> Iterator[Tuple[str, str]]:
    content = path.read_text(encoding="utf-8")
    for block in content.split("\n\n"):
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        header_line = lines[0]
        if not header_line.endswith(":"):
            continue
        specs = [spec.strip().strip('"') for spec in header_line[:-1].split(",")]
        version = ""
        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith("version "):
                version = stripped.split(" ", 1)[1].strip().strip('"')
                break
        for spec in specs:
            if not spec:
                continue
            at_index = spec.rfind("@")
            if at_index <= 0:
                name = spec
            else:
                name = spec[:at_index]
            yield name, version


def parse_requirements(requirement_file: Path, ecosystem: Ecosystem) -> List[Tuple[str, str]]:
    try:
        if ecosystem == "python":
            return list(parse_python_requirements(requirement_file.read_text(encoding="utf-8").splitlines()))
        if ecosystem == "nodejs":
            lower_name = requirement_file.name.lower()
            if lower_name == "package.json":
                return list(parse_package_json(requirement_file))
            if lower_name == "package-lock.json":
                return list(parse_package_lock(requirement_file))
            if lower_name == "yarn.lock":
                return list(parse_yarn_lock(requirement_file))
        # Fallback: simple line-per-package parsing
        return [
            (line.strip(), "")
            for line in requirement_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to parse {requirement_file}: {exc}") from exc


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a dependency file into a CSV table of packages.",
    )
    parser.add_argument("requirement_file", help="Path to the requirement/lock file to parse.")
    parser.add_argument(
        "--repo",
        help="Repository name to use in the CSV. If omitted we attempt to infer it.",
    )
    parser.add_argument(
        "--output",
        default="requirement_packages.csv",
        help="Output CSV path (default: requirement_packages.csv).",
    )
    parser.add_argument(
        "--ecosystem",
        help="Override ecosystem detection (e.g. python, nodejs).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    requirement_file = Path(args.requirement_file).expanduser().resolve()
    if not requirement_file.exists():
        raise SystemExit(f"Requirement file not found: {requirement_file}")

    repo_name, repo_root = infer_repo_context(requirement_file, args.repo)
    ecosystem = args.ecosystem or infer_ecosystem(requirement_file)
    filename = relative_filename(requirement_file, repo_root)
    rows = parse_requirements(requirement_file, ecosystem)

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["ecosystem", "repo", "filename", "package", "version"])
        for package, version in rows:
            writer.writerow([ecosystem, repo_name, filename, package, version])

    print(f"Wrote {len(rows)} rows to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

