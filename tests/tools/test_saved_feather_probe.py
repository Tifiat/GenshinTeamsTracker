"""No engine calls: exact substitution and managed-entrypoint safety."""
import unittest
from unittest.mock import patch

from tools.experiments.gcsim.parametric_effects.check_saved_feather import main, replace_feather


class SavedFeatherProbeTests(unittest.TestCase):
    def setUp(self):
        self.before = dict(slot='plume', set_uid='nightoftheskysunveiling',
                           main_stat={'key': 'atk', 'value': '311'}, substats=[
                               {'key': 'atk_percent', 'value': '0.093'},
                               {'key': 'crit_rate', 'value': '0.093'},
                               {'key': 'crit_damage', 'value': '0.155'},
                               {'key': 'hp', 'value': '239'}])
        self.after = dict(self.before, substats=[
            {'key': 'atk_percent', 'value': '0.058'},
            {'key': 'crit_rate', 'value': '0.101'},
            {'key': 'crit_damage', 'value': '0.187'},
            {'key': 'hp', 'value': '478'}])
        self.config = ('flins char lvl=90/90 cons=0 talent=10,10,10;\n'
                       'flins add stats hp=5557.000000 atk=348.000000 atk%=1.153000 cr=0.419000 cd=1.430000;\n'
                       'ineffa add stats atk=311 cr=0.5;\noptions iteration=500 workers=4;\n')

    def test_only_four_substats_change(self):
        self.assertEqual(replace_feather(self.config, self.before, self.after),
            self.config.replace('hp=5557.000000', 'hp=5796.000000')
            .replace('atk%=1.153000', 'atk%=1.118000')
            .replace('cr=0.419000', 'cr=0.427000')
            .replace('cd=1.430000', 'cd=1.462000'))

    def test_roundtrip(self):
        changed = replace_feather(self.config, self.before, self.after)
        self.assertEqual(replace_feather(changed, self.after, self.before), self.config)

    def test_rejects_other_set(self):
        with self.assertRaises(ValueError):
            replace_feather(self.config, self.before, dict(self.after, set_uid='other'))

    def test_unmanaged_refused_before_reading_inputs(self):
        with patch.dict('os.environ', {}, clear=True), self.assertRaises(RuntimeError):
            main()


if __name__ == '__main__':
    unittest.main()
