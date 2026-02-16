from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

from risk_scoring.canonical_change import compute_change_id_from_normalized_diff


NORMALIZED_DIFF_SCHEMA_VERSION = "normalized_diff.v1"


class GitError(RuntimeError):
    pass


class GitRunner(Protocol):
    def run(self, args: Sequence[str], *, cwd: str) -> str:
        ...


class SubprocessGitRunner:
    def run(self, args: Sequence[str], *, cwd: str) -> str:
        try:
            res = subprocess.run(
                list(args),
                cwd=cwd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise GitError(e.stderr.strip() or str(e)) from e
        return res.stdout


@dataclass(frozen=True)
class Hunk:
    header: str
    lines: Tuple[str, ...]


@dataclass(frozen=True)
class FileDiff:
    path: str
    hunks: Tuple[Hunk, ...]


@dataclass(frozen=True)
class NormalizedDiff:
    schema_version: str
    base_ref: str
    repo: Dict[str, Optional[str]]
    files: Tuple[FileDiff, ...]
    change_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "base_ref": self.base_ref,
            "repo": dict(self.repo),
            "files": [
                {
                    "path": f.path,
                    "hunks": [
                        {"header": h.header, "lines": list(h.lines)} for h in f.hunks
                    ],
                }
                for f in self.files
            ],
            "change_id": self.change_id,
        }


_HUNK_RE = re.compile(r"^@@\s.*?@@")


def _normalize_newlines(text: str) -> str:
    # Deterministic newline normalization: CRLF/CR -> LF
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _parse_patch(patch_text: str) -> List[FileDiff]:
    """Parse a `git diff --patch` output into stable per-file hunks.

    Normalization rules:
    - Drop volatile metadata lines: `index ...` and the `---/+++` headers.
    - Preserve hunk lines exactly (after newline normalization), including leading +/-/space.
    - Sort files lexicographically by path.
    - Preserve hunk ordering as it appears in the patch.

    Assumptions:
    - Input comes from `git diff --patch --no-color --no-ext-diff`.
    """

    patch_text = _normalize_newlines(patch_text)
    lines = patch_text.split("\n")

    files: List[FileDiff] = []
    current_path: Optional[str] = None
    current_hunks: List[Hunk] = []
    current_hunk_header: Optional[str] = None
    current_hunk_lines: List[str] = []

    def flush_hunk() -> None:
        nonlocal current_hunk_header, current_hunk_lines, current_hunks
        if current_hunk_header is None:
            return
        current_hunks.append(Hunk(header=current_hunk_header, lines=tuple(current_hunk_lines)))
        current_hunk_header = None
        current_hunk_lines = []

    def flush_file() -> None:
        nonlocal current_path, current_hunks
        flush_hunk()
        if current_path is None:
            return
        files.append(FileDiff(path=current_path, hunks=tuple(current_hunks)))
        current_path = None
        current_hunks = []

    for line in lines:
        if line.startswith("diff --git "):
            flush_file()
            # Format: diff --git a/<path> b/<path>
            parts = line.split()
            if len(parts) >= 4:
                b_path = parts[3]
                if b_path.startswith("b/"):
                    current_path = b_path[2:]
                else:
                    current_path = b_path
            else:
                current_path = ""
            continue

        if current_path is None:
            continue

        if line.startswith("index "):
            continue
        if line.startswith("--- ") or line.startswith("+++ "):
            continue

        if _HUNK_RE.match(line):
            flush_hunk()
            current_hunk_header = line
            current_hunk_lines = []
            continue

        if current_hunk_header is not None:
            # Include even empty lines as part of the hunk.
            current_hunk_lines.append(line)

    flush_file()

    # Deterministic file ordering
    return sorted(files, key=lambda f: f.path)


def capture_normalized_diff(
    *,
    repo_dir: str,
    base_ref: str = "HEAD",
    paths: Optional[Sequence[str]] = None,
    git: Optional[GitRunner] = None,
) -> NormalizedDiff:
    """Capture a deterministic normalized diff against `base_ref`.

    MVP behavior:
    - Workspace-level diff (all changes) unless `paths` are provided.
    - Uses `git diff --patch` so we can parse hunks.

    Determinism contract:
    - Stable ordering: files are sorted by path.
    - Newlines are normalized.
    - change_id = sha256 of the normalized diff JSON representation.
    """

    runner: GitRunner = git or SubprocessGitRunner()

    repo_uri = None
    try:
        repo_uri = runner.run(["git", "config", "--get", "remote.origin.url"], cwd=repo_dir).strip() or None
    except GitError:
        # Not fatal; remain explicit.
        repo_uri = None

    revision = None
    try:
        revision = runner.run(["git", "rev-parse", base_ref], cwd=repo_dir).strip() or None
    except GitError:
        revision = None

    cmd: List[str] = [
        "git",
        "diff",
        "--patch",
        "--no-color",
        "--no-ext-diff",
        "--unified=3",
        base_ref,
    ]

    if paths:
        cmd.append("--")
        cmd.extend(list(paths))

    patch = runner.run(cmd, cwd=repo_dir)
    file_diffs = _parse_patch(patch)

    normalized_obj: Dict[str, Any] = {
        "schema_version": NORMALIZED_DIFF_SCHEMA_VERSION,
        "base_ref": base_ref,
        "repo": {"uri": repo_uri, "revision": revision},
        "files": [
            {
                "path": f.path,
                "hunks": [
                    {"header": h.header, "lines": list(h.lines)} for h in f.hunks
                ],
            }
            for f in file_diffs
        ],
    }

    change_id = compute_change_id_from_normalized_diff(normalized_obj)

    return NormalizedDiff(
        schema_version=NORMALIZED_DIFF_SCHEMA_VERSION,
        base_ref=base_ref,
        repo={"uri": repo_uri, "revision": revision},
        files=tuple(file_diffs),
        change_id=change_id,
    )
