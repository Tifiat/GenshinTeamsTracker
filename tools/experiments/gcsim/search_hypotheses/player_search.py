"""Research-only player heuristics. None supplies a certified search bound."""

PLAYER_VARIANTS = {
    "player_safe_wide", "player_screen_pairs", "player_refine_one",
    "player_gap_half", "player_one_cycle", "player_cv", "player_rolls",
    "player_filter2", "player_filter4", "player_packages32", "player_packages96", "player_packages32_refine",
    "player_combo", "player_mean", "player_peak", "player_literal",
    "player_point32", "player_point96", "player_point32_refine", "player_point32_adaptive", "player_point96_adaptive",
}


def apply_player(root, name, replace):
    path = "internal/search/candidates.go"
    if name == "player_safe_wide":
        replace(root, "internal/allsets/neutral_coordinator.go",
                "solver.RefineCandidatesHypothesisNarrow(runCtx, c.Score.Assignment, proposal.actor, min(remaining, cfg.Search.MaxExpandedPerActor))",
                "solver.RefineCandidates(runCtx, c.Score.Assignment, proposal.actor, min(remaining, cfg.Search.MaxExpandedPerActor))")
    elif name == "player_screen_pairs":
        replace(root, path, "for n := 1; n <= 2; n++ {", "for n := 2; n <= 2; n++ {")
    elif name == "player_refine_one":
        replace(root, path, "engine.config.RecheckFrontierWidth = 2", "engine.config.RecheckFrontierWidth = 1")
    elif name == "player_gap_half":
        replace(root, path, "r.High+2*(r.High-r.Low)", "r.High+0.5*(r.High-r.Low)")
    elif name == "player_one_cycle":
        replace(root, "internal/allsets/neutral_coordinator.go",
                "func RunNeutral(ctx context.Context, index *domain.Index, base *setcontext.Context, sources *seteffects.SourceCatalog, provider setcontext.CaptureProvider, cfg CoordinatorConfig) (out CoordinatorResult, err error) {",
                "func RunNeutral(ctx context.Context, index *domain.Index, base *setcontext.Context, sources *seteffects.SourceCatalog, provider setcontext.CaptureProvider, cfg CoordinatorConfig) (out CoordinatorResult, err error) {\n cfg.Search.MaxCycles = 1 // isolated heuristic, not convergence")
    elif name == "player_cv":
        replace(root, path, "r.report.Step.GuideEvaluations++", """r.report.Step.GuideEvaluations++
    // Deliberately test the player's simple crit-mass priority. Full formula
    // still scores every proposed build; this is NOT its damage estimate.
    for i, key := range r.program.Coordinates() {
        weights[i] = 0
        if strings.HasSuffix(key, ".crit_rate") { weights[i] = 2 }
        if strings.HasSuffix(key, ".crit_damage") { weights[i] = 1 }
    }""")
    elif name == "player_rolls":
        replace(root, path, "r.report.Step.GuideEvaluations++", """r.report.Step.GuideEvaluations++
    // Equal relative amounts of every locally useful stat. Scale comes from
    // actual inventory vectors, not hardcoded game roll tables. This is a
    // deliberate useful-roll proxy, NOT the derivative's damage prediction.
    maxima := make([]float64,len(weights))
    for _, vector := range r.vectors { for j,value := range vector { maxima[j] = math.Max(maxima[j],math.Abs(value)) } }
    for j,w := range weights { if w > 0 && maxima[j] > 0 { weights[j] = 1/maxima[j] } else { weights[j] = 0 } }
""")
    elif name in {"player_filter2", "player_filter4"}:
        width = int(name[-1])
        replace(root, path, "\tr.report.Low, r.report.High = math.Inf(1), math.Inf(-1)\n\treturn r, nil",
                f"""    r.report.Low, r.report.High = math.Inf(1), math.Inf(-1)
    // Do not prune tiny inventories: they remain the exhaustive oracle.
    if len(engine.domain.Artifacts) > 120 {{
        weights, err := r.priorities(anchor[actor]); if err != nil {{ return nil, err }}
        r.hypothesisFilter(weights, {width})
    }}
    return r, nil""")
    elif name.startswith("player_packages"):
        from bonus_approx import apply_bonus_approx
        apply_bonus_approx(root, replace)
        width = int(name.removeprefix("player_packages").split("_")[0])
        replace(root, "internal/allsets/neutral_coordinator.go", "\t\t\tfor packIndex, pack := range feasible {", f"""            selectedPackages, selectErr := hypothesisPackages(runCtx, anchor, actor, feasible, sources, {width})
            if selectErr != nil {{ return out, selectErr }}
            for packIndex, pack := range selectedPackages {{""")
        if name.endswith("_refine"):
            apply_player(root, "player_refine_one", replace)
    elif name == "player_combo":
        apply_player(root, "player_screen_pairs", replace)
        apply_player(root, "player_refine_one", replace)
    elif name in {"player_mean", "player_peak"}:
        replace(root, "internal/seteffects/neutral_binding.go", "type NeutralBinding struct {",
                "type NeutralBinding struct {\n hypothesisUptimeGroups [][]int\n hypothesisUptimePrepared bool")
        replace(root, "internal/seteffects/neutral_composition.go",
                "c.raw = out.raw", "c.raw = b.hypothesisApproximate(out)")
    elif name == "player_literal":
        from bonus_approx import apply_bonus_approx
        from literal_fast import apply_literal_fast
        apply_bonus_approx(root, replace)
        apply_literal_fast(root, replace)
    elif name.startswith("player_point"):
        replace(root, "internal/setcontext/neutral.go", "type NeutralModel struct {",
                "type NeutralModel struct {\n hypothesisPointProgram *formula.ParametricProgram")
        width = int(name.removeprefix("player_point").split("_")[0])
        replace(root, "internal/allsets/neutral_coordinator.go", "\t\t\tfor packIndex, pack := range feasible {", f"""            selectedPackages, selectErr := hypothesisPointPackages(runCtx, anchor, actor, feasible, model, {width})
            if selectErr != nil {{ return out, selectErr }}
            for packIndex, pack := range selectedPackages {{""")
        if name.endswith(("_refine", "_adaptive")):
            apply_player(root, "player_refine_one", replace)
    else:
        raise ValueError(name)
