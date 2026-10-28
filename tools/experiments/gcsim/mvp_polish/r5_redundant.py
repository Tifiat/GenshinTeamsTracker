"""R5 native overlay over the exact accepted R4 image, never dirty native."""
from __future__ import annotations

from pathlib import Path
from . import r4_redundant as parent
from .r3_recovery import map_sha

ROOT, OUT, HERE = parent.ROOT, parent.OUT, Path(__file__).resolve().parent
R4_MAP = '0f504808a6fd57fd3fae55403d15853bc6adaeb891583c32fabdc813535c9e83'
once = parent.once


def native_images():
    images = dict(parent.native_images())
    if map_sha(images) != R4_MAP:
        raise ValueError('R5 requires the exact accepted R4 image')

    name = 'internal/formula/artifact_program.go'
    old = images[name].decode()
    # Preserve the frozen R4 arithmetic as the differential oracle in tests.
    begin = old.index('func (p *ArtifactProgram) Evaluate(')
    end = old.index('\nfunc ', begin + 5)
    legacy = old[begin:end].replace(') Evaluate(', ') evaluateR4Legacy(', 1)
    images['internal/formula/r5_legacy_evaluate_test.go'] = (
        'package formula\nimport ("fmt"; "math"; '
        '"genshinteamstracker/native/gcsim_optimizer/internal/projectionmetrics")\n'
        + legacy).encode()
    text = once(old, '''	if p == nil || len(delta) != len(p.coordinates) {
		return 0, fmt.Errorf("artifact program coordinate mismatch")
	}
	for _, v := range delta {
		if !isFinite(v) {
			return 0, fmt.Errorf("nonfinite artifact input")
		}
	}
	p.prepareDependencies()
	changed := ^uint64(0)
	if p.previousValid && p.dependencies != nil {
		changed = 0
		for i, value := range delta {
			if math.Float64bits(value) != math.Float64bits(p.previous[i]) {
				changed |= uint64(1) << uint(i)
			}
		}''', '''	if p == nil || len(delta) != len(p.coordinates) {
		return 0, fmt.Errorf("artifact program coordinate mismatch")
	}
    reusable := p.previousValid && p.dependencies != nil
    changed := ^uint64(0)
    if reusable { changed = 0 }
    // Every coordinate is checked before any reuse, including unused inputs.
    // Bit comparison preserves signed zero; no arithmetic order is changed.
    if reusable {
        for i, value := range delta {
            if !isFinite(value) { return 0, fmt.Errorf("nonfinite artifact input") }
            if math.Float64bits(value) != math.Float64bits(p.previous[i]) {
                changed |= uint64(1) << uint(i)
            }
        }
    } else {
        for _, value := range delta {
            if !isFinite(value) { return 0, fmt.Errorf("nonfinite artifact input") }
        }
    }
    p.prepareDependencies()
    if reusable {''')
    images[name] = text.encode()

    name = 'internal/formula/specialization_cache.go'
    text = images[name].decode()
    text = once(text, '''func (p *ParametricProgram) WithSpecializationCache(c *SpecializationCache) *ParametricProgram {
	view := p.WithOwnScratch()
	view.specializations = c
	return view
}''', '''func (p *ParametricProgram) WithSpecializationCache(c *SpecializationCache) *ParametricProgram {
    return p.WithSearchScratch(c, false)
}

// WithSearchScratch combines two view-only settings on one fresh scratch.
// Immutable nodes/cache may be shared; values, inputs and error state may not.
func (p *ParametricProgram) WithSearchScratch(c *SpecializationCache, uncertain bool) *ParametricProgram {
    view := p.WithOwnScratch()
    view.specializations = c
    if uncertain { view.program.unresolved = true }
    return view
}''')
    images[name] = text.encode()
    name = 'internal/evaluator/parametric_view.go'
    text = images[name].decode()
    text = once(text, 'func (panel *Panel) ParametricView(program *formula.ParametricProgram, uncertainty []string) (*Panel, error) {', '''func (panel *Panel) ParametricView(program *formula.ParametricProgram, uncertainty []string) (*Panel, error) {
    return panel.buildParametricView(program, uncertainty, false)
}

// The neutral owner needs independent scratch and uncertainty on every view.
// Apply both to the same copy; retain the complete zero-input preflight below.
func (panel *Panel) ParametricSearchView(program *formula.ParametricProgram, cache *formula.SpecializationCache, uncertainty []string) (*Panel, error) {
    if program == nil { return nil, fmt.Errorf("bound parametric view differs from neutral coordinates") }
    return panel.buildParametricView(program.WithSearchScratch(cache, len(uncertainty) > 0), uncertainty, true)
}

func (panel *Panel) buildParametricView(program *formula.ParametricProgram, uncertainty []string, uncertaintyApplied bool) (*Panel, error) {''')
    text = once(text, 'if len(uncertainty) > 0 {', 'if len(uncertainty) > 0 && !uncertaintyApplied {')
    images[name] = text.encode()
    name = 'internal/setcontext/neutral.go'
    images[name] = once(images[name].decode(),
        'm.panel.ParametricView(program.WithSpecializationCache(m.specializations), uncertainty)',
        'm.panel.ParametricSearchView(program, m.specializations, uncertainty)').encode()

    name = 'internal/engineclient/ordinary.go'
    text = images[name].decode()
    text = once(text, '"encoding/hex"', '"encoding/hex"\n "io"')
    text = once(text, '''	payload, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	digest := sha256.Sum256(payload)
	actual := hex.EncodeToString(digest[:])''', '''    file, err := os.Open(path)
    if err != nil { return err }
    defer file.Close()
    digest := sha256.New()
    if _, err = io.Copy(digest, file); err != nil { return err }
    actual := hex.EncodeToString(digest.Sum(nil))''')
    images[name] = text.encode()
    for package, names in {
        'formula': ('r5_evaluate_test.go', 'r5_saved_costs_test.go'),
        'evaluator': ('r5_view_test.go',),
        'engineclient': ('r5_stream_hash_test.go', 'r5_hash_costs_test.go'),
    }.items():
        for name in names:
            images[f'internal/{package}/{name}'] = (HERE / name).read_bytes()
    return images
