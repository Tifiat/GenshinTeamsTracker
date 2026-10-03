"""Relocation gate: compare expressions and effect ownership, not local node IDs.

Owned by repair_hit_identity's bounded deployment gate. No engine behavior or
files are changed. Each sidecar must first bind its original member bytes.
Intervention labels participate in every dependent expression fingerprint, so
equal zero-valued ports with different owners/times cannot collapse together.
"""
from copy import deepcopy
import hashlib
import json
import math
import struct


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _commute_independent_status_adds(member, effects):
    """Normalize only unobserved consecutive independent writes, never a tape.

    Active-engine AddStatus writes one owner/key and records a global order.
    A Go map (e.g. Hakushin's element ICDs) can reverse adjacent independent
    writes. All actual reads/world snapshots/events and their orders remain
    barriers; repeated keys, unknown fields and incomplete evidence stay exact.
    This is evidence comparison only, not a gameplay/consumer transformation.
    """
    neutral = effects.get('neutral') or {}
    states = neutral.get('states')
    if (not isinstance(states, list) or neutral.get('reads_complete') is not True or
            (neutral.get('world') or {}).get('complete') is not True or
            (neutral.get('ledger') or {}).get('truncated') is not False):
        return
    fields = {'order', 'frame', 'kind', 'owner', 'key', 'expiry'}
    previous = 0
    for row in states:
        if (not isinstance(row, dict) or not (fields-{'expiry'} <= set(row) <= fields) or
                any(type(row[k]) is not int for k in ('order', 'frame', 'owner')) or
                row['order'] <= previous or row['owner'] < 0 or
                row['kind'] not in ('status_add', 'status_delete') or
                (row['kind'] == 'status_add' and 'expiry' not in row) or
                not isinstance(row['key'], str) or not row['key'] or
                ('expiry' in row and type(row['expiry']) is not int)):
            return  # Invalid tape or unknown state fields cannot hide order references.
        previous = row['order']
    barriers = set()
    known_references = True

    def visit(value):
        nonlocal known_references
        if value is states:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if 'order' in key.casefold():
                    if type(item) is int and item >= 0:
                        barriers.add(item)
                    else:
                        known_references = False  # Unknown order encoding is not permission to commute.
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(member)
    visit(effects)
    if not known_references:
        return
    def eligible(row):
        return (isinstance(row, dict) and set(row) == fields and row['kind'] == 'status_add' and
                all(type(row[k]) is int for k in ('order', 'frame', 'owner', 'expiry')) and
                row['order'] > 0 and row['owner'] >= 0 and isinstance(row['key'], str) and bool(row['key']))

    start = 0
    while start < len(states):
        if not eligible(states[start]):
            start += 1
            continue
        end = start + 1
        while (end < len(states) and eligible(states[end]) and
               states[end]['frame'] == states[start]['frame'] and
               states[end]['order'] == states[end-1]['order'] + 1):
            end += 1
        batch = states[start:end]
        orders = [row['order'] for row in batch]
        distinct = {(row['owner'], row['key']) for row in batch}
        if len(batch) > 1 and len(distinct) == len(batch) and not barriers.intersection(orders):
            ordered = sorted(batch, key=lambda row: encoded({k: v for k, v in row.items() if k != 'order'}))
            states[start:end] = [dict(row, order=order) for row, order in zip(ordered, orders)]
        start = end


def captures_equal(first, second):
    """Old receipts keep strict/independent hashes; refinements are opt-in."""
    return any(first.get(key) and first[key] == second.get(key) for key in
               ('canonical_sha256', 'independent_status_sha256_v1',
                'independent_status_constant_fold_sha256_v1'))


def capture_comparison_kind(first, second, *, allow_algebraic=False):
    """Classify strongest shared evidence; algebraic needs an external exact-row gate.

    Operand commutation is mathematically valid for this pure IR, but does not
    certify bitwise floating-point equality. Callers must explicitly require
    equal finalist rows before accepting the algebraic class.
    """
    for kind, key in (('strict', 'canonical_sha256'),
                      ('status', 'independent_status_sha256_v1'),
                      ('constant', 'independent_status_constant_fold_sha256_v1'),
                      ('algebraic', 'algebraic_capture_sha256_v1')):
        if kind == 'algebraic':
            prior = ('canonical_sha256', 'independent_status_sha256_v1',
                     'independent_status_constant_fold_sha256_v1')
            if not allow_algebraic or any(not first.get(name) or not second.get(name) for name in prior):
                continue  # Never promote a standalone algebraic-only receipt.
        if first.get(key) and first[key] == second.get(key):
            return kind
    return 'unmatched'


def _float_bits(value):
    return struct.pack('>d', value).hex()


def _fold_known_constant(node, children):
    """Return (float64, value-only expression, value-free shape), or None."""
    if (type(node) is not dict or type(node.get('node_id')) is not int or
            type(node.get('inputs')) is not list):
        return None
    op = node.get('operation')
    if op == 'constant':
        if set(node) != {'node_id', 'operation', 'value', 'inputs'} or node['inputs'] or type(node['value']) is not str:
            return None
        try:
            value = float(node['value'])
        except ValueError:
            return None
        if not math.isfinite(value):
            return None
        return value, {'operation': 'constant', 'value_bits': _float_bits(value), 'inputs': []}, _float_bits_shape(op, [])
    if (op not in ('add', 'multiply', 'min', 'max') or
            set(node) != {'node_id', 'operation', 'inputs'} or
            len(children) != len(node['inputs']) or len(children) < 2):
        return None
    previous_id = 0
    for index, (edge, child) in enumerate(zip(node['inputs'], children)):
        if (type(edge) is not dict or set(edge) != {'node_id', 'relation'} or
                type(edge['node_id']) is not int or not previous_id < edge['node_id'] < node['node_id'] or
                edge['relation'] != f'input/{index:06d}' or child is None):
            return None
        previous_id = edge['node_id']
    values = [child[0] for child in children]
    if op == 'add':
        value = 0.0
        for item in values:
            value += item
    elif op == 'multiply':
        value = 1.0
        for item in values:
            value *= item
    else:
        value = values[0]
        for item in values[1:]:
            if value == 0.0 and item == 0.0:
                # Go math.Min(-0,+0)=-0 and math.Max(-0,+0)=+0.
                left_negative = math.copysign(1.0, value) < 0
                right_negative = math.copysign(1.0, item) < 0
                negative = (left_negative or right_negative) if op == 'min' else (left_negative and right_negative)
                value = -0.0 if negative else 0.0
            else:
                value = min(value, item) if op == 'min' else max(value, item)
    if not math.isfinite(value):
        return None
    return value, {'operation': 'constant', 'value_bits': _float_bits(value), 'inputs': []}, _float_bits_shape(
        op, sorted(child[2] for child in children))


def _float_bits_shape(operation, children):
    return hashlib.sha256(encoded({'operation': operation, 'inputs': children})).hexdigest()


def _commutative_flat(node):
    """Only the engine's flat pure commutative IR with positional input edges."""
    if (type(node) is not dict or set(node) != {'node_id', 'operation', 'inputs'} or
            node['operation'] not in ('add', 'multiply', 'min', 'max') or
            type(node['node_id']) is not int or type(node['inputs']) is not list or
            len(node['inputs']) < 2):
        return False
    previous = 0
    for index, edge in enumerate(node['inputs']):
        if (type(edge) is not dict or set(edge) != {'node_id', 'relation'} or
                type(edge['node_id']) is not int or not 0 < edge['node_id'] or
                not previous <= edge['node_id'] < node['node_id'] or
                edge['relation'] != f'input/{index:06d}'):
            return False
        previous = edge['node_id']
    return True


def canonical_capture(member_bytes: bytes, effects_bytes: bytes, *, independent_status_adds=False,
                      fold_unbound_constants=False, algebraic_commutative=False):
    member, effects = json.loads(member_bytes), json.loads(effects_bytes)
    if effects['member_content_sha256'] != hashlib.sha256(member_bytes).hexdigest():
        raise ValueError('Effect sidecar is not bound to its exact member')
    neutral = effects.get('neutral') or {}
    if (fold_unbound_constants or algebraic_commutative) and not (
            neutral.get('reads_complete') is True and
            (neutral.get('world') or {}).get('complete') is True and
            (neutral.get('ledger') or {}).get('truncated') is False):
        fold_unbound_constants = False
        algebraic_commutative = False
    if independent_status_adds:
        _commute_independent_status_adds(member, effects)
    nodes = member['nodes']
    by_id = {}
    for node in nodes:
        ident = node['node_id']
        if type(ident) is not int or ident <= 0 or ident in by_id:
            raise ValueError('Invalid or duplicate node identity')
        by_id[ident] = node
    annotations = {ident: [] for ident in by_id}
    groups = [('effect_inputs', effects.get('effect_inputs', [])),
              ('resistance_inputs', effects.get('resistance_inputs', [])),
              ('neutral.stats', neutral.get('stats', [])),
              ('neutral.reads', neutral.get('reads', []))]
    for kind, rows in groups:
        for row in rows:
            ident = row['node_id']
            if ident not in by_id:
                raise ValueError('Effect refers to absent node')
            annotations[ident].append({'kind': kind, 'binding': {k: v for k, v in row.items() if k != 'node_id'}})
    opaque = {row['node_id'] for row in member['opaque_boundaries']}
    labels, folded = {}, {}
    for ident in sorted(by_id):
        node = deepcopy(by_id[ident])
        commute = algebraic_commutative and _commutative_flat(node)
        if fold_unbound_constants and not annotations[ident] and ident not in opaque:
            children = [folded.get(edge.get('node_id')) if isinstance(edge, dict) else None
                        for edge in node.get('inputs', [])]
            candidate = _fold_known_constant(node, children)
            if candidate is not None:
                folded[ident] = candidate
                labels[ident] = hashlib.sha256(encoded({'expression': candidate[1], 'bindings': []})).hexdigest()
                continue
        del node['node_id']
        for edge in node.get('inputs', []):
            source = edge['node_id']
            if type(source) is not int or source not in labels:
                raise ValueError('Non-topological or missing graph input')
            edge['node_id'] = labels[source]
        if commute:
            node['inputs'].sort(key=lambda edge: edge['node_id'])
            for index, edge in enumerate(node['inputs']):
                edge['relation'] = f'input/{index:06d}'
        bound = sorted(annotations[ident], key=encoded)
        labels[ident] = hashlib.sha256(encoded({'expression': node, 'bindings': bound})).hexdigest()
    member['nodes'] = sorted(labels.values())  # Preserve all nodes and multiplicities.
    if fold_unbound_constants:
        # Value-only labels allow equal zero islands to commute at a variable
        # parent. This separate multiset retains every island's arity and shape.
        member['constant_fold_shapes_v1'] = sorted(row[2] for row in folded.values())
    for channel in member['channels']:
        channel['root_node_id'] = labels[channel['root_node_id']]
    for boundary in member['opaque_boundaries']:
        boundary['node_id'] = labels[boundary['node_id']]
    for _, rows in groups:
        for row in rows:
            row['node_id'] = labels[row['node_id']]
    # Compiler discovery order is not event order. Every owner/time/event field
    # is retained, only the unordered annotation list is sorted.
    if 'stats' in neutral:
        neutral['stats'].sort(key=encoded)
    effects['member_content_sha256'] = hashlib.sha256(encoded(member)).hexdigest()
    return {'member': member, 'effects': effects}
