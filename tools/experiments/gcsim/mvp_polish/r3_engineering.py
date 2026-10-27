"""Isolated R3 overlay over the independently recoverable exact R2 module."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'docs/optimizer-evidence/2026-10-27-engineering-efficiency'
R2_MAP = '5091c1ca4365c894b93db7685dc3e0d6905bdb226c1772b8cd06ab1fd0c64d14'
R2_ARCHIVE = '56123cc8a4eac0af90e434553a1624e0aa226c13cfb4797589b9346476418924'


def once(text, old, new):
    if text.count(old) == 0 and '\n' in old:
        for newline in ('\r\n', '\r\r\n'):
            variant = old.replace('\n', newline)
            if text.count(variant) == 1:
                return text.replace(variant, new.replace('\n', newline), 1)
    if text.count(old) != 1:
        raise ValueError('R3 source seam differs: ' + old[:90])
    return text.replace(old, new, 1)


def frozen_images():
    path = OUT / 'r2-native-source-v1.zip'
    if not path.exists():
        # Durable recovery uses a committed baseline plus a readable exact delta;
        # the generated zip is only a local shortcut, never the sole source.
        from . import r3_recovery
        images = r3_recovery.recover_images()
        return checked_r2_images(images)
    if hashlib.sha256(path.read_bytes()).hexdigest() != R2_ARCHIVE:
        raise ValueError('R2 archive identity differs')
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names) or any(Path(n).is_absolute() or '..' in Path(n).parts for n in names):
            raise ValueError('unsafe source archive')
        images = {name: archive.read(name) for name in names}
    return checked_r2_images(images)


def checked_r2_images(images):
    mapping = {k: hashlib.sha256(v).hexdigest() for k, v in sorted(images.items())}
    if hashlib.sha256(json.dumps(mapping, sort_keys=True, separators=(',', ':')).encode()).hexdigest() != R2_MAP:
        raise ValueError('R2 source map differs')
    return images


def native_images():
    images = frozen_images()
    frozen_gradient = images['internal/formula/program_gradient.go'].decode()
    name = 'internal/setcontext/engine_provider.go'
    text = images[name].decode()
    text = once(text, '"strings"', '"strings"\n "sync"')
    text = once(text, 'type EngineProvider struct {', 'type EngineProvider struct {\n r3Mu sync.Mutex')
    text = once(text, 'if p == nil || p.closed || c == nil {',
                'if p == nil { return out, fmt.Errorf("capture provider unavailable") }; p.r3Mu.Lock(); defer p.r3Mu.Unlock()\n if p.closed || c == nil {')
    text = once(text, '\tfor _, seed := range c.binding.Seeds {',
                '\tif os.Getenv("GTT_R3_PARALLEL_CAPTURE")=="1" { return p.r3Capture(ctx,c,dir,out) }\n\tfor _, seed := range c.binding.Seeds {')
    text = once(text, 'func (p *EngineProvider) Timings() []CaptureTiming { return append([]CaptureTiming(nil), p.timings...) }',
                'func (p *EngineProvider) Timings() []CaptureTiming { p.r3Mu.Lock(); defer p.r3Mu.Unlock(); return append([]CaptureTiming(nil), p.timings...) }')
    text = once(text, '\tp.closed = true', '\tp.r3Mu.Lock(); defer p.r3Mu.Unlock()\n\tp.closed = true')
    images[name] = text.encode()
    images['internal/setcontext/r3_capture.go'] = (HERE / 'r3_capture.go').read_bytes()

    name = 'internal/formula/artifact_program.go'
    text = images[name].decode()
    text = once(text, 'type ArtifactProgram struct {',
                'type ArtifactProgram struct {\n r3Adjoints []float64 // sequential evaluation owner only; never copied/shared')
    images[name] = text.encode()
    name = 'internal/formula/program_gradient.go'
    text = images[name].decode()
    text = once(text, 'adjoint := make([]float64, len(p.nodes))', 'adjoint := p.r3AdjointScratch()')
    images[name] = text.encode()
    images['internal/formula/r3_adjoint.go'] = (HERE / 'r3_adjoint.go').read_bytes()
    images['internal/formula/r3_gradient_reference_test.go'] = once(
        frozen_gradient, 'func (p *ArtifactProgram) ValueGradient(',
        'func (p *ArtifactProgram) r3FrozenValueGradient(').encode()
    name = 'internal/formula/specialization_cache.go'
    text = once(images[name].decode(), 'copy := *p', 'copy := *p\n copy.r3Adjoints = nil')
    images[name] = text.encode()

    name = 'internal/setcontext/neutral.go'
    text = images[name].decode()
    text = once(text, 'type NeutralModel struct {',
                'type NeutralModel struct {\n r3ProgramKeys map[*formula.ParametricProgram][32]byte')
    old = '''\tfor key, cached := range m.programCache {
\t\tif cached == program {
\t\t\tif m.targetPrograms == nil || len(m.targetPrograms) >= 8192 {
\t\t\t\tm.targetPrograms = map[string]contextDispatch{}
\t\t\t}
\t\t\tm.targetPrograms[target.key] = contextDispatch{key, append([]string(nil), effects.Uncertainty...)}
\t\t\tbreak
\t\t}
\t}'''
    new = '''\tif key, found := m.r3ProgramKey(program); found {
        if m.targetPrograms == nil || len(m.targetPrograms) >= 8192 {
            m.targetPrograms = map[string]contextDispatch{}
        }
        m.targetPrograms[target.key] = contextDispatch{key, append([]string(nil), effects.Uncertainty...)}
    }'''
    text = once(text, old, new)
    images[name] = text.encode()
    name = 'internal/setcontext/neutral_program_cache.go'
    text = images[name].decode()
    old = '''\tvar key [32]byte
\tfound := false
\tfor candidateKey, cached := range m.programCache {
\t\tif cached == program {
\t\t\tkey, found = candidateKey, true
\t\t\tbreak
\t\t}
\t}'''
    text = once(text, old, '\tkey, found := m.r3ProgramKey(program)')
    text = once(text, '\t\tdelete(m.programCache, old)', '\t\tm.r3ForgetProgramKey(old, m.programCache[old])\n\t\tdelete(m.programCache, old)')
    text = once(text, '\tm.programCache[key] = program', '\tm.programCache[key] = program\n\tm.r3RememberProgramKey(key,program)')
    images[name] = text.encode()
    name = 'internal/setcontext/theory_model.go'
    text = once(images[name].decode(), 'out := *m', 'out := *m\n out.r3ProgramKeys = nil')
    images[name] = text.encode()
    images['internal/setcontext/r3_program_identity.go'] = (HERE / 'r3_program_identity.go').read_bytes()
    name = 'internal/contracts/canonical.go'
    images[name] = once(images[name].decode(), 'typedCanonical, err := CanonicalJSON(value)',
                        'typedCanonical, err := r3CanonicalDecodedContract(value)').encode()
    images['internal/contracts/r3_typed_json.go'] = (HERE / 'r3_typed_json.go').read_bytes()
    legacy_parity = (HERE / 'seed_member_typed_canonical_parity_test.go').read_bytes()
    # Preserve the reviewed synthetic differential/schema tests as an overlay;
    # this does not invoke their historical, unbound measurement recipe.
    images['internal/contracts/r3_typed_json_parity_test.go'] = legacy_parity
    name = 'internal/contracts/validate_outputs.go'
    text = images[name].decode()
    start = text.index('func (node IRNode) validate(')
    end = text.find('\nfunc ', start + 5)
    reference = text[start:end if end >= 0 else len(text)].replace('\r', '')
    reference = once(reference, 'func (node IRNode) validate(', 'func (node IRNode) r3FrozenNodeValidate(')
    images['internal/contracts/r3_node_validator_reference_test.go'] = ('package contracts\nimport "fmt"\n' + reference).encode()
    old = '''\tallowed := map[string]bool{
\t\t"constant": true, "artifact_stat": true, "add": true, "multiply": true,
\t\t"min": true, "max": true, "power": true, "opaque_frozen": true,
\t\t"select_lt": true,
\t}
\tif !allowed[node.Operation] {'''
    images[name] = once(text, old, '\tif !r3OperationSupported(node.Operation) {').encode()
    images['internal/contracts/r3_operation.go'] = (HERE / 'r3_operation.go').read_bytes()
    for package, leaf in [('setcontext', 'r3_capture_test.go'), ('setcontext', 'r3_program_identity_test.go'),
                          ('formula', 'r3_adjoint_test.go'), ('contracts', 'r3_codec_cost_test.go'),
                          ('engineclient', 'r3_ready_cost_test.go'), ('formula', 'r3_gradient_cost_test.go'),
                          ('engineclient', 'r3_cpu_windows_test.go'), ('engineclient', 'r3_cpu_other_test.go'),
                          ('contracts', 'r3_operation_test.go')]:
        images['internal/' + package + '/' + leaf] = (HERE / leaf).read_bytes()
    return images
