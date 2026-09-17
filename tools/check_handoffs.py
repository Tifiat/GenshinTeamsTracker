"""Read-only, stdlib-only structural checks for the handoff closeout protocol."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT_BUDGETS = {
    "AGENTS.md": 2000,
    "CODEX.md": 32000,
    "TODO.md": 18000,
    "docs/handoff/README.md": 16000,
    "docs/handoff/HANDOFF_MAINTENANCE.md": 16000,
}
CURRENT_START = re.compile(r"<!-- handoff-current: ([a-z0-9-]+) -->")
CURRENT_BLOCK = re.compile(
    r"<!-- handoff-current: ([a-z0-9-]+) -->\s*(.*?)\s*<!-- /handoff-current -->",
    re.S,
)
LINK = re.compile(r'(?<!!)\[[^\]\n]*\]\((<[^>\n]+>|[^\s)]+)(?:\s+"[^"]*")?\)')
DOC_LITERAL = re.compile(r"(?<!\x60)\x60([A-Za-z0-9_./-]+\.md)\x60(?!\x60)")
CURRENT_FIELDS = {
    "active_engine_id": "Active engine",
    "rollback_engine_id": "Rollback engine",
    "active_patch": "Active patch",
    "patch_sha256": "Patch SHA256",
    "acceptance_status": "Acceptance status",
}
OPTIMIZER_CONTRACT = "gcsim_optimizer_trace_equation_cleanup_manifest_v1"


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    detail: str


def prose(text: str) -> str:
    """Exclude fenced examples without changing the remaining line boundaries."""
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r"^\s*(\x60{3,}|~{3,})", line)
        if match:
            marker = match[1]
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
            lines.append("")
        else:
            lines.append(line if fence is None else "")
    return "\n".join(lines)


def resolve_local(root: Path, owner: Path, target: str) -> Path | None:
    parts = urlsplit(target.strip("<>"))
    if parts.scheme or parts.netloc:
        return None
    candidate = (owner.parent / unquote(parts.path)).resolve() if parts.path else owner
    if not candidate.is_relative_to(root):
        raise ValueError("local link escapes repository")
    return candidate


def check_repository(root: Path) -> list[Issue]:
    root = root.resolve()
    handoff = root / "docs/handoff"
    issues: list[Issue] = []
    documents: dict[Path, str] = {}

    def issue(code: str, path: Path, detail: str) -> None:
        issues.append(Issue(code, path.relative_to(root).as_posix(), detail))

    paths = set(handoff.glob("*.md")) | {root / name for name in ROOT_BUDGETS}
    for path in sorted(paths):
        if not path.is_file():
            issue("missing-entrypoint", path, "required document is missing")
            continue
        try:
            raw = path.read_bytes()
            documents[path] = raw.decode("utf-8-sig")
        except (OSError, UnicodeError) as exc:
            issue("unreadable", path, str(exc))
            continue
        budget = ROOT_BUDGETS.get(path.relative_to(root).as_posix())
        if budget and len(raw.replace(b"\r\n", b"\n")) > budget:
            issue("root-budget", path, f"compact to at most {budget} UTF-8 bytes")

    agents = root / "AGENTS.md"
    for required in ("CODEX.md", "docs/handoff/HANDOFF_MAINTENANCE.md"):
        if required not in prose(documents.get(agents, "")):
            issue("missing-routing", agents, f"must route agents to {required}")

    index = handoff / "README.md"
    indexed: list[Path] = []
    scopes: dict[str, Path] = {}
    owner_blocks: dict[Path, list[tuple[str, str]]] = {}
    for path, raw in documents.items():
        text = prose(raw)
        blocks = CURRENT_BLOCK.findall(text)
        owner_blocks[path] = blocks
        if (
            len(blocks) != text.count("<!-- handoff-current:")
            or len(blocks) != text.count("<!-- /handoff-current -->")
            or len(blocks) != len(CURRENT_START.findall(text))
        ):
            issue("current-markers", path, "current blocks must have balanced, valid markers")
        for scope, body in blocks:
            if scope in scopes:
                issue("duplicate-current", path, f"{scope} already owned by {scopes[scope].name}")
            scopes[scope] = path
            if len(body.split()) > 400:
                issue("current-budget", path, f"{scope}: compact current state to 400 words")
        if path == root / "TODO.md" and re.search(r"^\s*[-*]\s+\[[xX]\]", text, re.M):
            issue("completed-todo", path, "remove completed tasks; retain durable outcomes in their owner")
        for match in LINK.finditer(text):
            try:
                target = resolve_local(root, path, match[1])
            except ValueError as exc:
                issue("invalid-link", path, f"{match[1]}: {exc}")
                continue
            if target is not None:
                if not target.exists():
                    issue("broken-link", path, match[1])
                if path == index:
                    indexed.append(target)
        # Existing handoffs also use inline-code document names as pointers.
        for name in DOC_LITERAL.findall(text):
            candidates = [path.parent / name, root / name]
            if "/" not in name:
                candidates.append(handoff / name)
            candidates = [p.resolve() for p in candidates]
            if not any(p.is_relative_to(root) and p.is_file() for p in candidates):
                issue("broken-doc-reference", path, name)

    for path in sorted(documents):
        if path.parent == handoff and path != index:
            count = indexed.count(path)
            if count != 1:
                issue("index-coverage", index, f"{path.name}: expected one link, found {count}")

    # Only live projections are reconciled. Historical migration records keep
    # their original ids, hashes and statuses.
    for path in sorted(handoff.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, ValueError) as exc:
            issue("invalid-json", path, str(exc))
            continue
        if not isinstance(data, dict):
            continue
        optimizer_manifest = data.get("contract") == OPTIMIZER_CONTRACT
        if optimizer_manifest:
            required = {
                "current_state": ("handoff", *CURRENT_FIELDS),
                "current_next_block": ("name", "resume"),
            }
            for section, keys in required.items():
                values = data.get(section)
                if not isinstance(values, dict) or any(not values.get(key) for key in keys):
                    issue("missing-current-fields", path, f"{section}: required live fields are missing")
        for section in ("current_state", "current_next_block"):
            live = data.get(section, {})
            if not isinstance(live, dict):
                issue("invalid-current", path, f"{section} must be an object")
                continue
            for key, value in live.items():
                if key not in ("handoff", "resume", "design_path") and not key.endswith("_handoff"):
                    continue
                if not isinstance(value, str) or (root / value).resolve() not in documents:
                    issue("current-pointer", path, f"{section}.{key} must name an existing handoff")
        state = data.get("current_state", {})
        if not isinstance(state, dict) or not isinstance(state.get("handoff"), str):
            continue
        owner = (root / state["handoff"]).resolve()
        blocks = owner_blocks.get(owner, [])
        if len(blocks) != 1:
            issue("current-owner", path, "current_state.handoff must own exactly one current block")
            continue
        body = blocks[0][1]
        for key, label in CURRENT_FIELDS.items():
            if key not in state:
                continue
            values = re.findall(rf"^- {re.escape(label)}:\s*\x60([^\x60]+)\x60\s*$", body, re.M)
            if values != [state[key]]:
                issue("current-projection", path, f"{key} differs from {owner.name} ({label})")
        if optimizer_manifest:
            if data.get("status") != state.get("acceptance_status"):
                issue("current-projection", path, "top-level status differs from current acceptance_status")
            next_block = data.get("current_next_block")
            if isinstance(next_block, dict):
                values = re.findall(r"^- Next block:\s*\x60([^\x60]+)\x60\s*$", body, re.M)
                if values != [next_block.get("name")]:
                    issue("current-projection", path, "next block differs from current owner")
                if next_block.get("resume") != state["handoff"]:
                    issue("current-projection", path, "resume must point to the declared current owner")
    return sorted(set(issues), key=lambda item: (item.path, item.code, item.detail))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    issues = check_repository(args.root)
    if issues:
        for item in issues:
            print(f"{item.code}: {item.path}: {item.detail}")
        print(f"FAIL: {len(issues)} handoff issue(s).")
        return 1
    print("PASS: handoff structure, budgets and declared current projections.")
    print("Still required: semantic closeout of affected facts and evidence scopes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
