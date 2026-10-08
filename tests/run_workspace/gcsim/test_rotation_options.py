import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import time
import unittest
from unittest.mock import patch

from run_workspace.gcsim.rotation_editor.options import (
    CharacterOptionService,
    EngineIdentity,
    OptionCache,
    fetch_pinned_tables,
    load_local_tables,
    read_character_options,
)


REVISION = "a" * 40


def tables(*keys):
    return (
        {key: [{"ability": "skill", "invalid": False, "note": "Documented"}] for key in keys},
        {key: [{"ability": "skill", "param": "hold", "desc": "0 or 1"}] for key in keys},
        {key: [] for key in keys},
    )


class RotationOptionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.identity = EngineIdentity("engine-a", "fingerprint-a", REVISION)

    def cache(self, **limits):
        return OptionCache(self.root / "owned", **limits)

    def test_shape_and_unknown_character(self):
        value = read_character_options(self.identity, "chasca", *tables("chasca"))
        self.assertEqual(value.actions[0].name, "skill")
        self.assertEqual(value.parameters[0].key, "hold")
        self.assertEqual(value.fields, ())
        self.assertEqual(value.origin, "source")
        self.assertEqual(read_character_options(self.identity, "unknown", *tables("chasca")).origin, "unavailable")
        with self.assertRaises(ValueError):
            read_character_options(self.identity, "chasca", {"chasca": [{"ability": "skill", "invalid": 0}]}, {}, {})

    def test_app_schema_upgrade_removes_only_owned_older_cache(self):
        cache = self.cache()
        cache.save(read_character_options(self.identity, "chasca", *tables('chasca')))
        old = list(cache.root.glob('options-v1-*.json'))[0]
        rotation = cache.root / 'rotation.txt'
        shipped = cache.root / 'dictionary.json'
        future = cache.root / ('options-v3-' + 'c' * 64 + '.json')
        for path in (rotation, shipped, future):
            path.write_text('preserve', encoding='utf-8')
        class NextSchemaCache(OptionCache):
            SCHEMA = 2
        upgraded = NextSchemaCache(cache.root)
        self.assertFalse(old.exists())
        self.assertEqual([path.read_text(encoding='utf-8') for path in (rotation, shipped, future)], ['preserve'] * 3)
        upgraded.save(read_character_options(self.identity, 'chasca', *tables('chasca')))
        self.assertEqual(len(list(cache.root.glob('options-v2-*.json'))), 1)
        self.assertIsNotNone(upgraded.get(self.identity, 'chasca'))

    def test_local_tables_are_loaded_from_injected_root(self):
        base = self.root / "engine" / "ui/packages/docs/src/components"
        for name, data in zip(("Actions", "Params", "Fields"), tables("chasca")):
            path = base / name / "character.dm.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(read_character_options(self.identity, "chasca", *load_local_tables(self.root / "engine")).fields, ())

    def test_cold_hit_and_new_character(self):
        cache = self.cache()
        calls = []
        def local(identity):
            calls.append(identity)
            return tables("chasca", "furina")
        with CharacterOptionService(local, cache) as service:
            self.assertEqual(service.select_character(self.identity, "chasca").result(2).origin, "local")
            self.assertEqual(service.select_character(self.identity, "furina").result(2).origin, "local")
        with CharacterOptionService(local, cache) as service:
            self.assertEqual(service.select_character(self.identity, "chasca").result(2).origin, "cache")
        self.assertEqual(len(calls), 1)

    def test_prepare_shares_one_local_table_load(self):
        calls = []
        def local(identity):
            calls.append(identity)
            return tables("chasca", "furina", "bennett", "ororon")
        with CharacterOptionService(local, self.cache()) as service:
            pending = service.prepare(self.identity, ["chasca", "furina", "bennett", "ororon"])
            self.assertEqual({key: future.result(2).character_key for key, future in pending.items()},
                             {key: key for key in pending})
        self.assertEqual(calls, [self.identity])

    def test_dedup_and_stale_engine_completion(self):
        cache = self.cache()
        blocked = Event()
        release = Event()
        newer = EngineIdentity("engine-b", "fingerprint-b")
        calls = []
        def local(identity):
            calls.append(identity)
            if identity == self.identity:
                blocked.set()
                release.wait(2)
            return tables("chasca")
        with CharacterOptionService(local, cache, workers=2) as service:
            first = service.select_character(self.identity, "chasca")
            self.assertTrue(blocked.wait(2))
            self.assertIs(first, service.select_character(self.identity, "chasca"))
            second = service.select_character(newer, "chasca")
            self.assertEqual(second.result(2).identity, newer)
            release.set()
            self.assertEqual(first.result(2).identity, self.identity)
            self.assertIsNone(service.result(self.identity, "chasca"))
            self.assertEqual(service.result(newer, "chasca").identity, newer)
        self.assertEqual(calls.count(self.identity), 1)

    def test_identity_change_cancels_queued_old_request(self):
        blocked = Event()
        release = Event()
        newer = EngineIdentity("engine-b", "fingerprint-b")
        calls = []
        def local(identity):
            calls.append(identity)
            if identity == self.identity:
                blocked.set()
                release.wait(2)
            return tables("chasca", "furina")
        with CharacterOptionService(local, self.cache(), workers=1) as service:
            running = service.select_character(self.identity, "chasca")
            self.assertTrue(blocked.wait(2))
            queued = service.select_character(self.identity, "furina")
            current = service.select_character(newer, "chasca")
            self.assertTrue(queued.cancelled())
            release.set()
            self.assertEqual(running.result(2).identity, self.identity)
            self.assertEqual(current.result(2).identity, newer)
            self.assertIsNone(service.result(self.identity, "chasca"))
        self.assertEqual(calls.count(self.identity), 1)

    def test_outstanding_work_is_bounded_without_waiting_for_loader(self):
        blocked = Event()
        release = Event()
        def local(identity):
            blocked.set()
            release.wait(2)
            return tables("c0")
        with CharacterOptionService(local, self.cache(), workers=1) as service:
            first = service.select_character(self.identity, "c0")
            self.assertTrue(blocked.wait(2))
            queued = [service.select_character(self.identity, f"c{index}") for index in range(1, 64)]
            self.assertEqual(service.select_character(self.identity, "c64").result(2).warnings, ("service_busy",))
            service.select_character(EngineIdentity("new", "new"), "c0")
            self.assertTrue(all(future.cancelled() for future in queued))
            release.set()
            self.assertEqual(first.result(2).character_key, "c0")

    def test_failure_offline_retry_and_good_cache(self):
        cache = self.cache()
        absent = EngineIdentity("engine", "fingerprint")
        calls = []
        def local(identity):
            calls.append(1)
            if len(calls) == 1:
                raise OSError("offline")
            return tables("furina")
        with CharacterOptionService(local, cache, fetch_loader=lambda identity, names: self.fail("network called")) as service:
            self.assertEqual(service.select_character(absent, "furina").result(2).origin, "unavailable")
            self.assertEqual(service.select_character(absent, "furina", retry=True).result(2).origin, "local")
        self.assertEqual(cache.get(absent, "furina").origin, "cache")

    def test_invalid_schema_and_corruption_are_ignored(self):
        cache = self.cache()
        original = read_character_options(self.identity, "chasca", *tables("chasca"))
        cache.save(original)
        path = cache._path(self.identity, "chasca")
        envelope = json.loads(path.read_text())
        envelope["schema"] = 999
        path.write_text(json.dumps(envelope))
        self.assertIsNone(cache.get(self.identity, "chasca"))
        path.write_text("{")
        self.assertIsNone(cache.get(self.identity, "chasca"))
        cache.save(original)
        self.assertEqual(cache.get(self.identity, "chasca").origin, "cache")

    def test_failed_write_preserves_previous_valid_cache(self):
        cache = self.cache()
        original = read_character_options(self.identity, "chasca", *tables("chasca"))
        cache.save(original)
        changed_tables = ({"chasca": [{"ability": "burst", "invalid": False}]}, {}, {})
        changed = read_character_options(self.identity, "chasca", *changed_tables)
        with patch("run_workspace.gcsim.rotation_editor.options.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                cache.save(changed)
        self.assertEqual(cache.get(self.identity, "chasca").actions[0].name, "skill")
        self.assertEqual(list(cache.root.glob("*.tmp")), [])

    def test_pinned_fetch_identity_and_size_limit(self):
        urls = []
        class Response:
            def __init__(self, body):
                self.body = body
            def __enter__(self):
                return self
            def __exit__(self, *unused):
                pass
            def read(self, size):
                return self.body[:size]
        payload = [json.dumps(x).encode() for x in tables("chasca")]
        def opener(url, *, timeout):
            urls.append((url, timeout))
            return Response(payload[len(urls) - 1])
        self.assertEqual(len(fetch_pinned_tables(self.identity, opener=opener)), 3)
        self.assertTrue(all(f"/{REVISION}/" in url and url.startswith("https://raw.githubusercontent.com/genshinsim/gcsim/") for url, _ in urls))
        self.assertEqual(fetch_pinned_tables(EngineIdentity("e", "f"), opener=opener), (None, None, None))
        self.assertEqual(len(urls), 3)
        with self.assertRaises(ValueError):
            fetch_pinned_tables(self.identity, opener=lambda *_args, **_kwargs: Response(b" " * (2 * 1024 * 1024 + 1)))
        def partly_offline(url, *, timeout):
            if "/Fields/" in url:
                raise OSError("offline")
            return Response(json.dumps(tables("chasca")[1]).encode())
        partial = fetch_pinned_tables(self.identity, ("Params", "Fields"), opener=partly_offline)
        self.assertIsNone(partial[0])
        self.assertIn("chasca", partial[1])
        self.assertIsNone(partial[2])

    def test_fetches_only_missing_table_at_pinned_revision(self):
        requested = []
        local_tables = tables("chasca")
        def fetch(identity, names):
            requested.append((identity, names))
            return (None, None, local_tables[2])
        with CharacterOptionService(lambda identity: (local_tables[0], local_tables[1], None), self.cache(), fetch_loader=fetch) as service:
            self.assertEqual(service.select_character(self.identity, "chasca").result(2).origin, "mixed")
        self.assertEqual(requested, [(self.identity, ("Fields",))])

    def test_partial_local_options_survive_fetch_outage_and_are_not_cached(self):
        local_tables = tables("chasca")
        for fetch in (lambda identity, names: (None, None, None),
                      lambda identity, names: (_ for _ in ()).throw(OSError("offline"))):
            cache = self.cache()
            with CharacterOptionService(lambda identity: (local_tables[0], local_tables[1], None), cache, fetch_loader=fetch) as service:
                result = service.select_character(self.identity, "chasca").result(2)
            self.assertEqual(result.origin, "partial")
            self.assertEqual(result.actions[0].name, "skill")
            self.assertEqual(result.parameters[0].key, "hold")
            self.assertEqual(result.fields, ())
            self.assertIn("fields_unavailable", result.warnings)
            self.assertTrue(all(warning.replace("_", "").islower() for warning in result.warnings))
            self.assertIsNone(cache.get(self.identity, "chasca"))

    def test_new_character_fetches_its_options_from_all_tables(self):
        requested = []
        def fetch(identity, names):
            requested.append(names)
            return tables("newhero")
        with CharacterOptionService(lambda identity: tables("chasca"), self.cache(), fetch_loader=fetch) as service:
            result = service.select_character(self.identity, "newhero").result(2)
        self.assertEqual(result.origin, "official")
        self.assertEqual(result.parameters[0].key, "hold")
        self.assertEqual(requested, [("Actions", "Params", "Fields")])

    def test_cache_limits_and_unrelated_files_survive_cleanup(self):
        cache = self.cache(max_entries=2, max_bytes=4096)
        sentinel = cache.root / "rotation.txt"
        sentinel.write_text("keep")
        partial = cache.root / ("options-v1-" + "b" * 64 + "." + "c" * 32 + ".tmp")
        partial.write_text("partial")
        os.utime(partial, (time.time() - 7200, time.time() - 7200))
        legacy = cache.root / ("options-v1-" + "f" * 64 + ".tmp")
        legacy.write_text("old partial")
        os.utime(legacy, (time.time() - 7200, time.time() - 7200))
        recent = cache.root / ("options-v1-" + "d" * 64 + "." + "e" * 32 + ".tmp")
        recent.write_text("active or recent")
        for key in ("chasca", "furina", "bennett"):
            cache.save(read_character_options(self.identity, key, *tables(key)))
        self.assertFalse(partial.exists())
        self.assertFalse(legacy.exists())
        self.assertTrue(recent.exists())
        self.assertEqual(sentinel.read_text(), "keep")
        owned = list(cache.root.glob("options-v1-*.json"))
        self.assertLessEqual(len(owned), 2)
        self.assertLessEqual(sum(path.stat().st_size for path in owned), 4096)

    def test_other_cache_instance_cannot_clean_active_temp(self):
        cache = self.cache()
        entered = Event()
        release = Event()
        real_replace = os.replace
        errors = []
        def delayed_replace(source, target):
            entered.set()
            release.wait(2)
            real_replace(source, target)
        def writer():
            try:
                cache.save(read_character_options(self.identity, "chasca", *tables("chasca")))
            except Exception as error:
                errors.append(error)
        with patch("run_workspace.gcsim.rotation_editor.options.os.replace", side_effect=delayed_replace):
            thread = Thread(target=writer)
            thread.start()
            self.assertTrue(entered.wait(2))
            active_temp = next(cache.root.glob("*.tmp"))
            os.utime(active_temp, (time.time() - 7200, time.time() - 7200))
            OptionCache(cache.root).cleanup()
            self.assertEqual(len(list(cache.root.glob("*.tmp"))), 1)
            release.set()
            thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(cache.get(self.identity, "chasca").origin, "cache")


if __name__ == "__main__":
    unittest.main()
