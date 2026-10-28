package theoryverify

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strconv"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
	"genshinteamstracker/native/gcsim_optimizer/internal/searchcontrol"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
)

// ResponseDirection is a dependency-neutral projection of the common
// supportimpact.Direction wire shape. The root probe owner supplies it; this
// adapter neither probes nor computes a DPS correction from a derivative.
type ResponseDirection struct {
	Binding               ResponseBinding   `json:"binding"`
	Owner                 string            `json:"owner"`
	Stat                  string            `json:"stat"`
	Amount                float64           `json:"amount"`
	MeanDPSChange         float64           `json:"mean_dps_change"`
	MinimumDPSChange      float64           `json:"minimum_dps_change"`
	MaximumDPSChange      float64           `json:"maximum_dps_change"`
	MeanOtherDPSChange    float64           `json:"mean_other_dps_change"`
	MinimumOtherDPSChange float64           `json:"minimum_other_dps_change"`
	CrossAncestryMissing  bool              `json:"cross_ancestry_missing,omitempty"`
	SeedDPSChanges        map[int64]float64 `json:"seed_dps_changes"`
	Status                string            `json:"status"`
	ConfigSHA256          string            `json:"config_sha256"`
	ResultSHA256BySeed    map[int64]string  `json:"result_sha256_by_seed"`
}

// ResponseBinding projects the common engineclient.StatResponseBinding. It is
// compared exactly, including request and patch; no probe implementation lives
// here and no response is transferred to another set/stat anchor.
type ResponseBinding struct {
	AnchorConfigSHA256         string `json:"anchor_config_sha256"`
	RequestSHA256              string `json:"request_sha256"`
	EngineArtifactSHA256       string `json:"engine_artifact_sha256"`
	EngineBindingSHA256        string `json:"engine_binding_sha256"`
	EngineSourceManifestSHA256 string `json:"engine_source_manifest_sha256"`
	EnginePatchManifestSHA256  string `json:"engine_patch_manifest_sha256"`
}

type ResponseDiagnostic struct {
	Owner  string
	Stat   string
	Reason string
}

type ResponseProposals struct {
	Candidates  []Candidate
	Diagnostics []ResponseDiagnostic
}

// This bounds model evaluations/proposal storage, not ordinary calls. The
// common 128-call/two-seed panel has at most 63 directions: one complete joint
// proposal per direction fits before any individual/local alternatives.
const ResponseProposalLimit = 64

type legalResponseDirection struct {
	direction  ResponseDirection
	actor      int
	coordinate int
	origin     finalists.FullBuildOrigin
}

// jointResponseWitness chooses all supported mains together and uses the
// existing allocator for legal incidence and all 25 upgrade units. It moves
// each full piece's upgrades to the primary direction where it is eligible,
// then to the strongest eligible companion measured direction;
// pieces with no such coordinate keep Seed's complete balanced allocation.
// The guide is proposal evidence only; it is never passed off as formula DPS.
func jointResponseWitness(base alloc.State, primary legalResponseDirection, peers []legalResponseDirection) alloc.State {
	actor := primary.actor
	mains := base.Mains
	choices := alloc.MainChoices()
	mainValues := alloc.MainValues()
	reduced := map[string]bool{}
	for _, peer := range peers {
		if peer.direction.Amount < 0 {
			reduced[peer.direction.Stat] = true
		}
	}
	for slot, options := range choices {
		best := ""
		for _, option := range options {
			if primary.direction.Amount > 0 && option == primary.direction.Stat {
				best = option
			}
		}
		companion, companionGuide := "", 0.0
		for _, peer := range peers {
			if peer.direction.Amount <= 0 {
				continue
			}
			for _, option := range options {
				if option != peer.direction.Stat || (best != "" && (primary.coordinate < 0 || peer.coordinate >= 0)) {
					continue
				}
				guide := peer.direction.MinimumOtherDPSChange * mainValues[option] / peer.direction.Amount
				if finite(guide) && guide > 0 && (companion == "" || guide > companionGuide || (guide == companionGuide && option < companion)) {
					companion, companionGuide = option, guide
				}
			}
		}
		if companion != "" {
			best = companion
		}
		if best != "" {
			mains[actor][slot] = best
		} else if reduced[mains[actor][slot]] {
			for _, option := range options {
				if !reduced[option] {
					mains[actor][slot] = option
					break
				}
			}
		}
	}
	var guide [4][10]float64
	for coordinate := range guide[actor] {
		guide[actor][coordinate] = 1e-9
	}
	// Per-roll evidence makes unlike stat units comparable for this local guide.
	// Normalize to the largest magnitude before asking Seed to choose lines.
	values := alloc.StatValues()
	weights := [10]float64{}
	for _, peer := range peers {
		if peer.coordinate < 0 {
			continue
		}
		weight := 1.0
		if peer.direction.MinimumOtherDPSChange > 0 && finite(peer.direction.MinimumOtherDPSChange) {
			weight = peer.direction.MinimumOtherDPSChange * (values[peer.coordinate] / peer.direction.Amount)
		} else if peer.direction.Amount < 0 {
			weight = -1
		}
		if finite(weight) {
			weights[peer.coordinate] = weight
		}
	}
	maximum := 0.0
	for _, weight := range weights {
		magnitude := weight
		if magnitude < 0 {
			magnitude = -magnitude
		}
		if magnitude > maximum {
			maximum = magnitude
		}
	}
	if maximum == 0 {
		maximum = 1
	}
	for coordinate, weight := range weights {
		if weight != 0 {
			guide[actor][coordinate] = weight / maximum
		}
	}
	// A competing measured coordinate must not crowd the primary direction out
	// of Seed's four legal lines. This also keeps one complete witness available
	// for every direction before the shared deterministic proposal cap is spent.
	if primary.coordinate >= 0 {
		guide[actor][primary.coordinate] = 2
		if primary.direction.Amount < 0 {
			guide[actor][primary.coordinate] = -2
		}
	}
	seeded := alloc.Seed(mains, guide, 0, 45)
	for slot, lines := range seeded.Lines[actor] {
		best := -1
		for line, coordinate := range lines {
			if weights[coordinate] > 0 && (best < 0 || guide[actor][coordinate] > guide[actor][lines[best]]) {
				best = line
			}
		}
		if best >= 0 {
			seeded.Upgrades[actor][slot] = [4]float64{}
			seeded.Upgrades[actor][slot][best] = 5
		}
	}
	state := base
	state.Mains[actor], state.Lines[actor], state.Upgrades[actor] = seeded.Mains[actor], seeded.Lines[actor], seeded.Upgrades[actor]
	return state
}

// ResponseAnchor is prepared without engine calls. Its private seal prevents
// an altered anchor descriptor from being reused for a different complete
// build. The common response-check owner uses Config.Text as its exact anchor.
type ResponseAnchor struct {
	CandidateSHA256      string
	FrameSHA256          string
	EngineArtifactSHA256 string
	SourceManifestSHA256 string
	Config               finalists.RenderedConfig
	Binding              ResponseBinding
	seal                 string
}

// ResponsePanel carries the common probe owner's explicit anchor/engine
// binding. Directions alone do not authorize cross-context proposal reuse.
type ResponsePanel struct {
	AnchorCandidateSHA256 string
	AnchorConfigSHA256    string
	EngineArtifactSHA256  string
	SourceManifestSHA256  string
	Directions            []ResponseDirection
	Binding               ResponseBinding
	Status                string
}

func responseSeal(anchor ResponseAnchor) (string, error) {
	return contracts.CanonicalSHA256(map[string]any{"candidate": anchor.CandidateSHA256, "frame": anchor.FrameSHA256,
		"config": anchor.Config.SHA256, "engine": anchor.EngineArtifactSHA256, "source": anchor.SourceManifestSHA256, "binding": anchor.Binding})
}

func NewResponseAnchor(request contracts.OptimizerRequest, catalogSHA string, base Candidate) (ResponseAnchor, error) {
	var anchor ResponseAnchor
	render, err := Renderer(request, catalogSHA)
	if err != nil {
		return anchor, err
	}
	config, err := render(base.Build, 1, 1)
	if err != nil {
		return anchor, err
	}
	key, err := finalists.FullBuildCandidateSHA256(base.Build.FrameSHA256, base.Build.BuildIdentity)
	if err != nil || key != base.Key {
		return anchor, fmt.Errorf("response anchor candidate identity mismatch")
	}
	anchor = ResponseAnchor{CandidateSHA256: key, FrameSHA256: base.Build.FrameSHA256,
		EngineArtifactSHA256: request.Engine.ArtifactSHA256, SourceManifestSHA256: request.Engine.SourceManifestSHA256, Config: config}
	requestSHA, err := contracts.CanonicalSHA256(request)
	if err != nil {
		return ResponseAnchor{}, err
	}
	anchor.Binding = ResponseBinding{AnchorConfigSHA256: config.SHA256, RequestSHA256: requestSHA,
		EngineArtifactSHA256: request.Engine.ArtifactSHA256, EngineBindingSHA256: request.Engine.BindingSHA256,
		EngineSourceManifestSHA256: request.Engine.SourceManifestSHA256, EnginePatchManifestSHA256: request.Engine.PatchManifestSHA256}
	anchor.seal, err = responseSeal(anchor)
	return anchor, err
}

// ProposeResponseDirections makes bounded legal alternatives of a concrete
// build. Its scores are evaluations of the ORIGINAL formula objective. Local
// paired response values are only proposal evidence, never verified DPS or a
// hard bound/cap. Zero/mixed/unavailable directions stay diagnosed.
func ProposeResponseDirections(base Candidate, anchor ResponseAnchor, panel ResponsePanel, objective alloc.Objective) (ResponseProposals, error) {
	out := ResponseProposals{Candidates: []Candidate{}, Diagnostics: []ResponseDiagnostic{}}
	if objective == nil || len(base.Row.Aliases) != 1 {
		return out, fmt.Errorf("response proposals require a complete build and its original objective")
	}
	normalized, err := NewCandidate(base.Build.FrameSHA256, base.Row.Witness45, base.Row.Aliases[0], base.Build.FormulaDPS, base.Build.Origins, base.Row.RefinementLevel)
	if err != nil || normalized.Key != base.Key {
		return out, fmt.Errorf("response base row differs from its complete build identity")
	}
	seal, err := responseSeal(anchor)
	if err != nil || anchor.seal == "" || seal != anchor.seal || contracts.TextSHA256(anchor.Config.Text) != anchor.Config.SHA256 ||
		anchor.CandidateSHA256 != base.Key || anchor.FrameSHA256 != base.Build.FrameSHA256 ||
		panel.AnchorCandidateSHA256 != anchor.CandidateSHA256 || panel.AnchorConfigSHA256 != anchor.Config.SHA256 ||
		panel.EngineArtifactSHA256 != anchor.EngineArtifactSHA256 || panel.SourceManifestSHA256 != anchor.SourceManifestSHA256 || panel.Binding != anchor.Binding {
		return out, fmt.Errorf("response evidence belongs to a different exact anchor/config/engine/source")
	}
	alias := base.Row.Aliases[0]
	baseStats, err := ArtifactStatTotals(base.Row.Witness45)
	if err != nil {
		return out, err
	}
	if len(panel.Directions) > ResponseProposalLimit {
		return out, fmt.Errorf("response panel exceeds the bounded direction policy")
	}
	seen := map[alloc.State]int{base.Row.Witness45: -1}
	originKeysByState := map[alloc.State]map[string]bool{}
	keys, choices := alloc.StatKeys(), alloc.MainChoices()
	directions := append([]ResponseDirection(nil), panel.Directions...)
	sort.SliceStable(directions, func(i, j int) bool {
		if directions[i].Owner != directions[j].Owner {
			return directions[i].Owner < directions[j].Owner
		}
		if directions[i].Stat != directions[j].Stat {
			return directions[i].Stat < directions[j].Stat
		}
		return directions[i].Amount < directions[j].Amount
	})
	eligible := []legalResponseDirection{}
	type directionKey struct {
		owner, stat string
		amount      float64
	}
	seenDirections := map[directionKey]bool{}
	for _, direction := range directions {
		if direction.Binding != panel.Binding {
			return out, fmt.Errorf("response direction belongs to another request/anchor/engine/source/patch")
		}
		actor := -1
		for index, row := range alias.Packages {
			if row.WearerKey == direction.Owner {
				actor = index
			}
		}
		if actor < 0 || !finite(direction.Amount) || direction.Amount == 0 {
			return out, fmt.Errorf("response direction has invalid owner/displacement")
		}
		key := directionKey{direction.Owner, direction.Stat, direction.Amount}
		if seenDirections[key] {
			return out, fmt.Errorf("response panel repeats an owner/stat/displacement direction")
		}
		seenDirections[key] = true
		if direction.Status != "positive_on_sampled_seeds" {
			out.Diagnostics = append(out.Diagnostics, ResponseDiagnostic{direction.Owner, direction.Stat, "inconclusive_proposal_evidence"})
			continue
		}
		if len(direction.SeedDPSChanges) < 2 || len(direction.SeedDPSChanges) != len(direction.ResultSHA256BySeed) {
			return out, fmt.Errorf("response proposal is missing its paired seed evidence")
		}
		codes := []string{"support_response_proposal_only", "owner=" + direction.Owner, "stat=" + direction.Stat,
			"probe_amount=" + strconv.FormatFloat(direction.Amount, 'g', -1, 64), "probe_config_sha256=" + direction.ConfigSHA256,
			"anchor_candidate_sha256=" + anchor.CandidateSHA256, "anchor_config_sha256=" + anchor.Config.SHA256,
			"anchor_engine_artifact_sha256=" + anchor.EngineArtifactSHA256, "anchor_source_manifest_sha256=" + anchor.SourceManifestSHA256}
		seeds := make([]int64, 0, len(direction.SeedDPSChanges))
		for seed, delta := range direction.SeedDPSChanges {
			if seed <= 0 || !finite(delta) || delta <= 0 || direction.ResultSHA256BySeed[seed] == "" {
				return out, fmt.Errorf("positive response proposal has inconsistent sampled evidence")
			}
			seeds = append(seeds, seed)
		}
		sort.Slice(seeds, func(i, j int) bool { return seeds[i] < seeds[j] })
		for _, seed := range seeds {
			codes = append(codes, fmt.Sprintf("probe_seed_%d_result_sha256=%s", seed, direction.ResultSHA256BySeed[seed]))
		}
		origin := finalists.FullBuildOrigin{Kind: string(ResponseLane), Phase: "local_response_proposal", Family: base.Row.Family, ContextSHA256: alias.ContextSHA256, DiagnosticCodes: codes}
		coordinate := -1
		for index, key := range keys {
			if key == direction.Stat {
				coordinate = index
			}
		}
		legalStat := coordinate >= 0
		for _, options := range choices {
			for _, option := range options {
				legalStat = legalStat || option == direction.Stat
			}
		}
		if !legalStat {
			out.Diagnostics = append(out.Diagnostics, ResponseDiagnostic{direction.Owner, direction.Stat, "no_legal_artifact_stat"})
			continue
		}
		eligible = append(eligible, legalResponseDirection{direction, actor, coordinate, origin})
	}
	propose := func(state alloc.State, primary legalResponseDirection, peers []legalResponseDirection, shape string) error {
		direction, actor := primary.direction, primary.actor
		if err := alloc.ValidateFull45(state); err != nil {
			out.Diagnostics = append(out.Diagnostics, ResponseDiagnostic{direction.Owner, direction.Stat, "inadmissible_full45:" + err.Error()})
			return nil
		}
		index, duplicate := seen[state]
		if duplicate && index < 0 {
			return nil
		}
		if !duplicate && len(out.Candidates) == ResponseProposalLimit {
			out.Diagnostics = append(out.Diagnostics, ResponseDiagnostic{direction.Owner, direction.Stat, "response_proposal_limit"})
			return nil
		}
		totals, err := ArtifactStatTotals(state)
		if err != nil {
			return err
		}
		displacement := totals[actor][direction.Stat] - baseStats[actor][direction.Stat]
		if displacement*direction.Amount <= 0 {
			out.Diagnostics = append(out.Diagnostics, ResponseDiagnostic{direction.Owner, direction.Stat, "no_legal_stat_displacement"})
			return nil
		}
		origins := cloneOrigins(base.Build.Origins)
		originKeys := originKeysByState[state]
		if duplicate {
			origins = cloneOrigins(out.Candidates[index].Build.Origins)
		} else {
			originKeys = map[string]bool{}
		}
		for _, peer := range peers {
			key, err := contracts.CanonicalSHA256(peer.origin)
			if err != nil {
				return err
			}
			if originKeys[key] {
				continue
			}
			origin := peer.origin
			origin.DiagnosticCodes = append(append([]string{}, origin.DiagnosticCodes...), "proposal_shape="+shape)
			origins = append(origins, origin)
			originKeys[key] = true
		}
		priority := ProposalPriority{LegalStatDisplacement: displacement}
		for _, peer := range peers {
			delta := totals[actor][peer.direction.Stat] - baseStats[actor][peer.direction.Stat]
			if finite(peer.direction.MinimumOtherDPSChange) && peer.direction.MinimumOtherDPSChange > 0 && delta*peer.direction.Amount > 0 {
				guide := peer.direction.MinimumOtherDPSChange * delta / peer.direction.Amount
				if !finite(guide) {
					continue
				}
				priority.ForeignPositive = true
				priority.CrossAncestryMissing = priority.CrossAncestryMissing || peer.direction.CrossAncestryMissing
				combined := priority.LocalOtherDPSGuide + guide
				if finite(combined) {
					priority.LocalOtherDPSGuide = combined
				} else {
					priority.LocalOtherDPSGuide = max(priority.LocalOtherDPSGuide, guide)
				}
			}
		}
		if duplicate {
			candidate := &out.Candidates[index]
			candidate.Build.Origins = origins
			foreign, cross := candidate.Priority.ForeignPositive, candidate.Priority.CrossAncestryMissing
			if priority.LocalOtherDPSGuide > candidate.Priority.LocalOtherDPSGuide {
				candidate.Priority = priority
			}
			candidate.Priority.ForeignPositive = foreign || priority.ForeignPositive
			candidate.Priority.CrossAncestryMissing = cross || priority.CrossAncestryMissing
			return nil
		}
		score, _, err := objective(state, false)
		if err != nil {
			return err
		}
		candidate, err := NewCandidate(base.Build.FrameSHA256, state, alias, score, origins, base.Row.RefinementLevel)
		if err != nil {
			return err
		}
		candidate.Lane, candidate.Priority = ResponseLane, priority
		seen[state] = len(out.Candidates)
		originKeysByState[state] = originKeys
		out.Candidates = append(out.Candidates, candidate)
		return nil
	}
	// Complete combined witnesses are offered before single-main/quarter steps.
	// Formula rank never trims this response lane. Other wearers stay unchanged.
	for _, primary := range eligible {
		peers := []legalResponseDirection{primary}
		byStat := map[string]legalResponseDirection{}
		for _, peer := range eligible {
			if peer.actor == primary.actor && peer.direction.Stat != primary.direction.Stat &&
				finite(peer.direction.MinimumOtherDPSChange) && peer.direction.MinimumOtherDPSChange > 0 {
				previous, exists := byStat[peer.direction.Stat]
				amount, previousAmount := peer.direction.Amount, previous.direction.Amount
				if amount < 0 {
					amount = -amount
				}
				if previousAmount < 0 {
					previousAmount = -previousAmount
				}
				if !exists || peer.direction.MinimumOtherDPSChange/amount > previous.direction.MinimumOtherDPSChange/previousAmount {
					byStat[peer.direction.Stat] = peer
				}
			}
		}
		stats := make([]string, 0, len(byStat))
		for stat := range byStat {
			stats = append(stats, stat)
		}
		sort.Strings(stats)
		for _, stat := range stats {
			peers = append(peers, byStat[stat])
		}
		if err := propose(jointResponseWitness(base.Row.Witness45, primary, peers), primary, peers, "joint_direction"); err != nil {
			return out, err
		}
	}
	for _, primary := range eligible {
		if err := propose(jointResponseWitness(base.Row.Witness45, primary, []legalResponseDirection{primary}), primary, []legalResponseDirection{primary}, "joint_single_stat"); err != nil {
			return out, err
		}
	}
	for _, primary := range eligible {
		direction, actor, coordinate := primary.direction, primary.actor, primary.coordinate
		// Transfer one legal quarter inside each piece. Insert a missing target
		// line through the existing legal seed allocator, preserving other actors.
		if coordinate >= 0 {
			state := base.Row.Witness45
			var guide [4][10]float64
			guide[actor][coordinate] = 1
			seeded := alloc.Seed(state.Mains, guide, 0, 45)
			for slot := range state.Lines[actor] {
				target := -1
				for line, stat := range state.Lines[actor][slot] {
					if stat == coordinate {
						target = line
					}
				}
				if direction.Amount > 0 && target < 0 && state.Mains[actor][slot] != direction.Stat {
					state.Lines[actor][slot], state.Upgrades[actor][slot] = seeded.Lines[actor][slot], seeded.Upgrades[actor][slot]
					for line, stat := range state.Lines[actor][slot] {
						if stat == coordinate {
							target = line
						}
					}
				}
				if target < 0 {
					continue
				}
				for line := range state.Upgrades[actor][slot] {
					if line == target {
						continue
					}
					if direction.Amount > 0 && state.Upgrades[actor][slot][line] >= .25 {
						state.Upgrades[actor][slot][line] -= .25
						state.Upgrades[actor][slot][target] += .25
						break
					}
					if direction.Amount < 0 && state.Upgrades[actor][slot][target] >= .25 {
						state.Upgrades[actor][slot][target] -= .25
						state.Upgrades[actor][slot][line] += .25
						break
					}
				}
			}
			if err := propose(state, primary, []legalResponseDirection{primary}, "local_quarter"); err != nil {
				return out, err
			}
		}
		if direction.Amount > 0 {
			for slot, mains := range choices {
				for _, main := range mains {
					if main != direction.Stat || main == base.Row.Witness45.Mains[actor][slot] {
						continue
					}
					if err := propose(alloc.ReplaceMain(base.Row.Witness45, actor, slot, main, [4][10]float64{}, 45), primary, []legalResponseDirection{primary}, "single_main"); err != nil {
						return out, err
					}
				}
			}
		}
	}
	return out, nil
}

// ResponseProducer belongs to the common probe owner. It may call the shared
// RunResponseCheck only under its own explicit allowance; nil installs no
// probing fallback. This context seam avoids importing/copying root-owned
// supportimpact or engineclient implementations into the Worker2 stage.
type ResponseProducer func(context.Context, contracts.OptimizerRequest, ResponseAnchor, Candidate) (ResponsePanel, error)

type responseProducerKey struct{}

func WithResponseProducer(ctx context.Context, producer ResponseProducer) context.Context {
	return context.WithValue(ctx, responseProducerKey{}, producer)
}

func HasResponseProducer(ctx context.Context) bool {
	producer, _ := ctx.Value(responseProducerKey{}).(ResponseProducer)
	return producer != nil
}

// OfferResponseProposals is called by the live Theory phase orchestrator before
// finalist selection. Each session invokes a configured producer at most once;
// the common owner accounts for its diagnostic calls separately from finalists.
func (a *Archive) OfferResponseProposals(ctx context.Context, request contracts.OptimizerRequest, catalogSHA string, objectiveFor func(Candidate) (alloc.Objective, error)) error {
	producer, _ := ctx.Value(responseProducerKey{}).(ResponseProducer)
	if producer == nil {
		a.responseStatus = "producer_not_connected"
		return nil
	}
	if a.responseAttempted {
		return nil
	}
	if err := ctx.Err(); err != nil {
		if errors.Is(err, context.Canceled) && searchcontrol.Requested(ctx) && searchcontrol.FinalizationContext(ctx).Err() == nil {
			a.responseStatus = "interrupted_by_finish"
			return nil
		}
		return err
	}
	responseAttempts := 0
	for key := range a.attempted {
		if a.candidates[key].Lane == ResponseLane {
			responseAttempts++
		}
	}
	if a.remaining() <= 0 || a.policy.ResponseReserve-responseAttempts <= 0 {
		a.responseStatus = "unprobed_exact_finalist_limit"
		return nil
	}
	rows := a.selectCandidates(1)
	if len(rows) == 0 {
		a.responseStatus = "no_complete_anchor"
		return nil
	}
	base := rows[0]
	anchor, err := NewResponseAnchor(request, catalogSHA, base)
	if err != nil {
		return err
	}
	a.responseAttempted = true
	panel, err := producer(ctx, request, anchor, base)
	a.responseStatus = panel.Status
	if err != nil {
		if errors.Is(err, context.Canceled) && searchcontrol.Requested(ctx) && searchcontrol.FinalizationContext(ctx).Err() == nil {
			a.responseStatus = "interrupted_by_finish"
			return nil
		}
		a.responseStatus = "failed"
		return err
	}
	if len(panel.Directions) == 0 {
		return nil
	}
	if objectiveFor == nil {
		return fmt.Errorf("response proposals require the original model objective")
	}
	objective, err := objectiveFor(base)
	if err != nil {
		return err
	}
	proposals, err := ProposeResponseDirections(base, anchor, panel, objective)
	if err != nil {
		return err
	}
	return a.Offer(proposals.Candidates)
}
