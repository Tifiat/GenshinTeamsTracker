package allsets

import (
	"fmt"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

// Discovery classifies source opportunities but assigns NO hypothetical DPS to
// a bonus. Tier checks alone do not establish activation, uptime or stacking.
// Every changed package, including a schedule-changing one, needs a fresh team
// capture before its formula can be compared or its inventory bound can prune.
func BuildDiscoveryGuide(index *domain.Index, handle *setcontext.Handle, sources *seteffects.SourceCatalog) (*Guide, error) {
	if index == nil || handle == nil || sources == nil {
		return nil, fmt.Errorf("missing discovery context")
	}
	engine, source, catalog := handle.SourceIdentity()
	if engine != sources.EngineSHA256 || source != sources.SourceManifestSHA256 || catalog != sources.CatalogSHA256 {
		return nil, fmt.Errorf("discovery sources differ from captured engine")
	}
	_, anchor, e := guideAnchor(index)
	if e != nil {
		return nil, e
	}
	g := &Guide{contextKey: handle.ContextKey(), graphSHA: handle.GraphSHA256(), anchorSHA: anchor, catalogSHA: catalog, hints: map[HintKey]Hint{}, Boundaries: append([]string(nil), sources.Boundaries...)}
	for _, set := range sources.Sets {
		for _, count := range []int{2, 4} {
			if count == 4 && !set.FourPieceModeled {
				continue
			}
			h := Hint{Unresolved: true, SharedGroups: map[string]float64{}}
			for _, r := range set.Recipes {
				if set.Description.TierApplicability(r.Effect, count) == seteffects.Excluded {
					continue
				}
				h.Shared = h.Shared || r.RecipientScope == "team_iteration_member" || r.Effect.Kind == "resistance"
				h.NewOutput = h.NewOutput || r.Effect.Kind == "new_attack"
			}
			for _, w := range index.Wearers {
				g.hints[HintKey{w.WearerKey, set.Key, count}] = h
			}
		}
	}
	g.Boundaries = append(g.Boundaries, "uncaptured_bonus_activation_requires_fresh_context")
	return g, nil
}
