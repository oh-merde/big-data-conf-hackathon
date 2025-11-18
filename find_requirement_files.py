#!/usr/bin/env python3
"""
Scan a git repository and list files that are likely to contain dependency
requirements, regardless of the ecosystem.

Example:
    python find_requirement_files.py https://github.com/pallets/flask --output json
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, List, Sequence


# Filenames that almost always contain dependency definitions.
EXACT_FILENAMES = {
    # Python
    "requirements.txt",
    "requirements-dev.txt",
    "requirements.in",
    "constraints.txt",
    "environment.yml",
    "environment.yaml",
    "pyproject.toml",
    "poetry.lock",
    "pdm.lock",
    "pdm.toml",
    "pipfile",
    "pipfile.lock",
    "setup.py",
    "setup.cfg",
    # JavaScript / TypeScript
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "pnpm-lock.yml",
    # Java / Kotlin
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "gradle.lockfile",
    # Ruby
    "gemfile",
    "gemfile.lock",
    # PHP
    "composer.json",
    "composer.lock",
    # Rust
    "cargo.toml",
    "cargo.lock",
    # Go
    "go.mod",
    "go.sum",
    # .NET
    "packages.config",
    "nuget.config",
    # Docker / misc
    "docker-compose.yml",
    "docker-compose.yaml",
    "conda.yml",
    "conda.yaml",
}

# Patterns that match files by extension or name structure.
FILENAME_PATTERNS = {
    "*.csproj",
    "*.fsproj",
    "*.vbproj",
    "requirements-*.txt",
    "*.deps.json",
}

SKIP_DIRECTORIES = {".git", ".hg", ".svn", ".idea", ".vscode", "__pycache__", "node_modules"}


def clone_repo(repo_url: str, destination: Path | None = None) -> Path:
    """Clone the repo into a temporary directory and return the path."""
    target = destination or Path(tempfile.mkdtemp(prefix="req-scan-"))
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(target)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Failed to clone repository: {exc.stderr.decode().strip()}") from exc
    return target


def is_requirement_file(filename: str) -> bool:
    """Return True if filename looks like a dependency definition file."""
    lower_name = filename.lower()
    if lower_name in EXACT_FILENAMES:
        return True
    return any(fnmatch.fnmatch(lower_name, pattern) for pattern in FILENAME_PATTERNS)


def find_requirement_files(root: Path) -> List[Path]:
    """Walk the repository and return requirement files relative to root."""
    matches: List[Path] = []
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRECTORIES]
        for file_name in files:
            if is_requirement_file(file_name):
                absolute_path = Path(current_root) / file_name
                matches.append(absolute_path.relative_to(root))
    return sorted(matches)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List dependency files from a git repository.")
    parser.add_argument("repo_url", help="Git repository URL or local path.")
    parser.add_argument(
        "--output",
        choices={"text", "json"},
        default="text",
        help="Output format. Default: text",
    )
    parser.add_argument(
        "--keep-clone",
        action="store_true",
        help="Do not delete the temporary clone (prints its path).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo_path: Path | None = None
    cleanup = True

    if Path(args.repo_url).exists():
        repo_path = Path(args.repo_url).resolve()
        cleanup = False
    else:
        repo_path = clone_repo(args.repo_url)

    try:
        matches = find_requirement_files(repo_path)
        if args.output == "json":
            print(json.dumps([str(path) for path in matches], indent=2))
        else:
            if matches:
                for match in matches:
                    print(match)
            else:
                print("No requirement files found.")

        if args.keep_clone and cleanup:
            cleanup = False
            print(f"Repository clone retained at: {repo_path}", file=sys.stderr)
        return 0
    finally:
        if cleanup and repo_path:
            shutil.rmtree(repo_path, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

