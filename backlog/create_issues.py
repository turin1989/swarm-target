#!/usr/bin/env python3
"""Create one GitHub issue per task in backlog/tasks.yaml.

Usage:  python backlog/create_issues.py [--repo owner/name] [--dry-run]

Idempotent: tasks whose id already appears in an open/closed issue title are skipped.
Labels 'swarm-task' and the task's kind are created if missing.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
LABEL_COLOURS = {
    "swarm-task": "0e8a16",
    "independent": "c5def5",
    "shared-module": "fbca04",
    "interface-change": "d93f0b",
}


def gh(*args: str, check: bool = True) -> str:
    res = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and res.returncode != 0:
        sys.exit(f"gh {' '.join(args)} failed:\n{res.stderr}")
    return res.stdout.strip()


def ensure_labels(repo: str) -> None:
    existing = {
        l["name"] for l in json.loads(gh("label", "list", "--repo", repo, "--json", "name", "--limit", "200"))
    }
    for name, colour in LABEL_COLOURS.items():
        if name not in existing:
            gh("label", "create", name, "--repo", repo, "--color", colour)


def existing_task_ids(repo: str) -> set[str]:
    out = gh("issue", "list", "--repo", repo, "--state", "all", "--limit", "500", "--json", "title")
    ids = set()
    for issue in json.loads(out):
        title = issue["title"]
        if title.startswith("[T") and "]" in title:
            ids.add(title[1 : title.index("]")])
    return ids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="turin1989/swarm-target")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    tasks = yaml.safe_load((HERE / "tasks.yaml").read_text())["tasks"]
    if not args.dry_run:
        ensure_labels(args.repo)
    done = set() if args.dry_run else existing_task_ids(args.repo)

    created = 0
    for t in tasks:
        if t["id"] in done:
            print(f"skip {t['id']} (exists)")
            continue
        title = f"[{t['id']}] {t['title']}"
        body = (
            f"**Kind:** `{t['kind']}`\n"
            f"**Likely touches:** {', '.join(f'`{p}`' for p in t['touches'])}\n\n"
            f"### Acceptance criteria\n{t['body'].rstrip()}\n"
        )
        if args.dry_run:
            print(f"would create: {title}")
            continue
        url = gh(
            "issue", "create", "--repo", args.repo, "--title", title, "--body", body,
            "--label", "swarm-task", "--label", t["kind"],
        )
        print(f"{t['id']} -> {url}")
        created += 1
    print(f"created {created} issue(s); {len(tasks)} tasks in backlog")


if __name__ == "__main__":
    main()
