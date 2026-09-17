"""Export reviewed engine edits as a pending delta, never activate an engine.

Run with the isolated source, the installed GP-3 source and consolidated
candidate patch. Only paths declared by that patch are considered.
"""
from pathlib import Path
import argparse
import difflib
import hashlib
import json
import re


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(set(re.findall(r"^diff --git a/(.*?) b/", args.candidate.read_text(encoding="utf-8"), re.M)))
    blocks = []
    changed = []
    for rel in paths:
        if Path(rel).is_absolute() or ".." in Path(rel).parts:
            raise ValueError(rel)
        old = args.base / rel
        new = args.source / rel
        before = old.read_text(encoding="utf-8").splitlines(keepends=True) if old.exists() else []
        after = new.read_text(encoding="utf-8").splitlines(keepends=True)
        if after and not after[-1].endswith("\n"):
            raise ValueError("Missing EOF newline: " + rel)
        if rel.endswith(".json"):
            json.loads("".join(after))
        if before == after:
            continue
        changed.append(rel)
        # Historical baseline may itself lack a newline. Preserve that fact in
        # a valid unified diff rather than concatenate the next file header.
        diff = list(difflib.unified_diff(before, after, fromfile="a/" + rel if before else "/dev/null", tofile="b/" + rel))
        lines = [line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in diff]
        blocks.append(f"diff --git a/{rel} b/{rel}\n" + ("" if before else "new file mode 100644\n") + "".join(lines))
    target = Path(__file__).with_name("engine_delta.patch")
    target.write_text("".join(blocks), encoding="utf-8", newline="\n")
    print(json.dumps({"files": len(changed), "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "paths": changed}, indent=2))


if __name__ == "__main__":
    main()
