"""Exact expression/port checks for the temporary observer relocation gate."""
from copy import deepcopy
import hashlib
import json
import unittest

from tools.experiments.gcsim.parametric_effects.capture_equivalence import (
    _fold_known_constant, canonical_capture, capture_comparison_kind, captures_equal)


class CaptureEquivalenceTests(unittest.TestCase):
    def fixture(self):
        member = dict(seed=7, duration_ms=1000, topology_sha256='same', nodes=[
            dict(node_id=1, operation='constant', value='0', inputs=[]),
            dict(node_id=2, operation='constant', value='0', inputs=[]),
            dict(node_id=3, operation='subtract', inputs=[dict(node_id=1, relation='left'), dict(node_id=2, relation='right')])],
            channels=[dict(root_node_id=3, baseline_damage='0')], opaque_boundaries=[], energy_ledger={})
        effects = dict(neutral=dict(stats=[dict(node_id=1, owner='a', stat='atk', point={'order': 1}),
                                           dict(node_id=2, owner='b', stat='atk', point={'order': 2})],
                                    reads=[], ledger={'events': []}), effect_inputs=[], resistance_inputs=[])
        return member, effects

    def canonical(self, member, effects, **options):
        raw = json.dumps(member).encode()
        sidecar = deepcopy(effects)
        sidecar['member_content_sha256'] = hashlib.sha256(raw).hexdigest()
        return canonical_capture(raw, json.dumps(sidecar).encode(), **options)

    def status_fixture(self):
        member, effects = self.fixture()
        effects['neutral'].update(reads_complete=True, world={'complete': True, 'states': []},
                                 ledger={'truncated': False, 'events': []}, states=[
            dict(order=10, frame=20, kind='status_add', owner=0, key='z', expiry=80),
            dict(order=11, frame=20, kind='status_add', owner=0, key='a', expiry=80)])
        return member, effects

    def test_only_unobserved_independent_status_add_order_can_commute(self):
        member, first = self.status_fixture()
        second = deepcopy(first)
        second['neutral']['states'][0]['key'] = 'a'
        second['neutral']['states'][1]['key'] = 'z'
        self.assertNotEqual(self.canonical(member, first), self.canonical(member, second))
        options = dict(independent_status_adds=True)
        self.assertEqual(self.canonical(member, first, **options), self.canonical(member, second, **options))
        for change in ('world_read', 'stat_read', 'event', 'order_gap', 'frame', 'expiry', 'owner',
                       'incomplete_reads', 'incomplete_world', 'truncated', 'unknown_field',
                       'order_index', 'order_string', 'duplicate_order', 'nonmonotone_order',
                       'state_order_reference'):
            a, b = deepcopy(first), deepcopy(second)
            for effects in (a, b):
                n = effects['neutral']
                if change == 'world_read': n['world']['states'] = [dict(order=10, modifiers=[])]
                if change == 'stat_read': n['stats'][0]['point']['order'] = 10
                if change == 'event': n['ledger']['events'] = [dict(order=9, end_order=11)]
                if change == 'order_gap': n['states'][1]['order'] = 12
                if change == 'incomplete_reads': n['reads_complete'] = False
                if change == 'incomplete_world': n['world']['complete'] = False
                if change == 'truncated': n['ledger']['truncated'] = True
                if change == 'unknown_field': n['states'][0]['unknown_effect'] = True
                if change == 'order_index': effects['future_observer'] = {'order_index': 10}
                if change == 'order_string': effects['future_observer'] = {'order': '10'}
                if change == 'duplicate_order': n['states'].append(dict(n['states'][0], key='third'))
                if change == 'nonmonotone_order': n['states'].append(dict(n['states'][0], order=9, key='third'))
                if change == 'state_order_reference':
                    n['states'].append(dict(n['states'][0], order=12, key='third',
                                            kind='status_delete', trigger_order=10))
            if change == 'frame': b['neutral']['states'][0]['frame'] = 21
            if change == 'expiry': b['neutral']['states'][0]['expiry'] = 81
            if change == 'owner': b['neutral']['states'][0]['owner'] = 1
            with self.subTest(change=change):
                self.assertNotEqual(self.canonical(member, a, **options), self.canonical(member, b, **options))

    def test_repeated_key_writes_and_deletes_keep_order(self):
        member, a = self.status_fixture()
        a['neutral']['states'][1].update(key='z', expiry=90)
        b = deepcopy(a)
        b['neutral']['states'][0]['expiry'], b['neutral']['states'][1]['expiry'] = 90, 80
        options = dict(independent_status_adds=True)
        self.assertNotEqual(self.canonical(member, a, **options), self.canonical(member, b, **options))
        a['neutral']['states'][1]['kind'] = 'status_delete'
        b = deepcopy(a)
        b['neutral']['states'][0]['kind'], b['neutral']['states'][1]['kind'] = 'status_delete', 'status_add'
        self.assertNotEqual(self.canonical(member, a, **options), self.canonical(member, b, **options))

    def test_new_hash_refinement_does_not_rewrite_or_require_old_receipts(self):
        self.assertTrue(captures_equal({'canonical_sha256': 'a'}, {'canonical_sha256': 'a'}))
        self.assertFalse(captures_equal({}, {}))
        self.assertFalse(captures_equal({'canonical_sha256': 'a'}, {'canonical_sha256': 'b'}))
        self.assertTrue(captures_equal({'canonical_sha256': 'a', 'independent_status_sha256_v1': 'same'},
                                       {'canonical_sha256': 'b', 'independent_status_sha256_v1': 'same'}))
        self.assertTrue(captures_equal({'canonical_sha256': 'a', 'independent_status_constant_fold_sha256_v1': 'same'},
                                       {'canonical_sha256': 'b', 'independent_status_constant_fold_sha256_v1': 'same'}))
        self.assertFalse(captures_equal({'independent_status_constant_fold_sha256_v1': 'same'},
                                        {'independent_status_sha256_v1': 'same'}))
        algebraic = {'algebraic_capture_sha256_v1': 'same'}
        self.assertFalse(captures_equal(algebraic, algebraic))
        self.assertEqual('unmatched', capture_comparison_kind(algebraic, algebraic))
        self.assertEqual('unmatched', capture_comparison_kind(algebraic, algebraic, allow_algebraic=True))
        first = {'canonical_sha256': 'a', 'independent_status_sha256_v1': 'a',
                 'independent_status_constant_fold_sha256_v1': 'a', **algebraic}
        second = {'canonical_sha256': 'b', 'independent_status_sha256_v1': 'b',
                  'independent_status_constant_fold_sha256_v1': 'b', **algebraic}
        self.assertEqual('algebraic', capture_comparison_kind(first, second, allow_algebraic=True))
        self.assertEqual('strict', capture_comparison_kind({'canonical_sha256': 'same', **algebraic},
                                                           {'canonical_sha256': 'same', **algebraic},
                                                           allow_algebraic=True))

    def test_algebraic_commutation_is_separate_from_float64_identity(self):
        a, effects = self.constant_fixture(('1e16', '-1e16', '1'))
        b = deepcopy(a)
        for node, value in zip(b['nodes'][:3], ('1e16', '1', '-1e16')):
            node['value'] = value
        self.assertNotEqual(self.canonical(a, effects), self.canonical(b, effects))
        self.assertNotEqual(self.canonical(a, effects, fold_unbound_constants=True),
                            self.canonical(b, effects, fold_unbound_constants=True))
        self.assertEqual(self.canonical(a, effects, algebraic_commutative=True),
                         self.canonical(b, effects, algebraic_commutative=True))

    def test_algebraic_scope_preserves_noncommutative_nodes_and_binding_details(self):
        a, effects = self.constant_fixture(('1', '2', '3'))
        b = deepcopy(a)
        b['nodes'][0]['value'], b['nodes'][1]['value'] = '2', '1'
        for change in ('subtract', 'branch', 'edge_metadata', 'node_metadata',
                       'owner', 'time', 'multiplicity'):
            left, right = deepcopy(a), deepcopy(b)
            e, f = deepcopy(effects), deepcopy(effects)
            if change == 'subtract':
                left['nodes'][-1]['operation'] = right['nodes'][-1]['operation'] = 'subtract'
            if change == 'branch':
                left['nodes'][-1]['operation'] = right['nodes'][-1]['operation'] = 'select_lt'
            if change == 'edge_metadata': right['nodes'][-1]['inputs'][0]['future'] = True
            if change == 'node_metadata': right['nodes'][-1]['future'] = True
            if change == 'owner':
                e['effect_inputs'] = [dict(node_id=1, owner='a', frame=10)]
                f['effect_inputs'] = [dict(node_id=2, owner='b', frame=10)]
            if change == 'time':
                e['effect_inputs'] = [dict(node_id=1, owner='a', frame=10)]
                f['effect_inputs'] = [dict(node_id=2, owner='a', frame=11)]
            if change == 'multiplicity':
                right['nodes'][-1]['inputs'][0]['node_id'] = 2
            with self.subTest(change=change):
                self.assertNotEqual(self.canonical(left, e, algebraic_commutative=True),
                                    self.canonical(right, f, algebraic_commutative=True))

    def constant_fixture(self, values=('1', '2', '3'), operation='add'):
        nodes = [dict(node_id=i, operation='constant', value=value, inputs=[])
                 for i, value in enumerate(values, 1)]
        nodes.append(dict(node_id=len(nodes)+1, operation=operation,
                          inputs=[dict(node_id=i, relation=f'input/{i-1:06d}')
                                  for i in range(1, len(values)+1)]))
        member = dict(seed=7, duration_ms=1000, topology_sha256='same', nodes=nodes,
                      channels=[dict(root_node_id=len(nodes), baseline_damage='6')],
                      opaque_boundaries=[], energy_ledger={})
        effects = dict(neutral=dict(stats=[], reads=[], reads_complete=True,
                                    world={'complete': True, 'states': []},
                                    ledger={'truncated': False, 'events': []}),
                       effect_inputs=[], resistance_inputs=[])
        return member, effects

    def test_only_exact_unbound_constant_islands_fold_in_original_float64_order(self):
        a, effects = self.constant_fixture()
        b = deepcopy(a)
        for node, value in zip(b['nodes'][:3], ('3', '2', '1')):
            node['value'] = value  # Both edge lists remain valid sorted-ID IR.
        self.assertNotEqual(self.canonical(a, effects), self.canonical(b, effects))
        self.assertEqual(self.canonical(a, effects, fold_unbound_constants=True),
                         self.canonical(b, effects, fold_unbound_constants=True))
        c, effects = self.constant_fixture(('1e16', '-1e16', '1'))
        d = deepcopy(c)
        for node, value in zip(d['nodes'][:3], ('1e16', '1', '-1e16')):
            node['value'] = value
        self.assertNotEqual(self.canonical(c, effects, fold_unbound_constants=True),
                            self.canonical(d, effects, fold_unbound_constants=True))
        for operation in ('multiply', 'min', 'max'):
            a, effects = self.constant_fixture(('2', '3', '4'), operation)
            b = deepcopy(a)
            for node, value in zip(b['nodes'][:3], ('4', '2', '3')):
                node['value'] = value
            with self.subTest(operation=operation):
                self.assertEqual(self.canonical(a, effects, fold_unbound_constants=True),
                                 self.canonical(b, effects, fold_unbound_constants=True))

    def test_annotated_constant_is_a_barrier_even_when_reordering_keeps_point_value(self):
        a, e = self.constant_fixture()
        b, f = deepcopy(a), deepcopy(e)
        b['nodes'][0]['value'], b['nodes'][1]['value'] = '2', '1'
        e['effect_inputs'] = [dict(node_id=1, owner='actor', key='damage', frame=10)]
        f['effect_inputs'] = [dict(node_id=2, owner='actor', key='damage', frame=10)]
        self.assertNotEqual(self.canonical(a, e, fold_unbound_constants=True),
                            self.canonical(b, f, fold_unbound_constants=True))

    def test_equal_zero_islands_under_variable_parent_keep_shape_and_ports(self):
        a, e = self.constant_fixture(('.12', '-1', '.12', '.15', '.15'))
        # Two islands: .12 + (-1 * .12) and .15 + (-1 * .15).
        a['nodes'] += [
            dict(node_id=7, operation='multiply', inputs=[dict(node_id=2, relation='input/000000'),
                                                           dict(node_id=3, relation='input/000001')]),
            dict(node_id=8, operation='add', inputs=[dict(node_id=1, relation='input/000000'),
                                                      dict(node_id=7, relation='input/000001')]),
            dict(node_id=9, operation='multiply', inputs=[dict(node_id=2, relation='input/000000'),
                                                           dict(node_id=5, relation='input/000001')]),
            dict(node_id=10, operation='add', inputs=[dict(node_id=4, relation='input/000000'),
                                                       dict(node_id=9, relation='input/000001')]),
            dict(node_id=11, operation='artifact_stat', coordinate='actor.atk', inputs=[]),
            dict(node_id=12, operation='add', inputs=[dict(node_id=8, relation='input/000000'),
                                                       dict(node_id=10, relation='input/000001'),
                                                       dict(node_id=11, relation='input/000002')])]
        a['channels'][0]['root_node_id'] = 12
        b, f = deepcopy(a), deepcopy(e)
        for index, value in ((0, '.15'), (2, '.15'), (3, '.12'), (4, '.12')):
            b['nodes'][index]['value'] = value  # Same leaves, reversed island construction order.
        self.assertNotEqual(self.canonical(a, e), self.canonical(b, f))
        self.assertEqual(self.canonical(a, e, fold_unbound_constants=True),
                         self.canonical(b, f, fold_unbound_constants=True))
        g = deepcopy(e)
        g['effect_inputs'] = [dict(node_id=1, owner='a', frame=1, key='bonus')]
        h = deepcopy(g)
        h['effect_inputs'][0]['node_id'] = 4  # Same observed .12, different ordered parent input.
        self.assertNotEqual(self.canonical(a, g, fold_unbound_constants=True),
                            self.canonical(b, h, fold_unbound_constants=True))
        changed = deepcopy(b)
        changed['nodes'][0]['value'] = '.13'
        self.assertNotEqual(self.canonical(a, e, fold_unbound_constants=True),
                            self.canonical(changed, f, fold_unbound_constants=True))

    def test_opaque_boundaries_and_incomplete_sidecars_disable_folding(self):
        a, effects = self.constant_fixture()
        b = deepcopy(a)
        for node, value in zip(b['nodes'][:3], ('3', '2', '1')):
            node['value'] = value
        a['opaque_boundaries'] = [{'node_id': 1, 'reason': 'opaque'}]
        b['opaque_boundaries'] = [{'node_id': 3, 'reason': 'opaque'}]
        self.assertNotEqual(self.canonical(a, effects, fold_unbound_constants=True),
                            self.canonical(b, effects, fold_unbound_constants=True))
        for guard in ('reads_complete', 'world_complete', 'ledger_truncated'):
            incomplete = deepcopy(effects)
            if guard == 'reads_complete': incomplete['neutral']['reads_complete'] = False
            if guard == 'world_complete': incomplete['neutral']['world']['complete'] = False
            if guard == 'ledger_truncated': incomplete['neutral']['ledger']['truncated'] = True
            with self.subTest(guard=guard):
                self.assertEqual(self.canonical(a, incomplete),
                                 self.canonical(a, incomplete, fold_unbound_constants=True))

    def test_equal_result_does_not_erase_constant_island_arity(self):
        a, effects = self.constant_fixture(('1', '2', '0'))
        b = deepcopy(a)
        b['nodes'][-1]['inputs'].pop()  # Same sum, same node count, different graph arity.
        self.assertNotEqual(self.canonical(a, effects, fold_unbound_constants=True),
                            self.canonical(b, effects, fold_unbound_constants=True))

    def test_fold_barriers_and_structural_counts_remain_distinct(self):
        original, effects = self.constant_fixture()
        options = dict(fold_unbound_constants=True)
        for change in ('literal', 'arity', 'node_count', 'channel', 'ledger', 'port_owner', 'port_time',
                       'port_key', 'unknown_edge', 'unknown_node', 'unknown_operation'):
            a, e = deepcopy(original), deepcopy(effects)
            b, f = deepcopy(original), deepcopy(effects)
            if change == 'literal': b['nodes'][0]['value'] = '9'
            if change == 'arity': b['nodes'][-1]['inputs'].pop()
            if change == 'node_count': b['nodes'].insert(3, dict(node_id=5, operation='constant', value='0', inputs=[]))
            if change == 'channel': b['channels'][0]['baseline_damage'] = '7'
            if change == 'ledger': f['neutral']['ledger']['events'] = [{'frame': 1}]
            if change.startswith('port_'):
                for side in (e, f):
                    side['effect_inputs'] = [dict(node_id=1, owner='a', key='damage', frame=10)]
                if change == 'port_owner': f['effect_inputs'][0]['owner'] = 'b'
                if change == 'port_time': f['effect_inputs'][0]['frame'] = 11
                if change == 'port_key': f['effect_inputs'][0]['key'] = 'other'
            if change == 'unknown_edge': b['nodes'][-1]['inputs'][0]['extra'] = 'future'
            if change == 'unknown_node': b['nodes'][-1]['future'] = True
            if change == 'unknown_operation': b['nodes'][-1]['operation'] = 'power'
            with self.subTest(change=change):
                self.assertNotEqual(self.canonical(a, e, **options), self.canonical(b, f, **options))

    def test_nonfinite_unknown_and_signed_zero_are_not_blurred(self):
        literal = dict(node_id=1, operation='constant', value='NaN', inputs=[])
        self.assertIsNone(_fold_known_constant(literal, []))
        self.assertIsNone(_fold_known_constant(dict(literal, value='Infinity'), []))
        self.assertIsNone(_fold_known_constant(dict(literal, value='1', future=True), []))
        aggregate = dict(node_id=3, operation='add', inputs=[
            dict(node_id=1, relation='input/000000'), dict(node_id=2, relation='input/000001')])
        one = _fold_known_constant(dict(node_id=1, operation='constant', value='1', inputs=[]), [])
        two = _fold_known_constant(dict(node_id=2, operation='constant', value='2', inputs=[]), [])
        self.assertIsNone(_fold_known_constant(dict(aggregate, inputs=[dict(node_id=True, relation='input/000000'),
                                                                 dict(node_id=2, relation='input/000001')]), [one, two]))
        self.assertIsNone(_fold_known_constant(dict(aggregate, inputs=[dict(node_id=2, relation='input/000000'),
                                                                 dict(node_id=1, relation='input/000001')]), [two, one]))
        negative, effects = self.constant_fixture(('-0', '1'))
        positive = deepcopy(negative)
        positive['nodes'][0]['value'] = '0'
        self.assertNotEqual(self.canonical(negative, effects, fold_unbound_constants=True),
                            self.canonical(positive, effects, fold_unbound_constants=True))
        spelled = deepcopy(negative)
        spelled['nodes'][0]['value'] = '-0.0'
        self.assertEqual(self.canonical(negative, effects, fold_unbound_constants=True),
                         self.canonical(spelled, effects, fold_unbound_constants=True))

    def test_local_renumbering_and_discovery_order_preserve_expressions_and_ports(self):
        a, e = self.fixture()
        b, f = deepcopy(a), deepcopy(e)
        b['nodes'][0]['node_id'], b['nodes'][1]['node_id'] = 2, 1
        b['nodes'][2]['inputs'][0]['node_id'], b['nodes'][2]['inputs'][1]['node_id'] = 2, 1
        f['neutral']['stats'][0]['node_id'], f['neutral']['stats'][1]['node_id'] = 2, 1
        f['neutral']['stats'].reverse()
        self.assertEqual(self.canonical(a, e), self.canonical(b, f))

    def test_zero_baseline_does_not_hide_changed_response_or_owner_or_time(self):
        a, e = self.fixture()
        for change in ('expression', 'owner', 'time', 'root', 'value', 'ledger'):
            b, f = deepcopy(a), deepcopy(e)
            if change == 'expression': b['nodes'][2]['operation'] = 'add'
            if change == 'owner': f['neutral']['stats'][0]['owner'] = 'b'
            if change == 'time': f['neutral']['stats'][0]['point']['order'] = 2
            if change == 'root': b['channels'][0]['root_node_id'] = 1
            if change == 'value': b['nodes'][0]['value'] = '1'
            if change == 'ledger': f['neutral']['ledger']['events'].append({'frame': 1})
            with self.subTest(change=change):
                self.assertNotEqual(self.canonical(a, e), self.canonical(b, f))

    def test_swapping_equal_zero_ports_is_not_renumbering(self):
        a, e = self.fixture()
        f = deepcopy(e)
        f['neutral']['stats'][0]['node_id'], f['neutral']['stats'][1]['node_id'] = 2, 1
        self.assertNotEqual(self.canonical(a, e), self.canonical(a, f))

    def test_broken_identity_binding_or_graph_is_rejected(self):
        a, e = self.fixture()
        with self.assertRaisesRegex(ValueError, 'exact member'):
            canonical_capture(json.dumps(a).encode(), json.dumps(dict(e, member_content_sha256='wrong')).encode())
        for change in ('duplicate', 'cycle', 'port'):
            b, f = deepcopy(a), deepcopy(e)
            if change == 'duplicate': b['nodes'][1]['node_id'] = 1
            if change == 'cycle': b['nodes'][2]['inputs'][0]['node_id'] = 3
            if change == 'port': f['neutral']['stats'][0]['node_id'] = 9
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.canonical(b, f)
