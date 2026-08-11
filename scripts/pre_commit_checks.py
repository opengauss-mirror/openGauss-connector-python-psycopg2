#!/usr/bin/env python3
"""Run baseline-aware checks only on lines changed from ``HEAD``.

The repository contains legacy files which don't pass a full modern lint run.
Pre-commit passes the changed filenames to this script; diagnostics outside the
current diff are suppressed so unrelated debt does not block a commit.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


HUNK_RE = re.compile(
    r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@"
)
FLAKE8_SEPARATOR = "::pre-commit::"


def run(command):
    """Run *command* from the repository root and capture text output."""
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def normalize_path(filename):
    """Return a stable repository-relative path using forward slashes."""
    path = os.path.normpath(filename)
    if os.path.isabs(path):
        path = os.path.relpath(path, os.getcwd())
    return Path(path).as_posix()


def path_exists_in_head(filename):
    """Return whether *filename* exists in the current ``HEAD`` tree."""
    result = run(["git", "cat-file", "-e", "HEAD:" + filename])
    return result.returncode == 0


def line_count(filename):
    """Count physical lines without assuming a text encoding."""
    data = Path(filename).read_bytes()
    if not data:
        return 0
    return len(data.splitlines())


def changed_lines(filename):
    """Return new-side line numbers changed between ``HEAD`` and the worktree."""
    result = run(
        [
            "git",
            "diff",
            "--unified=0",
            "--no-color",
            "HEAD",
            "--",
            filename,
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff failed")

    lines = set()
    for diff_line in result.stdout.splitlines():
        match = HUNK_RE.match(diff_line)
        if not match:
            continue
        start = int(match.group("start"))
        count = int(match.group("count") or "1")
        lines.update(range(start, start + count))

    if not lines and Path(filename).is_file() and not path_exists_in_head(filename):
        lines.update(range(1, line_count(filename) + 1))
    return lines


def collect_changed_lines(filenames):
    """Build a path-to-line-number map and discard deleted files."""
    changed = {}
    for raw_filename in filenames:
        filename = normalize_path(raw_filename)
        if not Path(filename).is_file():
            continue
        changed[filename] = changed_lines(filename)
    return changed


def executable(name):
    """Locate an installed tool beside the Python running this script."""
    path = Path(sys.executable).with_name(name)
    if not path.is_file():
        raise RuntimeError(
            "{} is not installed in {}. Run bash setup-pre-commit.sh".format(
                name, path.parent
            )
        )
    return str(path)


def print_tool_failure(result):
    """Print captured output for a tool/configuration failure."""
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)


def run_flake8(changed):
    """Report Flake8 findings whose source line is in the current diff."""
    filenames = [name for name, lines in changed.items() if lines]
    if not filenames:
        return 0

    output_format = FLAKE8_SEPARATOR.join(
        ["%(path)s", "%(row)d", "%(col)d", "%(code)s", "%(text)s"]
    )
    result = run(
        [executable("flake8"), "--format", output_format] + filenames
    )
    if result.returncode not in (0, 1):
        print_tool_failure(result)
        return result.returncode

    findings = []
    unparsed = []
    for output_line in result.stdout.splitlines():
        parts = output_line.split(FLAKE8_SEPARATOR, 4)
        if len(parts) != 5:
            if output_line.strip():
                unparsed.append(output_line)
            continue
        filename, row, column, code, message = parts
        filename = normalize_path(filename)
        if int(row) in changed.get(filename, set()):
            findings.append(
                "{}:{}:{}: {} {}".format(
                    filename, row, column, code, message
                )
            )

    if unparsed:
        print("\n".join(unparsed))
        return 1
    if findings:
        print("\n".join(findings))
        return 1
    return 0


def run_codespell(changed):
    """Report spelling findings whose source line is in the current diff."""
    filenames = [name for name, lines in changed.items() if lines]
    if not filenames:
        return 0

    result = run([executable("codespell")] + filenames)
    if result.returncode not in (0, 65):
        print_tool_failure(result)
        return result.returncode

    findings = []
    unparsed = []
    finding_re = re.compile(r"^(?P<path>.*):(?P<line>\d+): (?P<message>.*)$")
    for output_line in result.stdout.splitlines():
        if output_line == "Used config files:" or re.match(
            r"^\s+\d+: ", output_line
        ):
            continue
        match = finding_re.match(output_line)
        if not match:
            if output_line.strip():
                unparsed.append(output_line)
            continue
        filename = normalize_path(match.group("path"))
        row = int(match.group("line"))
        if row in changed.get(filename, set()):
            findings.append(output_line)

    if unparsed:
        print("\n".join(unparsed))
        return 1
    if findings:
        print("\n".join(findings))
        return 1
    return 0


def run_bandit(changed):
    """Report medium-or-higher, high-confidence Bandit findings in the diff."""
    filenames = [name for name, lines in changed.items() if lines]
    if not filenames:
        return 0

    result = run(
        [
            executable("bandit"),
            "-q",
            "-ll",
            "-iii",
            "-f",
            "json",
        ]
        + filenames
    )
    if result.returncode not in (0, 1):
        print_tool_failure(result)
        return result.returncode

    try:
        report = json.loads(result.stdout or "{}")
    except ValueError:
        print_tool_failure(result)
        return 1

    if report.get("errors"):
        for error in report["errors"]:
            print(error, file=sys.stderr)
        return 1

    findings = []
    for issue in report.get("results", []):
        filename = normalize_path(issue["filename"])
        issue_lines = set(issue.get("line_range") or [issue["line_number"]])
        if not issue_lines.intersection(changed.get(filename, set())):
            continue
        findings.append(
            "{}:{}: {} {}/{} {}".format(
                filename,
                issue["line_number"],
                issue["test_id"],
                issue["issue_severity"],
                issue["issue_confidence"],
                issue["issue_text"],
            )
        )

    if findings:
        print("\n".join(findings))
        return 1
    return 0


def split_line_ending(line):
    """Split a byte line into content and its original line ending."""
    if line.endswith(b"\r\n"):
        return line[:-2], b"\r\n"
    if line.endswith(b"\n") or line.endswith(b"\r"):
        return line[:-1], line[-1:]
    return line, b""


def trim_trailing_whitespace(filename, line_numbers):
    """Trim trailing whitespace on selected lines and preserve Markdown breaks."""
    path = Path(filename)
    data = path.read_bytes()
    if b"\0" in data:
        return False

    markdown = path.suffix.lower() == ".md"
    source_lines = data.splitlines(keepends=True)
    output_lines = []
    modified = False

    for number, line in enumerate(source_lines, 1):
        if number not in line_numbers:
            output_lines.append(line)
            continue

        content, ending = split_line_ending(line)
        stripped = content.rstrip(b" \t")
        trailing = content[len(stripped):]
        if (
            markdown
            and stripped
            and trailing.endswith(b"  ")
            and b"\t" not in trailing
        ):
            replacement = stripped + b"  " + ending
        else:
            replacement = stripped + ending
        output_lines.append(replacement)
        modified = modified or replacement != line

    if modified:
        path.write_bytes(b"".join(output_lines))
    return modified


def run_whitespace(changed):
    """Auto-fix trailing whitespace only on changed text lines."""
    modified = []
    for filename, line_numbers in changed.items():
        if line_numbers and trim_trailing_whitespace(filename, line_numbers):
            modified.append(filename)

    if modified:
        print("Trimmed trailing whitespace on changed lines:")
        for filename in modified:
            print("  {}".format(filename))
        return 1
    return 0


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "check", choices=("bandit", "codespell", "flake8", "whitespace")
    )
    parser.add_argument("filenames", nargs="*")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        changed = collect_changed_lines(args.filenames)
        checks = {
            "bandit": run_bandit,
            "codespell": run_codespell,
            "flake8": run_flake8,
            "whitespace": run_whitespace,
        }
        check = checks.get(args.check)
        if check is None:
            print(
                "pre-commit check failed: unsupported check {}".format(
                    args.check
                ),
                file=sys.stderr,
            )
            return 2
        return check(changed)
    except (OSError, RuntimeError) as error:
        print("pre-commit check failed: {}".format(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
