package theoryverify

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
)

// ArtifactStatTotals is the same max-roll/main projection used for rendering
// and for the legal displacement of a local response proposal.
func ArtifactStatTotals(witness alloc.State) ([4]map[string]float64, error) {
	var stats [4]map[string]float64
	if err := alloc.ValidateFull45(witness); err != nil {
		return stats, err
	}
	keys, values, mains := alloc.StatKeys(), alloc.StatValues(), alloc.MainValues()
	rolls := witness.Rolls()
	for actor := range stats {
		stats[actor] = make(map[string]float64)
		for _, main := range witness.Mains[actor] {
			stats[actor][main] += mains[main]
		}
		for coordinate, units := range rolls[actor] {
			stats[actor][keys[coordinate]] += units * values[coordinate]
		}
	}
	return stats, nil
}

// Renderer starts from the original ordinary frame, never the neutral capture
// config. Whole concrete packages replace old set rows at their declaration
// position. All artifact totals replace the baseline row exactly once.
func Renderer(request contracts.OptimizerRequest, catalogSHA string) (finalists.FullBuildRenderer, error) {
	if len(request.Wearers) != 4 || !request.Legality.TheorySearch || len(request.Artifacts) != 0 {
		return nil, fmt.Errorf("Theory ordinary renderer requires the original virtual request")
	}
	frameSHA, err := finalists.FullBuildFrameSHA256(request)
	if err != nil {
		return nil, err
	}
	requestSHA, err := contracts.CanonicalSHA256(request)
	if err != nil {
		return nil, err
	}
	base, err := setcontext.New(setcontext.Binding{Engine: request.Engine, CatalogSHA256: catalogSHA, ReferenceStatsSHA256: requestSHA, Seeds: request.Stochastic.Seeds}, request.Context.PreparedConfig.Text)
	if err != nil {
		return nil, err
	}
	var wearers [4]string
	for actor, wearer := range request.Wearers {
		wearers[actor] = wearer.WearerKey
	}
	return func(candidate finalists.FullBuildCandidate, iterations, workers int) (finalists.RenderedConfig, error) {
		if candidate.FrameSHA256 != frameSHA {
			return finalists.RenderedConfig{}, fmt.Errorf("Theory ordinary candidate belongs to a different frame")
		}
		var identity BuildIdentity
		decoder := json.NewDecoder(bytes.NewReader(candidate.BuildIdentity))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&identity); err != nil {
			return finalists.RenderedConfig{}, err
		}
		var trailing any
		if err := decoder.Decode(&trailing); err != io.EOF || identity.Kind != BuildKind {
			return finalists.RenderedConfig{}, fmt.Errorf("invalid Theory full-build identity")
		}
		if err := alloc.ValidateFull45(identity.Witness45); err != nil {
			return finalists.RenderedConfig{}, err
		}
		packages, err := validatePackages(identity.Packages, wearers)
		if err != nil {
			return finalists.RenderedConfig{}, err
		}
		changes := make(map[string][]setcontext.Set, 4)
		stats, err := ArtifactStatTotals(identity.Witness45)
		if err != nil {
			return finalists.RenderedConfig{}, err
		}
		for actor, wearer := range wearers {
			changes[wearer] = []setcontext.Set{}
			for _, set := range packages[actor].Sets {
				changes[wearer] = append(changes[wearer], setcontext.Set{UID: set.SetUID, Count: set.Count})
			}
		}
		replaced, err := base.Replace(changes)
		if err != nil {
			return finalists.RenderedConfig{}, err
		}
		ordinary := request
		ordinary.Context.PreparedConfig.Text = replaced.Config()
		return finalists.RenderArtifactStatTotals(ordinary, stats, iterations, workers)
	}, nil
}
