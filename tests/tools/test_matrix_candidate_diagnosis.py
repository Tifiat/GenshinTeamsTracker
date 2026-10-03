import unittest

from tools.experiments.gcsim.parametric_effects.diagnose_bloom_candidates import non_artifact_identity


class CandidateIdentityTests(unittest.TestCase):
    def test_only_artifact_rows_and_empty_lines_are_ignored(self):
        a = 'a char lvl=90/90;\na add set="one" count=4;\na add stats hp=10;\na skill;\n'
        b = 'a char lvl=90/90;\na add stats hp=20;\n\na skill;\n'
        self.assertEqual(non_artifact_identity(a), non_artifact_identity(b))

    def test_gameplay_changes_and_declaration_order_remain_visible(self):
        a = 'a char lvl=90/90;\nb char lvl=90/90;\na skill;\n'
        for b in (a.replace('90/90', '80/80'), a.replace('skill', 'burst'),
                  'b char lvl=90/90;\na char lvl=90/90;\na skill;\n',
                  a + 'options ignore_burst_energy=true;\n'):
            self.assertNotEqual(non_artifact_identity(a), non_artifact_identity(b))
