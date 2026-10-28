"""R4: scoped redundant-work removal over exact preserved R3, never dirty native."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from . import r3_engineering as parent

ROOT, HERE = parent.ROOT, Path(__file__).resolve().parent
OUT = parent.OUT
R3_MAP = '3401a0e41238cc6fb85b9f74121f89e2c7cd062c6aebb2a717fc1969a9db9672'
once = parent.once


def native_images(*, region_candidate=False):
    images = parent.native_images()
    mapping = {k: hashlib.sha256(v).hexdigest() for k, v in sorted(images.items())}
    if hashlib.sha256(json.dumps(mapping, sort_keys=True, separators=(',', ':')).encode()).hexdigest() != R3_MAP:
        raise ValueError('R4 requires exact preserved R3')
    images = dict(images)

    name = 'internal/engineclient/effect_inputs.go'
    text = images[name].decode()
    signature = 'func decodeEffectInputs(payload, memberBytes []byte, member contracts.IRSeedMember, configSHA, sourceSHA string) (*contracts.EffectInputsOutput, error) {'
    replacement = signature + '''
 return decodeEffectInputsWithMemberSHA(payload, contracts.BytesSHA256(memberBytes), member, configSHA, sourceSHA)
}

// Only runCompact passes this digest, synchronously, from its own unmodified
// payload. The byte-taking boundary above always hashes arbitrary inputs itself.
func decodeEffectInputsWithMemberSHA(payload []byte, memberSHA string, member contracts.IRSeedMember, configSHA, sourceSHA string) (*contracts.EffectInputsOutput, error) {'''
    text = once(text, signature, replacement)
    text = once(text, 'out.MemberContentSHA256 != contracts.TextSHA256(string(memberBytes))',
                'out.MemberContentSHA256 != memberSHA')
    images[name] = text.encode()
    name = 'internal/engineclient/compact.go'
    text = images[name].decode()
    text = once(text, '\tif includeEffects {\r', '\tvar memberSHA string\n\tif includeEffects {\r') if '\tif includeEffects {\r' in text else once(text, '\tif includeEffects {', '\tvar memberSHA string\n\tif includeEffects {')
    old = 'out.Effects, err = decodeEffectInputs(effectsPayload, payload, out.Member, out.ConfigSHA256, bound.sourceManifestSHA256)'
    text = once(text, old, '''if r4OwnedDigest {
            memberSHA = contracts.BytesSHA256(payload)
            out.Effects, err = decodeEffectInputsWithMemberSHA(effectsPayload, memberSHA, out.Member, out.ConfigSHA256, bound.sourceManifestSHA256)
        } else { ''' + old + ' }')
    text = once(text, 'out.ResultSHA256, out.ResultPath = contracts.TextSHA256(string(payload)), resultPath',
                'if memberSHA == "" { memberSHA = contracts.BytesSHA256(payload) }\n out.ResultSHA256, out.ResultPath = memberSHA, resultPath')
    images[name] = text.encode()
    images['internal/engineclient/r4_owned_digest.go'] = (HERE / 'r4_owned_digest.go').read_bytes()

    name = 'internal/setcontext/session.go'
    text = images[name].decode()
    text = once(text, 'compiled.graphSHA, err = contracts.CanonicalSHA256(capture.Members)', '''if r4TypedPanel {
        compiled.graphSHA, err = contracts.CanonicalSeedMembersSHA256(capture.Members)
    } else { compiled.graphSHA, err = contracts.CanonicalSHA256(capture.Members) }''')
    images[name] = text.encode()
    images['internal/setcontext/r4_typed_panel.go'] = (HERE / 'r4_typed_panel.go').read_bytes()
    images['internal/contracts/r4_canonical_panel.go'] = (HERE / 'r4_canonical_panel.go').read_bytes()

    if region_candidate:
        name = 'internal/formula/region_binding.go'
        text = images[name].decode()
        reference = text.replace('\r', '')
        start = reference.index('func (p *ParametricProgram) BindConstantEffectsRegions(')
        end = reference.index('func (p *ParametricProgram) exportRegions(')
        reference = once(reference[start:end], 'func (p *ParametricProgram) BindConstantEffectsRegions(',
                         'func (p *ParametricProgram) r4FrozenBindConstantEffectsRegions(')
        images['internal/formula/r4_regions_reference_test.go'] = ('package formula\nimport("fmt";"math")\n' + reference).encode()
        text = once(text, 'type regionBinder struct {', 'type regionBinder struct {\n r4Dirty *r4RegionDirty')
        text = once(text, '\tfor _, id := range p.damageOrder {', '''\torder := p.damageOrder
        if r4DirtyRegions {
            order = p.r4RegionOrder(r, values)
            p.regionStats.Reused += uint64(len(p.damageOrder)-len(order))
        } else { r.r4Dirty = nil }
        for _, id := range order {''')
        images[name] = text.encode()
        name = 'internal/formula/theory_fork.go'
        images[name] = once(images[name].decode(), 'r := *p.regions', 'r := *p.regions\n r.r4Dirty = nil // rebuild private dirty scratch; never share mutable frontier').encode()
        images['internal/formula/r4_region_dirty.go'] = (HERE / 'r4_region_dirty.go').read_bytes()

    old_metrics = images['internal/projectionmetrics/metrics.go'].decode().replace('\r', '')
    reference = old_metrics[old_metrics.index('var mu sync.Mutex'):]
    for name in ('mu', 'enabled', 'current', 'StartCounters', 'Count', 'Begin', 'Finish'):
        reference = re.sub(r'\b' + name + r'\b', 'r4Reference' + name[0].upper() + name[1:], reference)
    images['internal/projectionmetrics/r4_reference_test.go'] = ('package projectionmetrics\nimport("sync";"time")\n' + reference).encode()
    images['internal/projectionmetrics/metrics.go'] = (HERE / 'r4_metrics.go').read_bytes()
    for package, filename in [('engineclient', 'r4_owned_digest_test.go'),
                              ('contracts', 'r4_canonical_panel_test.go'),
                              ('formula', 'r4_region_dirty_test.go'),
                              ('projectionmetrics', 'r4_metrics_test.go'),
                              ('contracts', 'r4_saved_costs_test.go'),
                              ('formula', 'r4_saved_regions_test.go'),
                              ('projectionmetrics', 'r4_saved_metrics_test.go'),
                              ('setcontext', 'r4_capture_identity_test.go')]:
        if not region_candidate and filename in ('r4_region_dirty_test.go', 'r4_saved_regions_test.go'):
            continue
        path = HERE / filename
        if path.exists():
            images['internal/' + package + '/' + filename] = path.read_bytes()
    return images
