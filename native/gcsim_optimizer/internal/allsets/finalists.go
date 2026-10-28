package allsets

import (
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

// FinalistRenderer adapts context-bound physical builds to the existing ordinary
// verifier. Neither formula graphs nor hint scores cross into the simulation.
func FinalistRenderer(request contracts.OptimizerRequest, base *setcontext.Context, candidates []Candidate) (finalists.CandidateRenderer, error) {
	if base == nil || base.Config() != request.Context.PreparedConfig.Text || len(candidates) == 0 {
		return nil, fmt.Errorf("missing or mismatched All Sets finalist baseline")
	}
	type item struct {
		request contracts.OptimizerRequest
		index   *domain.Index
		score   search.ScoredAssignment
	}
	items := map[domain.Assignment]item{}
	for _, c := range candidates {
		if c.Context == nil || c.Handle == nil || c.Index == nil || !base.SameFrame(c.Context) || c.Handle.ContextKey() != c.Context.Key() {
			return nil, fmt.Errorf("finalist context is outside the original run frame")
		}
		engine, source, _ := c.Handle.SourceIdentity()
		if engine != request.Engine.ArtifactSHA256 || source != request.Engine.SourceManifestSHA256 {
			return nil, fmt.Errorf("finalist engine/source differs from ordinary verifier")
		}
		if _, found := items[c.Score.Assignment]; found {
			return nil, fmt.Errorf("duplicate All Sets finalist")
		}
		if e := c.Index.ValidateAssignment(c.Score.Assignment); e != nil {
			return nil, e
		}
		req := request
		req.Context.PreparedConfig.Text = c.Context.Config()
		req.Wearers = append([]contracts.Wearer(nil), request.Wearers...)
		for actor, p := range c.Packages {
			if actor >= len(req.Wearers) || req.Wearers[actor].WearerKey != c.Index.Wearers[actor].WearerKey || p.Key() != (domain.Package{Sets: c.Index.Wearers[actor].SelectedSets}).Key() {
				return nil, fmt.Errorf("finalist wearer/package mismatch")
			}
			req.Wearers[actor].SelectedSetUID = ""
			req.Wearers[actor].SelectedSets = append([]contracts.SetRequirement(nil), p.Sets...)
		}
		items[c.Score.Assignment] = item{req, c.Index, c.Score}
	}
	return func(score search.ScoredAssignment, iterations, workers int) (finalists.RenderedConfig, error) {
		item, found := items[score.Assignment]
		if !found || score.DPS != item.score.DPS {
			return finalists.RenderedConfig{}, fmt.Errorf("unbound or modified All Sets finalist")
		}
		return finalists.RenderConfig(item.request, item.index, score.Assignment, iterations, workers)
	}, nil
}
