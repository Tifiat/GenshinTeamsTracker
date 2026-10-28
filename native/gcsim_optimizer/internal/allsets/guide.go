package allsets

import (
	"context"
	"fmt"
	"math"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

// Guide is tied to exact set context, graph and current raw-artifact anchor.
// A new context/assignment gets a refreshed guide, not cached old set bonuses.
type Guide struct {
	contextKey, graphSHA, anchorSHA, catalogSHA string
	hints                                       map[HintKey]Hint
	Features, Unresolved                        int
	Boundaries                                  []string
}

func guideAnchor(index *domain.Index) (map[string]float64, string, error) {
	dense, e := index.DenseDeltas(index.Incumbent)
	if e != nil {
		return nil, "", e
	}
	delta := map[string]float64{}
	for i, k := range index.Coordinates {
		if dense[i] != 0 {
			delta[k] = dense[i]
		}
	}
	sha, e := contracts.CanonicalSHA256(delta)
	return delta, sha, e
}

func BuildGuide(ctx context.Context, index *domain.Index, handle *setcontext.Handle, sources *seteffects.SourceCatalog) (*Guide, error) {
	if index == nil || handle == nil || sources == nil {
		return nil, fmt.Errorf("missing guide context")
	}
	engineSHA, sourceSHA, catalogSHA := handle.SourceIdentity()
	for _, w := range index.Wearers {
		counts := map[string]int{}
		for _, s := range handle.Sets(w.WearerKey) {
			counts[s.UID] = s.Count
		}
		for _, s := range w.SelectedSets {
			if counts[s.SetUID] < s.Count {
				return nil, fmt.Errorf("guide domain set package differs from captured context")
			}
			delete(counts, s.SetUID)
		}
		for _, count := range counts {
			if count >= 2 {
				return nil, fmt.Errorf("guide domain omits captured set effect")
			}
		}
	}
	if sources.EngineSHA256 != engineSHA || sources.SourceManifestSHA256 != sourceSHA || sources.CatalogSHA256 != catalogSHA {
		return nil, fmt.Errorf("guide sources differ from captured engine/catalog")
	}
	panel, e := handle.SearchPanel()
	if e != nil {
		return nil, e
	}
	delta, anchorSHA, e := guideAnchor(index)
	if e != nil {
		return nil, e
	}
	members := []contracts.IRSeedMember{}
	inputs := []*seteffects.InputProbe{}
	resistance := []*seteffects.ResistanceProbe{}
	g := &Guide{contextKey: handle.ContextKey(), graphSHA: handle.GraphSHA256(), anchorSHA: anchorSHA, catalogSHA: catalogSHA, hints: map[HintKey]Hint{}, Boundaries: append([]string(nil), sources.Boundaries...)}
	e = handle.VisitEffectSnapshots(func(m contracts.IRSeedMember, sidecar contracts.EffectInputsOutput) error {
		if e := ctx.Err(); e != nil {
			return e
		}
		sha, e := contracts.CanonicalSHA256(m)
		if e != nil {
			return e
		}
		var p *seteffects.InputProbe
		if len(sidecar.EffectInputs) > 0 && len(sidecar.EffectInputs) <= 4096 {
			p, e = seteffects.NewInputProbe(m, sidecar.CharacterKeys, seteffects.InputEnvelope{SchemaVersion: 1, MemberSHA256: sha, Inputs: sidecar.EffectInputs})
			if e != nil {
				return e
			}
			if e = p.Reanchor(delta); e != nil {
				return e
			}
		} else {
			g.Boundaries = append(g.Boundaries, "reaction_inputs_absent_or_over_guide_limit")
		}
		var r *seteffects.ResistanceProbe
		if len(sources.Curves) > 0 && len(sidecar.ResistanceInputs) > 0 && len(sidecar.ResistanceInputs) <= 4096 {
			r, e = seteffects.NewResistanceProbe(m, sidecar.CharacterKeys, seteffects.ResistanceEnvelope{SchemaVersion: 1, MemberSHA256: sha, Inputs: sidecar.ResistanceInputs}, sources.Curves)
			if e != nil {
				return e
			}
			if e = r.Reanchor(delta); e != nil {
				return e
			}
		}
		members = append(members, m)
		inputs = append(inputs, p)
		resistance = append(resistance, r)
		return nil
	})
	if e != nil {
		return nil, e
	}
	exposure, e := seteffects.NewExposureProbe(panel, members)
	if e != nil {
		return nil, e
	}
	if e = exposure.Reanchor(delta); e != nil {
		return nil, e
	}
	for _, item := range sources.Sets {
		if e = ctx.Err(); e != nil {
			return nil, e
		}
		for _, pieces := range []int{2, 4} {
			if pieces == 4 && !item.FourPieceModeled {
				continue
			}
			for _, w := range index.Wearers {
				key := HintKey{Wearer: w.WearerKey, Set: item.Key, Pieces: pieces}
				h := Hint{SharedGroups: map[string]float64{}, Unresolved: item.Unresolved != "" || len(item.Recipes) == 0}
				for _, recipe := range item.Recipes {
					if item.Description.TierApplicability(recipe.Effect, pieces) == seteffects.Excluded {
						continue
					}
					h.Shared = h.Shared || recipe.RecipientScope == "team_iteration_member" || recipe.Effect.Kind == "resistance"
					h.NewOutput = h.NewOutput || recipe.Effect.Kind == "new_attack"
					h.Unresolved = h.Unresolved || len(recipe.Terms) == 0 || len(recipe.Unresolved) > 0
					for term := range recipe.Terms {
						gain := 0.0
						represented := true
						switch recipe.Effect.Kind {
						case "reaction_bonus":
							for _, p := range inputs {
								if p == nil {
									represented = false
									continue
								}
								f, e := p.Feature(item.Description, recipe, term, w.WearerKey, sources.Tags)
								if e != nil {
									return nil, e
								}
								if f.IncrementDPS == nil {
									represented = false
								} else {
									gain += *f.IncrementDPS / float64(len(inputs))
								}
							}
						case "resistance":
							for _, p := range resistance {
								if p == nil {
									represented = false
									continue
								}
								f, e := p.Feature(recipe, term, sources.Elements)
								if e != nil {
									return nil, e
								}
								if f.IncrementDPS == nil {
									represented = false
								} else {
									gain += *f.IncrementDPS / float64(len(resistance))
								}
							}
						default:
							f, e := exposure.Feature(item.Description, recipe, term, w.WearerKey, sources.Stats, sources.Tags)
							if e != nil {
								return nil, e
							}
							if f.RawStatProxyDPS == nil {
								represented = false
							} else {
								gain = *f.RawStatProxyDPS
							}
						}
						g.Features++
						if !represented {
							g.Unresolved++
							h.Unresolved = true
						}
						group := seteffects.SharedModifierKey(recipe)
						if group != "" {
							h.SharedGroups[group] = math.Max(h.SharedGroups[group], gain)
						} else {
							h.PeakIncrement = math.Max(h.PeakIncrement, gain)
						}
					}
				}
				g.hints[key] = h
			}
		}
	}
	return g, nil
}

func (g *Guide) Propose(ctx context.Context, index *domain.Index, handle *setcontext.Handle, catalog []domain.SetCapability, limit int) (ProposalReport, error) {
	if g == nil || index == nil || handle == nil || g.contextKey != handle.ContextKey() || g.graphSHA != handle.GraphSHA256() {
		return ProposalReport{}, fmt.Errorf("stale set guide context")
	}
	_, sha, e := guideAnchor(index)
	if e != nil {
		return ProposalReport{}, e
	}
	if sha != g.anchorSHA {
		return ProposalReport{}, fmt.Errorf("stale set guide artifact anchor")
	}
	panel, e := handle.SearchPanel()
	if e != nil {
		return ProposalReport{}, e
	}
	return Propose(ctx, index, panel, catalog, g.hints, limit)
}
