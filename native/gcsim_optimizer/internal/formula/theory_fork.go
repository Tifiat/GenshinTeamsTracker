package formula

// Theory forks mutable evaluation/cache state at a pass boundary. Arithmetic
// identities are retained; no expression is rebuilt or reassociated.
func (p *ArtifactProgram) ForkTheory() *ArtifactProgram {
	if p == nil {
		return nil
	}
	return copyArtifactScratch(p)
}
func theoryMap[K comparable, V any](source map[K]V) map[K]V {
	if source == nil {
		return nil
	}
	out := make(map[K]V, len(source))
	for k, v := range source {
		out[k] = v
	}
	return out
}
func (c *SpecializationCache) ForkTheory() *SpecializationCache {
	if c == nil {
		return nil
	}
	out := *c
	out.entries = theoryMap(c.entries)
	for k, p := range out.entries {
		out.entries[k] = p.ForkTheory()
	}
	out.order = append([]specializationKey(nil), c.order...)
	return &out
}
func (p *ParametricProgram) ForkTheory() *ParametricProgram {
	if p == nil {
		return nil
	}
	out := *p
	out.program = p.program.ForkTheory()
	// Cache keys use immutable arithmetic identity rather than copied scratch.
	if out.specializationSource == nil {
		out.specializationSource = p.program
	}
	out.input = append([]float64(nil), p.input...)
	out.damageLive = append([]bool(nil), p.damageLive...)
	out.damageOrder = append([]uint32(nil), p.damageOrder...)
	out.specializations = p.specializations.ForkTheory()
	if p.regions != nil {
		r := *p.regions
		r.mapped = append([]uint32(nil), p.regions.mapped...)
		r.changed = append([]bool(nil), p.regions.changed...)
		r.values = append([]float64(nil), p.regions.values...)
		r.liveStamp = append([]uint32(nil), p.regions.liveStamp...)
		r.exportedStamp = append([]uint32(nil), p.regions.exportedStamp...)
		r.exportMap = append([]uint32(nil), p.regions.exportMap...)
		if p.regions.arena != nil {
			b := *p.regions.arena
			b.program = p.regions.arena.program.ForkTheory()
			// The binding arena appends nodes: its backing array must be owned.
			b.program.nodes = append([]compiledNode(nil), b.program.nodes...)
			b.memo = theoryMap(b.memo)
			b.wideMemo = theoryMap(b.wideMemo)
			r.arena = &b
		}
		out.regions = &r
	}
	return &out
}
