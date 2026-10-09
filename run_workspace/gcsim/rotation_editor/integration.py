"""Read-only admission of the locally audited source and UI context.

This fingerprint covers the relevant source files, not runtime/executable parity.
The directory name and the binary's opaque version are never admission keys.
"""

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .conditions import PROFILE
from .options import EngineIdentity, load_local_tables, read_character_options
from .source import load_source_dialect


AUDITED_REVISION = "20d8f7706cc7209afffd6f21aff351c7d9a73398"
AUDITED_FINGERPRINT = "c9e00c1820dd5844e0e7833f7cdd5d3fb15bed5329f4036691ad3d967e3f7bd9"
AUDITED_GROUPS = {
    "internal/characters/bennett": "asc attack bennett burst charge cons plunge skill zz_bennett.dm",
    "internal/characters/chasca": "aimed asc attack burst chasca cons dash jump plunge skill zz_chasca.dm",
    "internal/characters/furina": "asc attack burst charge cons furina plunge skill zz_furina.dm",
    "internal/template/character": "ready",
    "internal/template/nightsoul": "nightsoul",
    "pkg/conditional": "character conditional construct enemy gadgets keys",
    "pkg/core/player/character": "basestat character energy gtt_neutral_world hitlag mods stats",
    "pkg/core/player": "exec",
    "pkg/gcs/ast": "errors item keys lex node position val",
    "pkg/gcs/constant": "op value",
    "pkg/gcs/eval": "eval expr function op stmt sysfunc",
    "pkg/gcs/parser": "fold parse parseCharacter parseCharacterAction parseEnergy parseFn parseHurt parseLet parseOptions parseTarget parseTyping parser",
    "pkg/gcs/validation": "register validate",
    "pkg/modifier": "modifier",
}


def source_fingerprint(root: Path) -> str:
    digest = sha256()
    paths = sorted(f"{directory}/{name}.go" for directory, names in AUDITED_GROUPS.items() for name in names.split())
    for relative in paths:
        path = root / relative
        if path.is_symlink() or path.stat().st_size > 512 * 1024:
            raise ValueError("Unsafe or oversized audited source file")
        digest.update(relative.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


@dataclass(frozen=True)
class EditorEnvironment:
    dialect: object
    identity: EngineIdentity
    character_options: dict
    audited: bool


def load_environment(installation) -> EditorEnvironment:
    root = Path(installation.path)
    manifest = installation.manifest
    metadata = manifest.metadata
    try:
        fingerprint = source_fingerprint(root)
    except (OSError, ValueError):
        fingerprint = ""
    audited = (metadata.get("upstream_repo") == "genshinsim/gcsim"
               and metadata.get("upstream_ref") == "v2.45.0"
               and fingerprint == AUDITED_FINGERPRINT)
    dialect = load_source_dialect(root, identity=PROFILE if audited else "gcsl-syntax-v1")
    try:
        tables = load_local_tables(root)
    except (OSError, ValueError, TypeError):
        tables = (None, None, None)
    # Include registries, docs and manifest freshness in the edit/apply binding.
    # A narrow source audit cannot prove the entire engine's upstream commit,
    # so it must not enable network fetches against a guessed revision.
    binding = sha256(json.dumps({"source": fingerprint, "declared_tree": manifest.engine_tree_hash,
        "aliases": dict(dialect.character_aliases), "tables": tables, "profile": dialect.identity},
        sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    identity = EngineIdentity(installation.engine_id, binding)
    try:
        options = {key: read_character_options(identity, key, *(table or {} for table in tables))
                   for key in set(dialect.character_aliases.values())}
    except (ValueError, TypeError):
        options = {}
    return EditorEnvironment(dialect, identity, options, audited)
