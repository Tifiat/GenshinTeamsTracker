from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from run_workspace.gcsim.rotation_editor.source import load_source_dialect


class RotationSourceTests(unittest.TestCase):
    def registry(self, root: Path, *, key: str = "Furina"):
        keys = root / "pkg/core/keys/character.dm.go"
        aliases = root / "pkg/shortcut/character.dm.go"
        keys.parent.mkdir(parents=True)
        aliases.parent.mkdir(parents=True)
        keys.write_text('package keys\nconst (\n NoChar Char = iota //\n Furina // furina\n)\n', encoding='utf-8')
        aliases.write_text('package shortcut\nvar CharNameToKey = map[string]keys.Char{\n "furina": keys.' + key + ',\n "furinadefontaine": keys.' + key + ',\n}\n', encoding='utf-8')
        return keys, aliases

    def test_aliases_use_engine_stable_keys_without_inferred_mechanics_profile(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.registry(root)
            dialect = load_source_dialect(root)
            self.assertEqual(dialect.character_aliases['furinadefontaine'], 'furina')
            self.assertEqual(dialect.identity, 'gcsl-syntax-v1')

    def test_missing_key_or_changed_generated_shape_is_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            keys, _ = self.registry(root, key='Unknown')
            with self.assertRaisesRegex(ValueError, 'Incomplete'):
                load_source_dialect(root)
            keys.write_text('changed registry schema', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Unrecognized'):
                load_source_dialect(root)

    def test_oversized_public_registry_is_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            keys, _ = self.registry(root)
            keys.write_text(' ' * (256 * 1024 + 1), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'oversized'):
                load_source_dialect(root)


if __name__ == '__main__':
    unittest.main()
