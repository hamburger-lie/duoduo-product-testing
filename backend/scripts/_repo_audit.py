"""Audit repo branches - classify merged vs active."""
import io
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


REPO_ROOT = Path(__file__).resolve().parents[2]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    return r.stdout.strip().split("\n") if r.stdout.strip() else []


# Remote branches
remote = [
    b.strip()
    for b in run(["git", "branch", "-r", "--format=%(refname:short)"])
    if b.strip() and b.strip() not in ("origin/main", "origin/HEAD", "origin")
]

# Merged to main
merged = {
    b.strip()
    for b in run(["git", "branch", "-r", "--merged", "main", "--format=%(refname:short)"])
    if b.strip()
}

# Local branches
local = [b.strip() for b in run(["git", "branch", "--format=%(refname:short)"]) if b.strip()]

# Local not merged
local_not_merged = [
    b.strip()
    for b in run(["git", "branch", "--no-merged", "main", "--format=%(refname:short)"])
    if b.strip()
]

print("=" * 80)
print("REMOTE BRANCHES - ALREADY MERGED (safe to delete)")
print("=" * 80)
for b in sorted(remote):
    if b in merged:
        print(f"  {b}")

print()
print("=" * 80)
print("REMOTE BRANCHES - NOT MERGED (active)")
print("=" * 80)
for b in sorted(remote):
    if b not in merged:
        print(f"  {b}")

print()
print("=" * 80)
print("LOCAL BRANCHES - NOT MERGED (have unique work)")
print("=" * 80)
for b in sorted(local_not_merged):
    has_remote = f"origin/{b}" in [r for r in remote]
    status = "has remote" if has_remote else "LOCAL ONLY"
    print(f"  {b:<50} [{status}]")

print()
print("=" * 80)
print("LOCAL BRANCHES - MERGED (can delete)")
print("=" * 80)
local_merged = [b for b in local if b not in local_not_merged and b != "main"]
for b in sorted(local_merged):
    print(f"  {b}")
