"""No engine or DB calls: isolated counterfactuals and input identity."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from tools.experiments.gcsim.parametric_effects.compare_navia_user_swaps import (
    main, non_artifact_hash, variants,
)


class NaviaUserSwapsTests(unittest.TestCase):
    def setUp(self):
        slots = ('flower', 'plume', 'sands', 'goblet', 'circlet')
        self.baseline = {actor: dict(zip(slots, ids)) for actor, ids in (
            ('navia', (1537, 1533, 63, 19, 1565)),
            ('xilonen', (207, 1288, 209, 54, 1617)),
            ('ineffa', (1560, 72, 73, 1566, 1567)),
            ('columbina', (31, 1598, 33, 1563, 1405)),
        )}

    def test_every_variant_starts_from_baseline_not_previous_variant(self):
        original = deepcopy(self.baseline)
        cases = variants(self.baseline)
        self.assertEqual(len(cases), 16)
        self.assertEqual(self.baseline, original)
        for name, assignment in cases:
            changed = [actor for actor in original if assignment[actor] != original[actor]]
            self.assertEqual(len(changed), int(name != 'baseline'))
            self.assertEqual(len({item for build in assignment.values() for item in build.values()}), 20)
        goblet = dict(cases)['navia_goblet64_atk_em63']
        self.assertEqual(goblet['navia']['plume'], 1533)

    def test_physical_collision_is_rejected(self):
        self.baseline['ineffa']['plume'] = 1535
        with self.assertRaises(ValueError):
            variants(self.baseline)

    def test_artifact_rows_and_empty_lines_are_ignored(self):
        a = 'navia char lvl=90/90;\nnavia add stats cr=0.3;\nnavia add set="x" count=4;\n\noptions iteration=2000;\nnavia skill;\n'
        b = a.replace('cr=0.3', 'cr=0.5').replace('navia add set="x" count=4;',
            'navia add set="y" count=2;\nnavia add set="z" count=2;')
        self.assertEqual(non_artifact_hash(a), non_artifact_hash(b))
        self.assertNotEqual(non_artifact_hash(a), non_artifact_hash(b.replace('navia skill;', 'navia burst;')))
        self.assertNotEqual(non_artifact_hash(a), non_artifact_hash(b.replace('lvl=90/90', 'lvl=80/90')))

    def test_unmanaged_refused_before_reading_inputs(self):
        with patch.dict('os.environ', {}, clear=True), self.assertRaises(RuntimeError):
            main()


if __name__ == '__main__':
    unittest.main()
