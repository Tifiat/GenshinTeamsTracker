"""Small, checked R5 edits applied to the prospectively pinned Python image."""
from __future__ import annotations

def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('R5 Python source pattern differs: ' + old[:90])
    return text.replace(old, new, 1)


def apply_changes(baseline):
    images = dict(baseline)

    name = 'run_workspace/gcsim/optimizer_artifact_database.py'
    text = images[name].decode().replace('\r\n', '\n')
    load = text.index('def load_gcsim_optimizer_artifact_database_input(')
    validation_start = text.index('    if not isinstance(engine_context,', load)
    validation_end = text.index('    path = Path(database_path)', validation_start)
    validation = text[validation_start:validation_end]
    start = text.index('    raw_input_hash = _raw_database_input_sha256(', load)
    end = text.index('\n\ndef evaluate_gcsim_optimizer_artifact_eligibility(', start)
    finish = text[start:end]
    text = (text[:start] + '''    return _database_input_from_frozen_rows(
        path, engine_context,
        (artifact_columns, substat_columns, artifact_rows, substat_rows, observation_rows),
    )


def _database_input_from_frozen_rows(path, engine_context, frozen_rows):
    """Validate/hash one owned immutable SQLite view; no further database reads."""
''' + validation + '''    artifact_columns, substat_columns, artifact_rows, substat_rows, observation_rows = frozen_rows
''' + finish + text[end:])
    images[name] = text.encode()

    name = 'run_workspace/gcsim/optimizer_go_selected_inputs.py'
    text = images[name].decode().replace('\r\n', '\n')
    text = once(text, 'from __future__ import annotations', '''from __future__ import annotations
from . import optimizer_artifact_database as _artifact_input''')
    start = text.index('def load_selected_equipped_team_snapshot(')
    query_start = text.index('        rows = connection.execute(', start)
    query_end = text.index('        try:\n            current_artifact_input_sha256', query_start)
    query = text[query_start:query_end]
    query_helper = '\n\ndef _selected_equipment_rows(connection, character_keys):\n' + query.replace('        rows =', '    return', 1)
    # Keep the original public API and its cross-transaction recheck intact.
    text = text[:query_start] + '        rows = _selected_equipment_rows(connection, character_keys)\n' + text[query_end:]
    pure_start = text.index('    virtual_key_set = set(normalized_virtual_keys)', start)
    pure_end = text.index('\n\ndef selected_virtual_inventory_baseline_summaries(', pure_start)
    pure_body = text[pure_start:pure_end]
    validation_start = text.index('    if not isinstance(artifact_database,', start)
    validation_end = text.index('    connection: sqlite3.Connection | None = None', validation_start)
    validation = text[validation_start:validation_end]
    text = (text[:pure_start] + '''    return _selected_snapshot_from_rows(
        database_path, artifact_database, character_keys, virtual_character_keys, rows,
    )


def _selected_snapshot_from_rows(database_path, artifact_database, character_keys, virtual_character_keys, rows):
''' + validation + pure_body + query_helper + '''

def _load_selected_inventory_snapshot(database_path, *, engine_context, character_keys, virtual_character_keys=()):
    """One read-only transaction freezes inventory and equipment together.

    The old public equipment loader still rechecks independently supplied
    inventory. This route owns both row sets from the same SQLite read view;
    it never substitutes a caller-supplied digest for a consistency check.
    """
    path = Path(database_path).expanduser().resolve()
    connection = None
    try:
        connection = sqlite3.connect(
            f"file:{quote(path.as_posix(), safe='/:')}?mode=ro", uri=True, timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        try:
            frozen = _artifact_input._fetch_all_rows_from_connection(connection)
        except (OSError, sqlite3.Error, ValueError) as exc:
            return _artifact_input._load_not_ready(
                "artifact_database_read_failed", f"Could not load optimizer artifact rows: {exc}",
            ), None
        rows = _selected_equipment_rows(connection, character_keys)
    except sqlite3.Error as exc:
        raise GcsimOptimizerGoSelectedInputError(f"selected equipment read failed: {exc}") from exc
    finally:
        if connection is not None:
            try:
                if connection.in_transaction:
                    connection.rollback()
            finally:
                connection.close()
    loaded = _artifact_input._database_input_from_frozen_rows(path, engine_context, frozen)
    if not loaded.ready or loaded.database_input is None:
        return loaded, None
    return loaded, _selected_snapshot_from_rows(
        path, loaded.database_input, character_keys, virtual_character_keys, rows,
    )
''' + text[pure_end:])
    images[name] = text.encode()

    name = 'run_workspace/gcsim/optimizer_go_inputs.py'
    text = images[name].decode().replace('\r\n', '\n')
    text = once(text, '    bind_selected_report_config_and_snapshot,',
        '    _load_selected_inventory_snapshot, bind_selected_report_config_and_snapshot,')
    text = once(text, '    build_selected_team_full_config_report, VIRTUAL_ARTIFACT_POLICY_OWNED_BUILD,',
        '    build_selected_team_payload, build_selected_team_full_config_report, VIRTUAL_ARTIFACT_POLICY_OWNED_BUILD,')
    start = text.index('    report = build_selected_team_full_config_report(')
    end = text.index('    prepared_characters = tuple(', start)
    report_call = text[start:end].split('    if theory_mode:')[0]
    # Keep common slot/mapping preparation; only skip the first config assembly.
    replacement = ('    if theory_mode:\n' + ''.join('    ' + line + '\n' for line in report_call.rstrip().splitlines())
        + '''        _require_prepared_report(report, theory_mode=True)
        initial_team = report.team
    else:
        initial_team = build_selected_team_payload(
            db_path=request.db_path, selected_team=request.selected_team,
            team_index=max(0, int(request.team_index)),
            artifact_set_registry_source=artifact_registry_source,
            virtual_artifact_policy=virtual_artifact_policy,
        )
''')
    text = text[:start] + replacement + text[end:]
    second = text.index('        report = build_selected_team_full_config_report(', start + len(replacement))
    text = text[:second].replace('report.team', 'initial_team') + text[second:]
    # The Theory assignment must still refer to the newly assembled report.
    text = once(text, '        initial_team = initial_team', '        initial_team = report.team')
    start = text.index('        loaded = load_gcsim_optimizer_artifact_database_input(')
    end = text.index('        character_keys = prepared_character_keys', start)
    validation = text[start:end]
    ready_start = validation.index('        if not loaded.ready')
    ready_check = validation[ready_start:]
    text = text[:start] + text[end:]
    text = once(text, '            snapshot = load_selected_equipped_team_snapshot(',
                '            loaded, snapshot = _load_selected_inventory_snapshot(')
    text = once(text, '                artifact_database=database,\n                character_keys=character_keys,',
                '                engine_context=engine_context,\n                character_keys=character_keys,')
    text = once(text, '        baselines_by_slot: dict[int, dict[str, Any]] = {}',
                ready_check + '        baselines_by_slot: dict[int, dict[str, Any]] = {}')
    images[name] = text.encode()

    name = 'run_workspace/gcsim/tree_identity.py'
    text = images[name].decode().replace('\r\n', '\n')
    text = once(text, '    excluded_relative_paths: Iterable[str] = (),',
                '    excluded_relative_paths: Iterable[str] = (),\n    file_digests: dict[str, str] | None = None,')
    text = once(text, '    for item in files:',
                '    buffer = bytearray(1024 * 1024) if file_digests else None\n    chunk = memoryview(buffer) if buffer is not None else None\n    for item in files:')
    text = once(text, '        digest.update(item.read_bytes())', '''        if file_digests is not None and relative in file_digests:
            # Only the explicitly requested binary needs a second digest and
            # bounded streaming storage. Ordinary small files keep the old read.
            file_digest = hashlib.sha256()
            with item.open("rb") as handle:
                while size := handle.readinto(buffer):
                    digest.update(chunk[:size])
                    file_digest.update(chunk[:size])
            file_digests[relative] = file_digest.hexdigest()''')
    text = once(text,
        '            file_digests[relative] = file_digest.hexdigest()',
        '            file_digests[relative] = file_digest.hexdigest()\n        else:\n            digest.update(item.read_bytes())')
    images[name] = text.encode()

    name = 'run_workspace/gcsim/optimizer_engine_context.py'
    text = images[name].decode().replace('\r\n', '\n')
    text = once(text, '''    actual_artifact_sha256 = _sha256_file(artifact_path)
    actual_engine_tree_sha256 = _engine_tree_sha256(root)''', '''    # Derive the binary's own SHA from the exact same streaming tree pass.
    # The tree and binary retain their distinct digest scopes/manifest checks.
    file_digests: dict[str, str] = {artifact_path.relative_to(root).as_posix(): ""}
    actual_engine_tree_sha256 = _engine_tree_sha256(root, file_digests=file_digests)
    actual_artifact_sha256 = file_digests.get(artifact_path.relative_to(root).as_posix())
    if not actual_artifact_sha256:
        actual_artifact_sha256 = _sha256_file(artifact_path)''')
    text = once(text, 'def _engine_tree_sha256(root: Path) -> str:',
                'def _engine_tree_sha256(root: Path, *, file_digests: dict[str, str] | None = None) -> str:')
    text = once(text, '        excluded_relative_paths=(MANIFEST_FILE_NAME,),',
                '        excluded_relative_paths=(MANIFEST_FILE_NAME,),\n        file_digests=file_digests,')
    images[name] = text.encode()

    name = 'run_workspace/gcsim/source_manifest_build.py'
    text = images[name].decode().replace('\r\n', '\n')
    text = once(text,
        '    engine_dir: str | Path, *, go_sources: dict[str, dict[str, str]] | None = None\n',
        '    engine_dir: str | Path, *, go_sources: dict[str, dict[str, str]] | None = None,\n    module_source: dict[str, str] | None = None,\n')
    text = once(text,
        '            if go_sources is not None and relative.endswith(".go") and not relative.endswith("_test.go"):\n',
        '''            collect_go = go_sources is not None and relative.endswith(".go") and not relative.endswith("_test.go")
            collect_module = module_source is not None and relative == "go.mod"
            if collect_go or collect_module:
''')
    text = once(text,
        '                go_sources[relative] = {"sha256": digest, "text": data.decode("utf-8")}',
        '''                if collect_go:
                    go_sources[relative] = {"sha256": digest, "text": data.decode("utf-8")}
                if collect_module:
                    module_source.update(sha256=digest, text=data.decode("utf-8"))''')
    images[name] = text.encode()

    name = 'run_workspace/gcsim/optimizer_go_all_sources.py'
    text = images[name].decode().replace('\r\n', '\n')
    text = once(text, 'from .artifact_set_catalog import load_gcsim_artifact_set_catalog',
                'from .artifact_set_catalog import load_gcsim_artifact_set_catalog\nfrom .optimizer_engine_context import _sha256_file')
    text = once(text, 'binary_sha = hashlib.sha256(binary.read_bytes()).hexdigest()',
                'binary_sha = _sha256_file(binary)')
    text = once(text, '    tree_sha = (compute_patched_source_tree_sha256(root, go_sources=repository)',
                '    module_source = {} if repository is not None else None\n    tree_sha = (compute_patched_source_tree_sha256(root, go_sources=repository, module_source=module_source)')
    text = once(text, '    def text(relative: str) -> dict[str, str]:\n', '''    def text(relative: str) -> dict[str, str]:
        if repository is not None and relative in repository:
            # These exact bytes were already read and hashed by the current
            # patched-source verification pass. Preserve independent dicts.
            return dict(repository[relative])
''')
    text = once(text,
        '(root / "go.mod").read_text(encoding="utf-8").splitlines()',
        'module_source.get("text", "").splitlines()')
    images[name] = text.encode()

    name = 'run_workspace/gcsim/optimizer_go_session.py'
    text = images[name].decode().replace('\r\n', '\n')
    text = once(text, 'from __future__ import annotations',
                'from __future__ import annotations\nfrom collections import deque')
    text = once(text, 'stderr_lines: list[str] = []',
                'stderr_lines: deque[tuple[str, bool]] = deque(maxlen=8)')
    text = once(text, 'stderr_lines.append(line.rstrip())',
                'stderr_lines.append((line.rstrip()[-2048:], "finish_no_result:" in line))')
    text = once(text, '"\\n".join(stderr_lines[-8:]).strip()',
                '"\\n".join(line for line, _is_finish in tuple(stderr_lines)).strip()')
    text = once(text, '"finish_no_result" if "finish_no_result:" in details else "optimizer_process_failed",',
                '"finish_no_result" if any(is_finish for _line, is_finish in tuple(stderr_lines)) else "optimizer_process_failed",')
    images[name] = text.encode()
    return images
