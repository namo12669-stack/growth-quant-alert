"""Restore only this workflow's default-branch state artifact. No write token needed."""
from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path, PurePosixPath

import requests


def extract_state(data: bytes, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(f.file_size for f in archive.infolist()) > 100_000_000:
            raise ValueError("State archive exceeds the 100 MB safety limit; archive old journal data")
        for item in archive.infolist():
            p = PurePosixPath(item.filename)
            if p.is_absolute() or ".." in p.parts or "\\" in item.filename:
                raise ValueError("Unsafe path in state artifact")
            if item.is_dir():
                continue
            allowed = item.filename in {"state.json", "journal.jsonl"} or (
                len(p.parts) == 2 and p.parts[0] == "fundamentals" and p.suffix == ".json")
            if not allowed:
                raise ValueError("Unexpected file in state artifact")
            target = destination.joinpath(*p.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(item))


def main() -> int:
    token, repo = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPOSITORY")
    branch = os.getenv("DEFAULT_BRANCH", "main")
    if not token or not repo:
        print("Not running in GitHub; existing local state is used.")
        return 0
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    base = f"https://api.github.com/repos/{repo}"
    response = session.get(base + "/actions/artifacts", params={"name": "growth-alert-state", "per_page": 100}, timeout=30)
    response.raise_for_status()
    artifacts = response.json().get("artifacts", [])
    for artifact in sorted(artifacts, key=lambda a: a["created_at"], reverse=True):
        run = artifact.get("workflow_run", {})
        if artifact.get("expired") or run.get("head_branch") != branch:
            continue
        check = session.get(base + f"/actions/runs/{run['id']}", timeout=30)
        check.raise_for_status()
        details = check.json()
        if details.get("path") != ".github/workflows/alerts.yml" or details.get("event") not in ("schedule", "workflow_dispatch"):
            continue
        archive = session.get(base + f"/actions/artifacts/{artifact['id']}/zip", timeout=60)
        archive.raise_for_status()
        extract_state(archive.content, Path("state"))
        print("Restored state from the most recent eligible artifact.")
        return 0
    print("No previous state artifact found. This run will start fresh.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Fail closed: do not restart empty and silently duplicate alerts on API failure.
        print(f"State restore failed ({type(exc).__name__}); no scan started.", file=sys.stderr)
        raise SystemExit(1)
