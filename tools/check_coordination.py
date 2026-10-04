"""Read-only structural checks for the shared worker coordination hub."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


LINK_SCHEMA = "gtt_coordination_link_v1"
REGISTRY_SCHEMA = "gtt_shared_coordination_v1"
STATES = {"awaiting_owner_update", "branch_work", "ready_for_review", "accepted_on_master"}
REQUIRED = ("README.md", "TODO.md", "BACKLOG.md", "registry.json")
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\((<[^>]+>|[^)\s]+)(?:\s+[^)]*)?\)")
TASK_BOX = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\[[ xX]\]", re.MULTILINE)


@dataclass(frozen=True)
class Issue:
    code: str
    path: Path
    detail: str


def _same(a: Path, b: Path) -> bool:
    return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))


def _within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except (ValueError, OSError, RuntimeError):
        return False


def _text(path: Path, issues: list[Issue], limit: int | None = None) -> str | None:
    try:
        with path.open("rb") as handle:
            data = handle.read(limit + 1) if limit is not None else handle.read()
    except (OSError, ValueError) as exc:
        issues.append(Issue("unreadable-file", path, str(exc)))
        return None
    if limit is not None and len(data) > limit:
        issues.append(Issue("oversize-file", path, f"File exceeds {limit} bytes"))
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        issues.append(Issue("invalid-utf8", path, "File must be UTF-8"))
        return None


def _json(path: Path, issues: list[Issue], limit: int) -> object | None:
    content = _text(path, issues, limit)
    if content is None:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        issues.append(Issue("invalid-json", path, f"JSON parse error: {exc.msg}"))
        return None


def _links(path: Path, content: str, scopes: list[Path], issues: list[Issue]) -> None:
    for match in MARKDOWN_LINK.finditer(content):
        target = match.group(1).strip("<>")
        try:
            parsed = urlsplit(target)
        except ValueError:
            issues.append(Issue("invalid-link-target", path, f"Invalid relative target: {target}"))
            continue
        if parsed.scheme or parsed.netloc or target.startswith(("#", "/", "\\")):
            continue
        local = unquote(parsed.path).replace("\\", "/")
        if not local or re.match(r"^[A-Za-z]:/", local):
            continue
        if "\x00" in local:
            issues.append(Issue("invalid-link-target", path, f"Invalid relative target: {target}"))
            continue
        try:
            resolved = (path.parent / local).resolve()
        except (OSError, ValueError, RuntimeError):
            issues.append(Issue("invalid-link-target", path, f"Invalid relative target: {target}"))
            continue
        if not any(_within(resolved, scope) for scope in scopes):
            issues.append(Issue("link-escape", path, f"Relative link leaves hub and registered checkouts: {target}"))
        else:
            try:
                exists = resolved.exists()
            except (OSError, ValueError):
                exists = False
            if not exists:
                issues.append(Issue("broken-link", path, f"Missing relative target: {target}"))


def check_coordination(root: Path, hub: Path | None = None, check_routes: bool = True) -> list[Issue]:
    """Return actionable issues; never modify the checkout or hub."""
    issues: list[Issue] = []
    root_input = Path(root)
    if "\x00" in str(root_input):
        return [Issue("invalid-root", root_input, "Checkout root contains a null byte")]
    try:
        root = root_input.resolve()
    except (OSError, ValueError, RuntimeError) as exc:
        return [Issue("invalid-root", Path(root), f"Cannot resolve checkout root: {exc}")]
    link_path = root / "coordination.json"
    if not link_path.exists() and hub is None:
        return issues  # Fixtures and checkouts that have not migrated yet.

    linked_hub: Path | None = None
    if link_path.exists():
        link = _json(link_path, issues, 4_000)
        if not isinstance(link, dict) or link.get("schema") != LINK_SCHEMA:
            issues.append(Issue("invalid-link", link_path, f"Expected schema {LINK_SCHEMA}"))
        else:
            value = link.get("hub")
            if not isinstance(value, str) or not value.strip() or "\x00" in value:
                issues.append(Issue("invalid-link", link_path, "hub must be a nonempty path string"))
            elif Path(value).is_absolute() or re.match(r"^[A-Za-z]:", value):
                issues.append(Issue("invalid-link", link_path, "hub must be relative to the checkout"))
            else:
                try:
                    linked_hub = (root / value).resolve()
                except (OSError, ValueError, RuntimeError) as exc:
                    issues.append(Issue("invalid-link", link_path, f"Cannot resolve hub path: {exc}"))
                else:
                    if _within(linked_hub, root):
                        issues.append(Issue("invalid-link", link_path, "hub must be outside the checkout"))
    if hub is not None and "\x00" in str(hub):
        issues.append(Issue("invalid-hub", Path(hub), "Explicit hub contains a null byte"))
        return issues
    try:
        selected_hub = Path(hub).resolve() if hub is not None else linked_hub
    except (OSError, ValueError, RuntimeError) as exc:
        issues.append(Issue("invalid-hub", Path(hub), f"Cannot resolve explicit hub: {exc}"))
        return issues
    if selected_hub is None:
        return issues
    if linked_hub is not None and hub is not None and not _same(selected_hub, linked_hub):
        issues.append(Issue("hub-mismatch", link_path, f"Explicit hub differs from coordination.json: {linked_hub}"))
    if not selected_hub.is_dir():
        issues.append(Issue("missing-hub", selected_hub, "Shared coordination hub directory is missing"))
        return issues
    workers_dir = selected_hub / "workers"
    workers_safe = _within(workers_dir, selected_hub)
    if not workers_safe:
        issues.append(Issue("workers-escape", workers_dir, "workers directory resolves outside hub"))
    elif not workers_dir.is_dir():
        issues.append(Issue("missing-workers", workers_dir, "workers directory is missing"))

    contents: dict[Path, str] = {}
    for name in REQUIRED:
        file = selected_hub / name
        if not file.is_file():
            issues.append(Issue("missing-file", file, "Required hub file is missing"))
        elif name != "registry.json":
            content = _text(file, issues, 20_000)
            if content is not None:
                contents[file] = content
    for name in ("DECISIONS.md", "GIT_POLICY.md", "GIT_JOURNAL.md", "archive/MIGRATION.md"):
        file = selected_hub / name
        if file.is_file():
            content = _text(file, issues, 20_000)
            if content is not None:
                contents[file] = content

    registry_path = selected_hub / "registry.json"
    registry = _json(registry_path, issues, 40_000) if registry_path.is_file() else None
    if not isinstance(registry, dict) or registry.get("schema") != REGISTRY_SCHEMA:
        issues.append(Issue("invalid-registry", registry_path, f"Expected schema {REGISTRY_SCHEMA}"))
        return issues
    workers = registry.get("workers")
    if not isinstance(workers, list) or not workers:
        issues.append(Issue("invalid-registry", registry_path, "workers must be a nonempty list"))
        return issues

    ids: set[str] = set()
    checkouts: set[str] = set()
    checkout_paths: list[Path] = []
    statuses: set[str] = set()
    root_count = 0
    for index, worker in enumerate(workers):
        if not isinstance(worker, dict):
            issues.append(Issue("invalid-worker", registry_path, f"workers[{index}] must be an object"))
            continue
        ident = worker.get("id")
        if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", ident):
            issues.append(Issue("invalid-worker", registry_path, f"workers[{index}].id is invalid"))
            continue
        if ident in ids:
            issues.append(Issue("duplicate-worker", registry_path, f"Duplicate worker id: {ident}"))
        ids.add(ident)
        for key in ("branch", "thread_id", "title"):
            if not isinstance(worker.get(key), str) or not worker[key].strip():
                issues.append(Issue("invalid-worker", registry_path, f"{ident}.{key} must be nonempty"))

        checkout_value = worker.get("checkout")
        checkout: Path | None = None
        if (not isinstance(checkout_value, str) or not checkout_value.strip()
                or "\x00" in checkout_value or not Path(checkout_value).is_absolute()):
            issues.append(Issue("invalid-checkout", registry_path, f"{ident}.checkout must be an absolute path"))
        else:
            try:
                checkout = Path(checkout_value).resolve()
            except (OSError, ValueError, RuntimeError) as exc:
                issues.append(Issue("invalid-checkout", registry_path, f"{ident}.checkout cannot resolve: {exc}"))
        if checkout is not None:
            normalized = os.path.normcase(str(checkout))
            if normalized in checkouts:
                issues.append(Issue("duplicate-checkout", registry_path, f"Checkout owned more than once: {checkout}"))
            checkouts.add(normalized)
            checkout_paths.append(checkout)
            if _same(root, checkout):
                root_count += 1
            if _within(selected_hub, checkout):
                issues.append(Issue("hub-inside-checkout", registry_path, f"Hub is inside {ident} checkout"))
            if not checkout.is_dir():
                issues.append(Issue("missing-checkout", registry_path, f"{ident}.checkout directory is missing: {checkout}"))

        status_value = worker.get("status")
        if (not isinstance(status_value, str) or not status_value.strip()
                or "\x00" in status_value or Path(status_value).is_absolute()):
            issues.append(Issue("invalid-status-path", registry_path, f"{ident}.status must be relative to hub/workers"))
            continue
        status_path = selected_hub / status_value
        if not workers_safe or not _within(status_path, workers_dir):
            issues.append(Issue("status-escape", registry_path, f"{ident}.status leaves hub/workers"))
            continue
        normalized_status = os.path.normcase(str(status_path.resolve()))
        if normalized_status in statuses:
            issues.append(Issue("duplicate-status", registry_path, f"Status file owned more than once: {status_value}"))
        statuses.add(normalized_status)
        content = _text(status_path, issues, 8_000)
        if content is None:
            continue
        contents[status_path] = content
        if f"<!-- coordination-worker: {ident} -->" not in content:
            issues.append(Issue("status-marker", status_path, f"Missing marker for {ident}"))
        branch = worker.get("branch")
        branch_match = re.search(r"(?m)^- Branch: `([^`]+)`\s*$", content)
        if not branch_match or branch_match.group(1) != branch:
            issues.append(Issue("status-branch", status_path, f"Branch must match registry: {branch}"))
        state_match = re.search(r"(?m)^- Integration: `([^`]+)`\s*$", content)
        state = state_match.group(1) if state_match else None
        if state not in STATES:
            issues.append(Issue("status-integration", status_path, "Integration must use an allowed state"))
        accepted = re.search(r"(?m)^- Accepted commit: `([0-9a-fA-F]{40})`\s*$", content)
        evidence = re.search(r"(?m)^- Evidence:\s*(\S.*)$", content)
        if state == "accepted_on_master" and (not accepted or not evidence):
            issues.append(Issue("false-acceptance", status_path, "Accepted state needs a 40-hex commit and evidence"))
        if state != "accepted_on_master" and (accepted or re.search(r"(?m)^- Accepted commit:", content)):
            issues.append(Issue("false-acceptance", status_path, "Only accepted_on_master may claim an accepted commit"))

    owner = registry.get("queue_owner")
    if not isinstance(owner, str) or owner not in ids:
        issues.append(Issue("invalid-queue-owner", registry_path, "queue_owner must name a registered worker"))
    if root_count != 1:
        issues.append(Issue("unregistered-root", registry_path, f"Checkout root must match exactly one worker; found {root_count}"))

    scopes = [selected_hub, *checkout_paths]
    for file, content in contents.items():
        _links(file, content, scopes, issues)

    if check_routes:
        for name in ("AGENTS.md", "CODEX.md"):
            path = root / name
            content = _text(path, issues)
            if content is not None and "coordination" not in content.casefold():
                issues.append(Issue("missing-route", path, "Must mention shared coordination"))
        for name in ("TODO.md", "docs/handoff/WORK_BACKLOG.md"):
            path = root / name
            content = _text(path, issues)
            if content is None:
                continue
            if "<!-- coordination-router -->" not in content:
                issues.append(Issue("missing-route", path, "Missing coordination router marker"))
            if TASK_BOX.search(content):
                issues.append(Issue("duplicate-queue", path, "Task checkboxes belong in the shared hub"))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--hub", type=Path)
    parser.add_argument("--no-route-check", action="store_true")
    args = parser.parse_args()
    issues = check_coordination(args.root, args.hub, not args.no_route_check)
    for issue in issues:
        print(f"{issue.code}: {issue.path}: {issue.detail}")
    if not issues:
        print("Coordination check passed")
    return bool(issues)


if __name__ == "__main__":
    raise SystemExit(main())
