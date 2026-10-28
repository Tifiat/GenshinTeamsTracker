package theoryverify

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/engineclient"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
	"genshinteamstracker/native/gcsim_optimizer/internal/searchcontrol"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
)

func jointResponseFixture(t *testing.T) (contracts.OptimizerRequest, *Archive, Candidate, ResponseAnchor, ResponsePanel) {
	t.Helper()
	request := ordinaryRequestFixture()
	archive, _ := NewArchive(request, Policy{Limit: 7, Iterations: 500, ResponseReserve: 2})
	state := witnessFixture()
	state.Mains[0] = [5]string{"hp", "atk", "energy_recharge", "pyro_damage_bonus", "crit_rate"}
	state = alloc.Seed(state.Mains, [4][10]float64{}, 0, 45)
	base, err := NewCandidate(archive.FrameSHA256(), state, aliasFixture("joint"), 10000,
		[]finalists.FullBuildOrigin{{Kind: "formula_search", Phase: "first_light", Family: "joint", ContextSHA256: strings.Repeat("b", 64)}}, 0)
	if err != nil {
		t.Fatal(err)
	}
	anchor, err := NewResponseAnchor(request, strings.Repeat("a", 64), base)
	if err != nil {
		t.Fatal(err)
	}
	panel := ResponsePanel{AnchorCandidateSHA256: base.Key, AnchorConfigSHA256: anchor.Config.SHA256,
		EngineArtifactSHA256: anchor.EngineArtifactSHA256, SourceManifestSHA256: anchor.SourceManifestSHA256, Binding: anchor.Binding}
	return request, archive, base, anchor, panel
}

func jointDirection(anchor ResponseAnchor, owner, stat string) ResponseDirection {
	return ResponseDirection{Binding: anchor.Binding, Owner: owner, Stat: stat, Amount: .2,
		Status: "positive_on_sampled_seeds", MinimumDPSChange: 5, MaximumDPSChange: 6,
		MinimumOtherDPSChange: 4, MeanOtherDPSChange: 5, CrossAncestryMissing: true,
		ConfigSHA256: strings.Repeat("c", 64), SeedDPSChanges: map[int64]float64{73: 5, 89: 6},
		ResultSHA256BySeed: map[int64]string{73: strings.Repeat("d", 64), 89: strings.Repeat("e", 64)}}
}

func TestTheoryVerifiedJointResponseCombinesMainsAndAllocation(t *testing.T) {
	for _, test := range []struct {
		name, stat, hat string
		heal            bool
	}{
		{"atk", "atk_percent", "atk_percent", false},
		{"hp", "hp_percent", "hp_percent", false},
		{"atk_heal", "atk_percent", "healing_bonus", true},
		{"hp_heal", "hp_percent", "healing_bonus", true},
	} {
		t.Run(test.name, func(t *testing.T) {
			_, archive, base, anchor, panel := jointResponseFixture(t)
			panel.Directions = []ResponseDirection{jointDirection(anchor, "actor_a", test.stat)}
			if test.heal {
				panel.Directions = append(panel.Directions, jointDirection(anchor, "actor_a", "healing_bonus"))
			}
			calls := 0
			out, err := ProposeResponseDirections(base, anchor, panel, func(alloc.State, bool) (float64, [4][10]float64, error) {
				calls++
				return 1, [4][10]float64{}, nil
			})
			if err != nil || len(out.Candidates) == 0 || calls > ResponseProposalLimit {
				t.Fatal("joint proposal missing/unbounded", err, calls)
			}
			first := out.Candidates[0]
			state := first.Row.Witness45
			if state.Mains[0][2] != test.stat || state.Mains[0][3] != test.stat || state.Mains[0][4] != test.hat || state.Upgrades[0] == base.Row.Witness45.Upgrades[0] {
				t.Fatal("only isolated main/quarter changes survived", state.Mains[0], state.Upgrades[0])
			}
			for _, candidate := range out.Candidates {
				if err := alloc.ValidateFull45(candidate.Row.Witness45); err != nil {
					t.Fatal(err)
				}
				if candidate.Build.FormulaDPS != 1 || candidate.Build.FrameSHA256 != base.Build.FrameSHA256 || !reflect.DeepEqual(candidate.Row.Aliases, base.Row.Aliases) {
					t.Fatal("proposal corrected DPS or changed exact set/frame")
				}
				for actor := 1; actor < 4; actor++ {
					if candidate.Row.Witness45.Mains[actor] != base.Row.Witness45.Mains[actor] || candidate.Row.Witness45.Lines[actor] != base.Row.Witness45.Lines[actor] || candidate.Row.Witness45.Upgrades[actor] != base.Row.Witness45.Upgrades[actor] {
						t.Fatal("other wearer changed")
					}
				}
			}
			// The source model is deliberately blind. A complete combined witness
			// must still reach the protected ordinary lane ahead of partial changes.
			_ = archive.Offer([]Candidate{base})
			if err := archive.Offer(out.Candidates); err != nil {
				t.Fatal(err)
			}
			selected := archive.selectCandidates(1)
			if len(selected) != 1 || selected[0].Row.Witness45.Mains[0][3] != test.stat || selected[0].Row.Witness45.Mains[0][4] != test.hat || !selected[0].Priority.ForeignPositive {
				t.Fatal("complete support witness lost its reserved slot", selected)
			}
		})
	}
}

func TestTheoryVerifiedJointResponseAtCapStaysInconclusive(t *testing.T) {
	_, _, base, anchor, panel := jointResponseFixture(t)
	for _, sample := range []struct {
		name, status string
		delta        float64
	}{
		{"below_cap", "positive_on_sampled_seeds", 2},
		{"at_cap", "inconclusive_local_response", 0},
		{"mixed", "inconclusive_local_response", -1},
	} {
		t.Run(sample.name, func(t *testing.T) {
			direction := jointDirection(anchor, "actor_a", "atk_percent")
			direction.Status = sample.status
			direction.SeedDPSChanges = map[int64]float64{73: sample.delta, 89: sample.delta}
			panel.Directions = []ResponseDirection{direction}
			calls := 0
			out, err := ProposeResponseDirections(base, anchor, panel, func(alloc.State, bool) (float64, [4][10]float64, error) { calls++; return 1, [4][10]float64{}, nil })
			if err != nil {
				t.Fatal(err)
			}
			if sample.delta > 0 {
				if len(out.Candidates) == 0 {
					t.Fatal("below-cap measured direction was omitted")
				}
			} else if len(out.Candidates) != 0 || calls != 0 || len(out.Diagnostics) != 1 || out.Diagnostics[0].Reason != "inconclusive_proposal_evidence" {
				t.Fatal("zero/mixed samples became a cap certificate or proposal", out, calls)
			}
		})
	}
}

func TestTheoryVerifiedJointResponseLimitDeterminismAndBinding(t *testing.T) {
	_, _, base, anchor, panel := jointResponseFixture(t)
	stats := []string{"atk", "atk_percent", "hp", "hp_percent", "def", "def_percent", "em", "energy_recharge", "crit_rate", "crit_damage", "healing_bonus", "pyro_damage_bonus", "hydro_damage_bonus", "cryo_damage_bonus", "physical_damage_bonus"}
	for _, owner := range []string{"actor_a", "actor_b", "actor_c", "actor_d"} {
		for _, stat := range stats {
			panel.Directions = append(panel.Directions, jointDirection(anchor, owner, stat))
		}
	}
	calls := 0
	objective := func(alloc.State, bool) (float64, [4][10]float64, error) { calls++; return 1, [4][10]float64{}, nil }
	first, err := ProposeResponseDirections(base, anchor, panel, objective)
	if err != nil || calls > ResponseProposalLimit || len(first.Candidates) > ResponseProposalLimit {
		t.Fatal("unbounded response proposals", err, calls)
	}
	baseStats, _ := ArtifactStatTotals(base.Row.Witness45)
	// Large flat-HP evidence competes with all other coordinates. Every sampled
	// direction with a legal positive displacement must retain a complete one.
	for actor, owner := range []string{"actor_a", "actor_b", "actor_c", "actor_d"} {
		for _, stat := range stats {
			moved := false
			coordinate := -1
			for index, key := range alloc.StatKeys() {
				if key == stat {
					coordinate = index
				}
			}
			for _, candidate := range first.Candidates {
				if err := alloc.ValidateFull45(candidate.Row.Witness45); err != nil {
					t.Fatal(err)
				}
				totals, _ := ArtifactStatTotals(candidate.Row.Witness45)
				fullDirection := totals[actor][stat] > baseStats[actor][stat]
				for slot, lines := range candidate.Row.Witness45.Lines[actor] {
					if coordinate < 0 || candidate.Row.Witness45.Mains[actor][slot] == stat {
						continue
					}
					fullPiece := false
					for line, value := range lines {
						fullPiece = fullPiece || value == coordinate && candidate.Row.Witness45.Upgrades[actor][slot][line] == 5
					}
					fullDirection = fullDirection && fullPiece
				}
				recorded := false
				for _, origin := range candidate.Build.Origins {
					ownerPresent, statPresent := false, false
					for _, code := range origin.DiagnosticCodes {
						ownerPresent = ownerPresent || code == "owner="+owner
						statPresent = statPresent || code == "stat="+stat
					}
					recorded = recorded || ownerPresent && statPresent
				}
				moved = moved || fullDirection && recorded
			}
			if actor == 0 && stat == "pyro_damage_bonus" {
				// The sole pyro main is already present and has no substat line.
				// A positive probe outside this artifact domain cannot invent a move.
				diagnosed := false
				for _, diagnostic := range first.Diagnostics {
					diagnosed = diagnosed || diagnostic.Owner == owner && diagnostic.Stat == stat && diagnostic.Reason == "no_legal_stat_displacement"
				}
				if moved || !diagnosed {
					t.Fatal("saturated artifact main was increased or left undiagnosed")
				}
			} else if !moved {
				t.Fatal("competing direction lost all complete proposals", owner, stat)
			}
		}
	}
	for i, j := 0, len(panel.Directions)-1; i < j; i, j = i+1, j-1 {
		panel.Directions[i], panel.Directions[j] = panel.Directions[j], panel.Directions[i]
	}
	calls = 0
	second, err := ProposeResponseDirections(base, anchor, panel, objective)
	if err != nil || len(first.Candidates) != len(second.Candidates) || calls > ResponseProposalLimit {
		t.Fatal("direction ordering changed work", err, calls)
	}
	for index := range first.Candidates {
		if first.Candidates[index].Key != second.Candidates[index].Key {
			t.Fatal("proposal order is nondeterministic")
		}
	}
	for _, field := range []string{"anchor", "request", "artifact", "binding", "source", "patch"} {
		t.Run(field, func(t *testing.T) {
			changed := panel
			changed.Directions = append([]ResponseDirection(nil), panel.Directions...)
			binding := &changed.Directions[0].Binding
			wrong := strings.Repeat("f", 64)
			switch field {
			case "anchor":
				binding.AnchorConfigSHA256 = wrong
			case "request":
				binding.RequestSHA256 = wrong
			case "artifact":
				binding.EngineArtifactSHA256 = wrong
			case "binding":
				binding.EngineBindingSHA256 = wrong
			case "source":
				binding.EngineSourceManifestSHA256 = wrong
			case "patch":
				binding.EnginePatchManifestSHA256 = wrong
			}
			calls = 0
			if _, err := ProposeResponseDirections(base, anchor, changed, objective); err == nil || calls != 0 {
				t.Fatal("cross-binding direction reached the model", err, calls)
			}
		})
	}
}

func TestTheoryVerifiedJointResponseDiagnosesUnusableStatAndDuplicates(t *testing.T) {
	_, _, base, anchor, panel := jointResponseFixture(t)
	panel.Directions = []ResponseDirection{jointDirection(anchor, "actor_a", "unsupported_artifact_stat"), jointDirection(anchor, "actor_a", "hp_percent")}
	calls := 0
	objective := func(alloc.State, bool) (float64, [4][10]float64, error) { calls++; return 1, [4][10]float64{}, nil }
	out, err := ProposeResponseDirections(base, anchor, panel, objective)
	if err != nil || len(out.Candidates) == 0 || len(out.Diagnostics) != 1 || out.Diagnostics[0].Reason != "no_legal_artifact_stat" {
		t.Fatal("unusable coordinate aborted the usable complete directions", out, err)
	}
	panel.Directions = append(panel.Directions, panel.Directions[1])
	calls = 0
	if _, err := ProposeResponseDirections(base, anchor, panel, objective); err == nil || calls != 0 {
		t.Fatal("ambiguous duplicate direction reached the model", err, calls)
	}
}

func TestTheoryVerifiedJointResponseRetainsRepeatedMagnitudeEvidence(t *testing.T) {
	_, archive, base, anchor, panel := jointResponseFixture(t)
	weak := jointDirection(anchor, "actor_a", "hp_percent")
	weak.Amount, weak.MinimumOtherDPSChange, weak.CrossAncestryMissing = .1, 0, false
	strong := jointDirection(anchor, "actor_a", "hp_percent")
	strong.ConfigSHA256 = strings.Repeat("f", 64)
	panel.Directions = []ResponseDirection{strong, weak}
	calls := 0
	objective := func(alloc.State, bool) (float64, [4][10]float64, error) { calls++; return 1, [4][10]float64{}, nil }
	out, err := ProposeResponseDirections(base, anchor, panel, objective)
	if err != nil || len(out.Candidates) == 0 || calls != len(out.Candidates) {
		t.Fatal("same complete witness was re-evaluated or omitted", err, calls)
	}
	first := out.Candidates[0]
	if !first.Priority.ForeignPositive || !first.Priority.CrossAncestryMissing || first.Priority.LocalOtherDPSGuide <= 0 || len(first.Build.Origins) != 3 {
		t.Fatal("later stronger support evidence was dropped by witness deduplication", first.Priority, first.Build.Origins)
	}
	amounts := map[string]bool{}
	for _, origin := range first.Build.Origins {
		for _, code := range origin.DiagnosticCodes {
			if strings.HasPrefix(code, "probe_amount=") {
				amounts[code] = true
			}
		}
	}
	if !amounts["probe_amount=0.1"] || !amounts["probe_amount=0.2"] {
		t.Fatal("exact magnitude provenance was lost", amounts)
	}
	panel.Directions[0], panel.Directions[1] = panel.Directions[1], panel.Directions[0]
	calls = 0
	reversed, err := ProposeResponseDirections(base, anchor, panel, objective)
	if err != nil || !reflect.DeepEqual(out.Candidates, reversed.Candidates) || calls != len(reversed.Candidates) {
		t.Fatal("magnitude ordering changed evidence or repeated model work", err, calls)
	}
	_ = archive.Offer([]Candidate{base})
	if err := archive.Offer(out.Candidates); err != nil {
		t.Fatal(err)
	}
	if selected := archive.selectCandidates(1); len(selected) != 1 || !selected[0].Priority.CrossAncestryMissing || len(archive.verified) != 0 {
		t.Fatal("stronger exact evidence lost the protected slot or certified a proposal", selected)
	}
}

func TestTheoryVerifiedJointResponseCombinesSignedDirections(t *testing.T) {
	for _, positiveStat := range []string{"atk_percent", "healing_bonus"} {
		t.Run(positiveStat, func(t *testing.T) {
			request, archive, base, _, _ := jointResponseFixture(t)
			state := base.Row.Witness45
			state.Mains[0] = [5]string{"hp", "atk", "hp_percent", "hp_percent", "hp_percent"}
			state = alloc.Seed(state.Mains, [4][10]float64{}, 0, 45)
			base, err := NewCandidate(archive.FrameSHA256(), state, base.Row.Aliases[0], 10000, base.Build.Origins, 0)
			if err != nil {
				t.Fatal(err)
			}
			anchor, err := NewResponseAnchor(request, strings.Repeat("a", 64), base)
			if err != nil {
				t.Fatal(err)
			}
			negative := jointDirection(anchor, "actor_a", "hp_percent")
			negative.Amount = -.2
			panel := ResponsePanel{AnchorCandidateSHA256: base.Key, AnchorConfigSHA256: anchor.Config.SHA256,
				EngineArtifactSHA256: anchor.EngineArtifactSHA256, SourceManifestSHA256: anchor.SourceManifestSHA256, Binding: anchor.Binding,
				Directions: []ResponseDirection{negative, jointDirection(anchor, "actor_a", positiveStat)}}
			out, err := ProposeResponseDirections(base, anchor, panel, func(alloc.State, bool) (float64, [4][10]float64, error) { return 1, [4][10]float64{}, nil })
			if err != nil || len(out.Candidates) == 0 {
				t.Fatal("signed complete combination is missing", err)
			}
			before, _ := ArtifactStatTotals(base.Row.Witness45)
			after, _ := ArtifactStatTotals(out.Candidates[0].Row.Witness45)
			if after[0][positiveStat] <= before[0][positiveStat] || after[0]["hp_percent"] >= before[0]["hp_percent"] || len(out.Candidates[0].Build.Origins) != 3 {
				t.Fatal("beneficial decrease was left outside the complete combination", before[0], after[0])
			}
			for _, candidate := range out.Candidates {
				if err := alloc.ValidateFull45(candidate.Row.Witness45); err != nil {
					t.Fatal(err)
				}
			}
		})
	}
}

func TestTheoryVerifiedResponseProposalsKeepOriginalFormulaAndFull45(t *testing.T) {
	request := ordinaryRequestFixture()
	archive, _ := NewArchive(request, Policy{Limit: 7, Iterations: 500, ResponseReserve: 2})
	base := candidateFixture(t, archive, "generic", 10)
	direction := ResponseDirection{Owner: "actor_a", Stat: "hp_percent", Amount: .2, MeanDPSChange: 9999,
		MinimumDPSChange: 5, MaximumDPSChange: 6, Status: "positive_on_sampled_seeds", ConfigSHA256: strings.Repeat("c", 64),
		SeedDPSChanges: map[int64]float64{73: 5, 89: 6}, ResultSHA256BySeed: map[int64]string{73: strings.Repeat("d", 64), 89: strings.Repeat("e", 64)}}
	objective := func(alloc.State, bool) (float64, [4][10]float64, error) { return 10, [4][10]float64{}, nil }
	anchor, err := NewResponseAnchor(request, strings.Repeat("a", 64), base)
	if err != nil {
		t.Fatal(err)
	}
	panel := ResponsePanel{AnchorCandidateSHA256: base.Key, AnchorConfigSHA256: anchor.Config.SHA256,
		EngineArtifactSHA256: request.Engine.ArtifactSHA256, SourceManifestSHA256: request.Engine.SourceManifestSHA256, Binding: anchor.Binding}
	direction.Binding = anchor.Binding
	panel.Directions = []ResponseDirection{direction}
	result, err := ProposeResponseDirections(base, anchor, panel, objective)
	if err != nil || len(result.Candidates) == 0 {
		t.Fatal("no legal response proposal", err)
	}
	for _, candidate := range result.Candidates {
		if candidate.Build.FormulaDPS != 10 || candidate.Lane != ResponseLane || len(candidate.Build.Origins) != 2 {
			t.Fatal("derivative was substituted as formula/verified score", candidate)
		}
		if err := alloc.ValidateFull45(candidate.Row.Witness45); err != nil {
			t.Fatal(err)
		}
		for actor := 1; actor < 4; actor++ {
			if candidate.Row.Witness45.Mains[actor] != base.Row.Witness45.Mains[actor] || candidate.Row.Witness45.Lines[actor] != base.Row.Witness45.Lines[actor] || candidate.Row.Witness45.Upgrades[actor] != base.Row.Witness45.Upgrades[actor] {
				t.Fatal("response proposal changed an unrelated wearer")
			}
		}
	}
	direction.Status = "inconclusive_local_response"
	panel.Directions = []ResponseDirection{direction}
	result, err = ProposeResponseDirections(base, anchor, panel, objective)
	if err != nil || len(result.Candidates) != 0 || len(result.Diagnostics) != 1 || result.Diagnostics[0].Reason != "inconclusive_proposal_evidence" {
		t.Fatal("mixed/zero local evidence became a usable/cap certificate", result, err)
	}
	other := candidateFixture(t, archive, "changed_set_context", 10)
	if _, err := ProposeResponseDirections(other, anchor, panel, objective); err == nil {
		t.Fatal("local response was inherited by another set context")
	}
}

func TestTheoryVerifiedConfiguredResponseProducerIsOnceAndUnpruned(t *testing.T) {
	request := ordinaryRequestFixture()
	archive, _ := NewArchive(request, Policy{Limit: 7, Iterations: 500, ResponseReserve: 2})
	base := candidateFixture(t, archive, "original", 10000)
	_ = archive.Offer([]Candidate{base})
	producerCalls := 0
	ctx := WithResponseProducer(context.Background(), func(_ context.Context, _ contracts.OptimizerRequest, anchor ResponseAnchor, candidate Candidate) (ResponsePanel, error) {
		producerCalls++
		direction := ResponseDirection{Binding: anchor.Binding, Owner: "actor_a", Stat: "hp_percent", Amount: .2,
			Status: "positive_on_sampled_seeds", ConfigSHA256: strings.Repeat("b", 64),
			SeedDPSChanges: map[int64]float64{73: 5, 89: 6}, ResultSHA256BySeed: map[int64]string{73: strings.Repeat("d", 64), 89: strings.Repeat("e", 64)}}
		return ResponsePanel{AnchorCandidateSHA256: candidate.Key, AnchorConfigSHA256: anchor.Config.SHA256,
			EngineArtifactSHA256: anchor.EngineArtifactSHA256, SourceManifestSHA256: anchor.SourceManifestSHA256,
			Binding: anchor.Binding, Directions: []ResponseDirection{direction}, Status: "complete_proposal_evidence_only"}, nil
	})
	objectiveFor := func(Candidate) (alloc.Objective, error) {
		return func(alloc.State, bool) (float64, [4][10]float64, error) { return 1, [4][10]float64{}, nil }, nil
	}
	for step := 0; step < 2; step++ {
		if err := archive.OfferResponseProposals(ctx, request, strings.Repeat("a", 64), objectiveFor); err != nil {
			t.Fatal(err)
		}
	}
	selected := archive.selectCandidates(1)
	if producerCalls != 1 || len(selected) != 1 || selected[0].Lane != ResponseLane || selected[0].Build.FormulaDPS != 1 || len(archive.verified) != 0 {
		t.Fatal("response producer restarted, was formula-pruned or certified", producerCalls, selected)
	}
}

func TestTheoryVerifiedResponseReservePrioritizesForeignSupportWithinOneSlot(t *testing.T) {
	request := ordinaryRequestFixture()
	archive, _ := NewArchive(request, Policy{Limit: 3, Iterations: 500, ResponseReserve: 1})
	base := candidateFixture(t, archive, "original", 10000)
	anchor, _ := NewResponseAnchor(request, strings.Repeat("a", 64), base)
	directions := []ResponseDirection{}
	for _, owner := range []string{"actor_a", "actor_d"} {
		direction := ResponseDirection{Binding: anchor.Binding, Owner: owner, Stat: "hp_percent", Amount: .2,
			Status: "positive_on_sampled_seeds", ConfigSHA256: strings.Repeat("b", 64),
			SeedDPSChanges: map[int64]float64{73: 5, 89: 6}, ResultSHA256BySeed: map[int64]string{73: strings.Repeat("d", 64), 89: strings.Repeat("e", 64)}}
		if owner == "actor_d" {
			direction.MinimumOtherDPSChange, direction.MeanOtherDPSChange = 4, 5
			direction.CrossAncestryMissing = true
		}
		directions = append(directions, direction)
	}
	panel := ResponsePanel{AnchorCandidateSHA256: base.Key, AnchorConfigSHA256: anchor.Config.SHA256,
		EngineArtifactSHA256: anchor.EngineArtifactSHA256, SourceManifestSHA256: anchor.SourceManifestSHA256, Binding: anchor.Binding, Directions: directions}
	proposals, err := ProposeResponseDirections(base, anchor, panel, func(alloc.State, bool) (float64, [4][10]float64, error) {
		return 1, [4][10]float64{}, nil
	})
	if err != nil {
		t.Fatal(err)
	}
	_ = archive.Offer([]Candidate{base})
	if err := archive.Offer(proposals.Candidates); err != nil {
		t.Fatal(err)
	}
	selected := archive.selectCandidates(1)
	if len(selected) != 1 || !selected[0].Priority.ForeignPositive || !selected[0].Priority.CrossAncestryMissing || selected[0].Build.FormulaDPS != 1 {
		t.Fatal("one response slot was crowded out by owner order or formula rank", selected)
	}
	ownerRecorded := false
	for _, origin := range selected[0].Build.Origins {
		for _, code := range origin.DiagnosticCodes {
			ownerRecorded = ownerRecorded || code == "owner=actor_d"
		}
	}
	if !ownerRecorded {
		t.Fatal("paired foreign-support proposal was not retained")
	}
}

func TestTheoryVerifiedNoChallengerSlotDoesNotInvokeResponseProducer(t *testing.T) {
	request := ordinaryRequestFixture()
	request.Finalists = &contracts.FinalistPolicy{PolicyID: "explicit_one", MaxCandidates: 1, Iterations: 500}
	policy, _ := PolicyFromRequest(request)
	archive, _ := NewArchive(request, policy)
	_ = archive.Offer([]Candidate{candidateFixture(t, archive, "original", 100)})
	calls := 0
	ctx := WithResponseProducer(context.Background(), func(context.Context, contracts.OptimizerRequest, ResponseAnchor, Candidate) (ResponsePanel, error) {
		calls++
		return ResponsePanel{}, nil
	})
	if err := archive.OfferResponseProposals(ctx, request, strings.Repeat("a", 64), nil); err != nil || calls != 0 || archive.responseStatus != "unprobed_exact_finalist_limit" {
		t.Fatal("response diagnostics ran without an available verification slot", err, calls, archive.responseStatus)
	}
}

func TestTheoryVerifiedFinishDuringResponseKeepsOrdinaryFinalization(t *testing.T) {
	request := ordinaryRequestFixture()
	archive, _ := NewArchive(request, Policy{Limit: 3, Iterations: 50, ResponseReserve: 1})
	base := candidateFixture(t, archive, "original", 100)
	_ = archive.Offer([]Candidate{base})
	finishPath := filepath.Join(t.TempDir(), "finish")
	outer := WithResponseProducer(searchcontrol.WithFile(context.Background(), finishPath),
		func(ctx context.Context, _ contracts.OptimizerRequest, _ ResponseAnchor, _ Candidate) (ResponsePanel, error) {
			if err := os.WriteFile(finishPath, nil, 0600); err != nil {
				return ResponsePanel{}, err
			}
			searchcontrol.Ready(ctx)
			return ResponsePanel{}, ctx.Err()
		})
	searchCtx, stop := searchcontrol.Begin(outer)
	defer stop()
	if err := archive.OfferResponseProposals(searchCtx, request, strings.Repeat("a", 64), nil); err != nil {
		t.Fatal("Finish during optional response prevented finalization", err)
	}
	if !searchcontrol.Requested(searchCtx) || outer.Err() != nil || archive.responseStatus != "interrupted_by_finish" {
		t.Fatal("Finish cancelled the outer context or lost its diagnostic", archive.responseStatus)
	}
	render, _ := Renderer(request, strings.Repeat("e", 64))
	calls := 0
	if err := archive.Verify(outer, request, searchFixture([]Candidate{base}, "first_light"), true, render, t.TempDir(), 1, nil, nil,
		func(ctx context.Context, _ contracts.OptimizerRequest, text, _ string, iterations, _ int) (engineclient.OrdinaryResult, error) {
			calls++
			if err := ctx.Err(); err != nil {
				return engineclient.OrdinaryResult{}, err
			}
			return runnerReceipt(text, iterations, 100), nil
		}); err != nil || calls != 1 || len(archive.verified) != 1 {
		t.Fatal("bounded ordinary result was lost after soft Finish", err, calls, len(archive.verified))
	}
}

func TestTheoryVerifiedCancelDuringResponseIsNotSoftFinish(t *testing.T) {
	request := ordinaryRequestFixture()
	archive, _ := NewArchive(request, Policy{Limit: 3, Iterations: 50, ResponseReserve: 1})
	_ = archive.Offer([]Candidate{candidateFixture(t, archive, "original", 100)})
	outer, cancel := context.WithCancel(context.Background())
	defer cancel()
	outer = WithResponseProducer(outer, func(ctx context.Context, _ contracts.OptimizerRequest, _ ResponseAnchor, _ Candidate) (ResponsePanel, error) {
		cancel()
		return ResponsePanel{}, ctx.Err()
	})
	searchCtx, stop := searchcontrol.Begin(outer)
	defer stop()
	if err := archive.OfferResponseProposals(searchCtx, request, strings.Repeat("a", 64), nil); !errors.Is(err, context.Canceled) || archive.responseStatus != "failed" || len(archive.verified) != 0 {
		t.Fatal("hard Cancel was swallowed or certified a proposal", err, archive.responseStatus)
	}
}
