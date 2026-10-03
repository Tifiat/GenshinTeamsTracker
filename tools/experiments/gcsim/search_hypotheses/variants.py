"""Guarded source-copy patches, NOT imported by any product module."""


def apply_variant(root, name, replace):
    from player_search import PLAYER_VARIANTS, apply_player
    if name in PLAYER_VARIANTS:
        apply_variant(root, "amount_plan", replace)
        apply_player(root, name, replace)
    elif name == "amount_plan":
        apply_variant(root, "effect_families", replace)
        from amount_plan import apply_amount_plan
        apply_amount_plan(root, replace)
    elif name == "effect_families":
        apply_variant(root, "mixed_sparse", replace)
        from effect_families import apply_families
        apply_families(root, replace)
    elif name == "mixed_sparse":
        apply_variant(root, "combined_preparation", replace)
        from mixed_inputs import apply_mixed
        apply_mixed(root, replace)
    elif name in {"inventory_views", "prepared_replay", "region_binding", "region_dense", "combined_preparation"}:
        # Every new preparation experiment shares the SAME previously measured
        # narrow/reuse search policy. Compare against combined_narrow_reuse,
        # not the older installed frontier, to attribute preparation costs.
        apply_variant(root, "combined_narrow_reuse", replace)
        parts = ("inventory_views", "prepared_replay", "region_binding") if name == "combined_preparation" else (("region_binding",) if name == "region_dense" else (name,))
        for part in parts:
            if part == "region_binding":
                replace(root, "internal/formula/parametric_program.go", "type ParametricProgram struct {",
                        "type ParametricProgram struct {\n\thypothesisRegions *hypothesisRegionBinder\n\thypothesisRegionStats HypothesisRegionStats")
                replace(root, "internal/setcontext/neutral_program_cache.go", "m.prepared.BindConstantEffects(ordered)", "m.prepared.BindConstantEffectsRegions(ordered)")
                replace(root, "internal/setcontext/neutral.go", "Requests, Unavailable                         int", "Requests, Unavailable                         int\n\tRegionReuse formula.HypothesisRegionStats")
                replace(root, "internal/setcontext/neutral.go", "stats := m.stats", "stats := m.stats\n\tstats.RegionReuse = m.prepared.HypothesisRegionsStats()")
            else:
                from preparation import apply_preparation
                apply_preparation(root, part, replace)
    elif name == "combined_narrow_reuse":
        for part in ("wide_program_cache", "context_dispatch_memo", "narrow_refine"):
            apply_variant(root, part, replace)
    elif name == "combined_exact_reuse":
        for part in ("wide_program_cache", "context_dispatch_memo"):
            apply_variant(root, part, replace)
    elif name == "context_dispatch_memo":
        path = "internal/setcontext/neutral.go"
        replace(root, path, "type NeutralModel struct {", "type hypothesisDispatch struct { key [32]byte; uncertainty []string }\n\ntype NeutralModel struct {\n\ttargetPrograms map[string]hypothesisDispatch")
        replace(root, path, "Requests, Unavailable                         int", "Requests, Unavailable                         int\n\tDispatchHits int")
        replace(root, path, "m.stats.Requests++", """m.stats.Requests++
	if known, ok := m.targetPrograms[target.key]; ok {
		if program := m.programCache[known.key]; program != nil {
			m.stats.DispatchHits++
			return m.hypothesisView(target, program, known.uncertainty)
		}
	}""")
        replace(root, path, "\tstart = time.Now()\n\tpanel, err := m.panel.ParametricView(program.WithSpecializationCache(m.specializations), effects.Uncertainty)", """
	for key, cached := range m.programCache {
		if cached == program {
			if m.targetPrograms == nil || len(m.targetPrograms) >= 8192 { m.targetPrograms = map[string]hypothesisDispatch{} }
			m.targetPrograms[target.key] = hypothesisDispatch{key, append([]string(nil), effects.Uncertainty...)}
			break
		}
	}
	return m.hypothesisView(target, program, effects.Uncertainty)
}

func (m *NeutralModel) hypothesisView(target *Context, program *formula.ParametricProgram, uncertainty []string) (*Handle, []string, error) {
	start := time.Now()
	panel, err := m.panel.ParametricView(program.WithSpecializationCache(m.specializations), uncertainty)""")
    elif name == "shared_source_accounting":
        path = "internal/formula/specialization_cache.go"
        replace(root, path, "entries                     map[specializationKey]*ArtifactProgram", "entries                     map[specializationKey]*ArtifactProgram\n\tsourceRefs map[*ArtifactProgram]int")
        replace(root, path, "entries: map[specializationKey]*ArtifactProgram{},", "entries: map[specializationKey]*ArtifactProgram{}, sourceRefs: map[*ArtifactProgram]int{},")
        replace(root, path, "cost := p.NodeCount() + key.source.NodeCount()", "if p.NodeCount() + key.source.NodeCount() > c.maxNodes { return }\n\tcost := p.NodeCount()\n\tif c.sourceRefs[key.source] == 0 { cost += key.source.NodeCount() }")
        replace(root, path, "c.nodes -= c.entries[old].NodeCount() + old.source.NodeCount()", """c.nodes -= c.entries[old].NodeCount()
		c.sourceRefs[old.source]--
		if c.sourceRefs[old.source] == 0 {
			c.nodes -= old.source.NodeCount()
			delete(c.sourceRefs, old.source)
		}
		cost = p.NodeCount()
		if c.sourceRefs[key.source] == 0 { cost += key.source.NodeCount() }""")
        replace(root, path, "c.nodes += cost", "c.nodes += cost\n\tc.sourceRefs[key.source]++")
    elif name == "wide_program_cache":
        path = "internal/setcontext/neutral_program_cache.go"
        replace(root, path, "const neutralProgramEntries = 64", "const neutralProgramEntries = 256")
        replace(root, path, "const neutralProgramNodes = 128000", "const neutralProgramNodes = 1024000")
    elif name == "linear_freeze":
        replace(root, "internal/setcontext/neutral_program_cache.go", "m.prepared.BindConstantEffects(ordered)", "m.prepared.BindConstantEffectsHypothesis(ordered)")
    elif name in {"lazy_constants", "grouped_constants"}:
        path = "internal/formula/parametric_program.go"
        replace(root, path, "type ParametricProgram struct {", "type ParametricProgram struct {\n\tfixedEffects []float64 // research-only immutable scalar binding")
        replace(root, path, "copy(p.input, artifacts)", "if p.fixedEffects != nil { effects = p.fixedEffects }\n\tcopy(p.input, artifacts)")
        replace(root, path, "fixed := append(append([]float64(nil), anchor...), effects...)", "if p.fixedEffects != nil { effects = p.fixedEffects }\n\tfixed := append(append([]float64(nil), anchor...), effects...)")
        replace(root, path, "for i, source := range p.program.nodes {\n\t\tn := copyNode(source)", """order := p.damageOrder
	if p.fixedEffects == nil {
		order = make([]uint32, len(p.program.nodes))
		for i := range order { order[i] = uint32(i) }
	}
	for _, i := range order {
		source := p.program.nodes[i]
		n := copyNode(source)""")
        if name == "grouped_constants":
            replace(root, path, "fixedEffects []float64 // research-only immutable scalar binding", "fixedEffects []float64 // research-only immutable scalar binding\n\thypothesisTemplates map[[32]byte]*ParametricProgram\n\thypothesisOrder [][32]byte\n\thypothesisNodes int\n\thypothesisStats HypothesisTemplateStats")
            replace(root, "internal/setcontext/neutral.go", "Requests, Unavailable                         int", "Requests, Unavailable                         int\n\tGroupedTemplates formula.HypothesisTemplateStats")
            replace(root, "internal/setcontext/neutral.go", "stats := m.stats", "stats := m.stats\n\tstats.GroupedTemplates=m.prepared.HypothesisGroupStats()")
        else:
            path = "internal/formula/constant_effects.go"
            replace(root, path, "func (p *ParametricProgram) BindConstantEffects(values []float64) (*ParametricProgram, error) {", """func (p *ParametricProgram) BindConstantEffectsHypothesis(values []float64) (*ParametricProgram, error) {
	if p == nil || len(values) != len(p.effects) { return nil, fmt.Errorf("constant vector mismatch") }
	for _, v := range values { if !isFinite(v) { return nil, fmt.Errorf("nonfinite constant") } }
	p.damageNodes()
	bound := p.WithOwnScratch()
	bound.fixedEffects = append([]float64(nil), values...)
	bound.effects = nil
	return bound, nil
}

func (p *ParametricProgram) BindConstantEffects(values []float64) (*ParametricProgram, error) {""")
        replace(root, "internal/setcontext/neutral_program_cache.go", "m.prepared.BindConstantEffects(ordered)", "m.prepared.BindConstantEffectsHypothesis(ordered)")
    elif name == "narrow_refine":
        # Screening remains complete. Only the first local refinement frontier
        # changes. This is a quality-risk hypothesis, never a certified prune.
        path = "internal/allsets/neutral_coordinator.go"
        replace(root, path,
                "result, e := solver.RefineCandidates(runCtx, c.Score.Assignment, proposal.actor, min(remaining, cfg.Search.MaxExpandedPerActor))",
                "result, e := solver.RefineCandidatesHypothesisNarrow(runCtx, c.Score.Assignment, proposal.actor, min(remaining, cfg.Search.MaxExpandedPerActor))")
        path = "internal/search/candidates.go"
        replace(root, path,
                "func (engine *Engine) RefineCandidates(ctx context.Context, anchor domain.Assignment, actor, allowance int) (CandidateReport, error) {",
                """func (engine *Engine) RefineCandidatesHypothesisNarrow(ctx context.Context, anchor domain.Assignment, actor, allowance int) (CandidateReport, error) {
	previous := engine.config.RecheckFrontierWidth
	engine.config.RecheckFrontierWidth = 2
	defer func() { engine.config.RecheckFrontierWidth = previous }()
	return engine.RefineCandidates(ctx, anchor, actor, allowance)
}

func (engine *Engine) RefineCandidates(ctx context.Context, anchor domain.Assignment, actor, allowance int) (CandidateReport, error) {""")
    else:
        raise ValueError(f"Unknown isolated hypothesis: {name}")
