#!/usr/bin/env python3
"""Build an app-only Git snapshot; keep the sample answer key out of inference."""
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess

PREFIX = "examples/invoice-desk/app/"

def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])

def extract(repo, revision, target):
    for entry in git(repo, "ls-tree", "-rz", revision, "--", PREFIX).split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        name = raw_path.decode()
        relative = PurePosixPath(name)
        if mode not in ("100644", "100755") or kind != "blob":
            raise ValueError(f"Only regular app files are supported: {name}")
        if relative.is_absolute() or ".." in relative.parts or not name.startswith(PREFIX):
            raise ValueError(f"Unsafe source path: {name}")
        output = target.joinpath(*relative.parts)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(git(repo, "cat-file", "blob", oid))
        output.chmod(0o755 if mode == "100755" else 0o644)

def commit(target, message):
    git(target, "add", "--all")
    git(target, "-c", "user.name=Invoice Desk demo", "-c",
        "user.email=demo@example.test", "commit", "--allow-empty", "-qm", message)
    return git(target, "rev-parse", "HEAD").decode().strip()

def main():
    source = Path(os.environ["SOURCE_REPO"]).resolve()
    target = Path(os.environ["RUNNER_TEMP"]) / "invoice-desk"
    reports = Path(os.environ["RUNNER_TEMP"]) / "invoice-desk-reports"
    target.mkdir()
    reports.mkdir()
    head = git(source, "rev-parse", "HEAD").decode().strip()
    base = os.environ.get("PR_BASE_SHA", "")
    git(target, "init", "-q")
    diff_base = ""
    if base:
        base = git(source, "merge-base", base, head).decode().strip()
        extract(source, base, target)
        diff_base = commit(target, "Invoice Desk base snapshot")
        shutil.rmtree(target / "examples", ignore_errors=True)
    extract(source, head, target)
    commit(target, "Invoice Desk head snapshot")
    changed = not diff_base or bool(git(target, "diff", "--name-only", diff_base, "HEAD"))
    (reports / "source.json").write_text(json.dumps({
        "source_head": head, "source_merge_base": base or None,
        "snapshot_diff_base": diff_base or None,
        "scope": PREFIX, "changed": changed,
    }, indent=2) + "\n")
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"changed={str(changed).lower()}\ndiff_base={diff_base}\n")

if __name__ == "__main__":
    main()
