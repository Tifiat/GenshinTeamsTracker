package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/engineclient"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

var (
	closeoutSetLine    = regexp.MustCompile(`^([ \t]*)([a-z][a-z0-9_]*)[ \t]+add[ \t]+set="([^"]+)"[ \t]+count=([1-5])([ \t]*\+params[ \t]*=[ \t]*\[[^\[\];\r\n]*\])?;[ \t]*\r?$`)
	closeoutStatsLine  = regexp.MustCompile(`^([ \t]*)([a-z][a-z0-9_]*)[ \t]+add[ \t]+stats\b[^;]*;([ \t]*\r?)$`)
	closeoutOptionLine = regexp.MustCompile(`^([ \t]*options[ \t]+)([^;]+)(;[ \t]*\r?)$`)
	closeoutActorLine  = regexp.MustCompile(`^([ \t]*)([a-z][a-z0-9_]*)[ \t]+char\b`)
)

type closeoutCaseInput struct {
	Name            string                         `json:"name"`
	Assignment      []contracts.ArtifactAssignment `json:"assignment"`
	Selection       map[string]any                 `json:"selection"`
	StatDeltaVsTop1 map[string]float64             `json:"stat_delta_vs_top1"`
}

type closeoutCasesInput struct {
	SchemaVersion            int                 `json:"schema_version"`
	SchemaKind               string              `json:"schema_kind"`
	ProductionTop1FormulaDPS float64             `json:"production_top1_formula_dps"`
	Cases                    []closeoutCaseInput `json:"cases"`
}

type closeoutChannelShape struct {
	ChannelID  string `json:"channel_id"`
	Kind       string `json:"kind"`
	ActorKey   string `json:"actor_key"`
	AttackTag  string `json:"attack_tag"`
	DamageType string `json:"damage_type"`
	HitCount   int    `json:"hit_count"`
}

type closeoutTopology struct {
	Seed                      uint64   `json:"seed"`
	TopologySHA256            string   `json:"topology_sha256"`
	ReferenceTopologySHA256   string   `json:"reference_topology_sha256"`
	NeutralBaseTopologySHA256 string   `json:"neutral_base_topology_sha256"`
	ChannelCount              int      `json:"channel_count"`
	ChannelSHA256             string   `json:"channel_sha256"`
	ReferenceChannelSHA256    string   `json:"reference_channel_sha256"`
	NeutralBaseChannelSHA256  string   `json:"neutral_base_channel_sha256"`
	ActorTagTypeHitCounts     []string `json:"actor_tag_type_hit_counts"`
	MatchesReference          bool     `json:"matches_reference"`
	MatchesNeutralBase        bool     `json:"matches_neutral_base"`
}

type closeoutHitFrame struct {
	HitID     uint64 `json:"hit_id"`
	Actor     string `json:"actor"`
	Frame     int    `json:"frame"`
	HitFrame  int    `json:"hit_frame"`
	AttackTag string `json:"attack_tag"`
	Element   string `json:"element"`
	EventID   string `json:"event_id,omitempty"`
	Mode      string `json:"mode"`
}

func TestCloseoutConfigPredicates(t *testing.T) {
	base := "chasca char name=Chasca;\n" +
		"chasca add set=\"chasca_set\" count=4 +params=[pilot=1];\n" +
		"chasca add stats atk=100 cr=60;\n" +
		"options iteration=500;\n"
	candidate := "chasca char name=Chasca;\n" +
		"chasca add set=\"chasca_set\" count=5 +params=[pilot=1];\n" +
		"chasca add stats atk=900 cr=80;\n" +
		"options iteration=1 workers=1;\n"
	if !equalConfigFingerprint(base, candidate) {
		t.Fatal("stats, set-count, iteration, and added worker tokens should be masked")
	}
	if equalConfigFingerprint(base, strings.Replace(candidate, "pilot=1", "pilot=2", 1)) {
		t.Fatal("set parameters must remain part of the fixed config fingerprint")
	}
	if equalConfigFingerprint(base, strings.Replace(candidate, "chasca_set", "other_set", 1)) {
		t.Fatal("set identity must remain part of the fixed config fingerprint")
	}
	if equalConfigFingerprint(base, strings.Replace(candidate, "options iteration=1", "options target=1 iteration=1", 1)) {
		t.Fatal("non-budget option changes must remain visible")
	}
	withoutSets, removed, err := closeoutRemoveSetRows(candidate)
	if err != nil || removed != 1 || strings.Contains(withoutSets, "add set") {
		t.Fatalf("set-row removal failed: removed=%d err=%v", removed, err)
	}
	sets, err := closeoutParseSetRows(candidate)
	if err != nil || len(sets["chasca"]) != 1 || sets["chasca"][0].Parameters != " +params=[pilot=1]" {
		t.Fatalf("parameterized set suffix was not retained: sets=%v err=%v", sets, err)
	}
	if got := closeoutDeclarationOrder(candidate); !equalStrings(got, []string{"chasca"}) {
		t.Fatalf("actor declaration predicate failed: %v", got)
	}
	if got := closeoutCompactSortedStrings(nil); got != nil {
		t.Fatalf("nil input must remain nil, got %#v", got)
	}
	empty := []string{}
	if got := closeoutCompactSortedStrings(empty); got == nil || len(got) != 0 {
		t.Fatalf("non-nil empty input must remain non-nil and empty, got %#v", got)
	}
	if got := closeoutCompactSortedStrings([]string{"alpha", "alpha", "beta", "beta", "gamma"}); !equalStrings(got, []string{"alpha", "beta", "gamma"}) {
		t.Fatalf("sorted duplicate strings were not compacted: %v", got)
	}
}

// closeoutCompactSortedStrings removes adjacent duplicates from an already
// sorted slice while preserving the distinction between nil and empty slices.
func closeoutCompactSortedStrings(values []string) []string {
	if values == nil || len(values) < 2 {
		return values
	}
	write := 1
	for read := 1; read < len(values); read++ {
		if values[read] == values[write-1] {
			continue
		}
		values[write] = values[read]
		write++
	}
	return values[:write]
}

func TestCloseoutResponse(t *testing.T) {
	requestPath := requiredCloseoutEnv(t, "GTT_CLOSEOUT_REQUEST")
	referenceCompactPath := requiredCloseoutEnv(t, "GTT_CLOSEOUT_REFERENCE_COMPACT")
	zeroDeltasPath := requiredCloseoutEnv(t, "GTT_CLOSEOUT_ZERO_DELTAS")
	sourcesPath := requiredCloseoutEnv(t, "GTT_CLOSEOUT_SOURCES")
	casesPath := requiredCloseoutEnv(t, "GTT_CLOSEOUT_CASES")
	captureRoot := requiredCloseoutEnv(t, "GTT_CLOSEOUT_CAPTURE_ROOT")
	neutralRoot := requiredCloseoutEnv(t, "GTT_CLOSEOUT_NEUTRAL_ROOT")
	outputPath := requiredCloseoutEnv(t, "GTT_CLOSEOUT_OUTPUT")
	testSourceSHA := requiredCloseoutEnv(t, "GTT_CLOSEOUT_TEST_SOURCE_SHA256")

	request, referenceCompact, zeroDeltas, err := loadPanel(requestPath, referenceCompactPath, zeroDeltasPath)
	if err != nil {
		t.Fatal(err)
	}
	if len(zeroDeltas) != 0 {
		t.Fatalf("reference zero-delta map must be empty, got %d entries", len(zeroDeltas))
	}
	if len(request.Stochastic.Seeds) != 2 || request.Stochastic.Seeds[0] != 742031889 || request.Stochastic.Seeds[1] != 742031890 {
		t.Fatalf("closeout requires exactly two ordered seeds")
	}
	var input closeoutCasesInput
	if err := readCloseoutJSON(casesPath, &input); err != nil {
		t.Fatal(err)
	}
	if input.SchemaVersion != 1 || input.SchemaKind != "gtt_optimizer_closeout_cases_v1" || len(input.Cases) != 3 {
		t.Fatalf("invalid bounded closeout case envelope")
	}
	if input.Cases[0].Name != "top1" || input.Cases[1].Name != "chasca_plume" || input.Cases[2].Name != "chasca_goblet" {
		t.Fatalf("cases must be fresh production top1, then independent Chasca plume and goblet swaps")
	}

	referencePanel, err := evaluator.Compile(request, referenceCompact)
	if err != nil {
		t.Fatal(err)
	}
	index, err := domain.Build(request, referencePanel.Coordinates())
	if err != nil {
		t.Fatal(err)
	}
	actorIndex, err := closeoutActorIndex(request, "chasca")
	if err != nil {
		t.Fatal(err)
	}
	baseTiers, err := closeoutAssignmentTiers(index, index.Incumbent)
	if err != nil {
		t.Fatal(err)
	}
	declarationOrder := closeoutDeclarationOrder(request.Context.PreparedConfig.Text)
	declarationDigest := closeoutDigest(declarationOrder)
	nonArtifactConfigFingerprint, err := closeoutMaskConfig(request.Context.PreparedConfig.Text)
	if err != nil {
		t.Fatalf("prepared config fingerprint: %v", err)
	}
	nonArtifactConfigDigest := closeoutDigest(nonArtifactConfigFingerprint)
	if len(declarationOrder) != len(request.Wearers) {
		t.Fatalf("prepared config declaration order does not cover the four request wearers")
	}

	selectedBound, err := engineclient.BindEngine(request)
	if err != nil {
		t.Fatal(err)
	}

	// The neutral source bundle is read from the current active-engine source
	// library by the production All Sets adapter. This test never runs package
	// search or falls back to the saved historical source envelope.
	sources, err := readInventorySourceCatalog(sourcesPath, request)
	if err != nil {
		t.Fatal(err)
	}
	neutralEnabled, err := useNeutralAllSets(request, sources.HasNeutralRules())
	if err != nil {
		t.Fatal(err)
	}
	if !neutralEnabled {
		t.Fatalf("active engine/source bundle cannot produce the neutral All Sets model")
	}
	neutralText, setRowsRemoved, err := closeoutRemoveSetRows(request.Context.PreparedConfig.Text)
	if err != nil || setRowsRemoved == 0 {
		t.Fatalf("prepared Selected config has no removable set rows: %v", err)
	}
	if closeoutWithoutSets(request.Context.PreparedConfig.Text) != neutralText {
		t.Fatalf("neutral baseline changed a non-set prepared statement")
	}
	if !equalStrings(declarationOrder, closeoutDeclarationOrder(neutralText)) {
		t.Fatalf("neutral baseline changed character declaration order")
	}
	requestSHA, err := contracts.CanonicalSHA256(request)
	if err != nil {
		t.Fatal(err)
	}
	binding := setcontext.Binding{
		Engine:               request.Engine,
		CatalogSHA256:        sources.CatalogSHA256,
		ReferenceStatsSHA256: requestSHA,
		Seeds:                append([]uint64(nil), request.Stochastic.Seeds...),
	}
	neutralBase, err := setcontext.New(binding, neutralText)
	if err != nil {
		t.Fatal(err)
	}
	provider, err := setcontext.NewEffectEngineProvider(binding, neutralRoot)
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		if closeErr := provider.Close(); closeErr != nil {
			t.Errorf("neutral capture engine changed: %v", closeErr)
		}
	}()
	session, err := setcontext.NewSession(provider.Capture, len(request.Stochastic.Seeds))
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Minute)
	defer cancel()
	neutralCaptured, err := session.Resolve(ctx, neutralBase, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	neutralMembers, err := neutralCaptured.EnergyMembers()
	if err != nil {
		t.Fatal(err)
	}
	neutralPanel, err := neutralCaptured.SearchPanel()
	if err != nil {
		t.Fatal(err)
	}
	neutralBaseTopology := make(map[uint64]closeoutTopology, len(neutralMembers))
	for _, member := range neutralMembers {
		shape := closeoutChannelTopology(member)
		neutralBaseTopology[member.Seed] = closeoutTopology{
			Seed:                  member.Seed,
			TopologySHA256:        member.TopologySHA256,
			ChannelCount:          len(shape),
			ChannelSHA256:         closeoutDigest(shape),
			ActorTagTypeHitCounts: closeoutChannelAggregates(shape),
		}
	}
	if session.AttemptedCaptureMembers() != len(request.Stochastic.Seeds) {
		t.Fatalf("neutral capture count differs from its two-seed budget")
	}
	neutralFrames, neutralCaptureUncertainty, err := closeoutNeutralFrameEvidence(neutralCaptured)
	if err != nil {
		t.Fatal(err)
	}
	neutralModel, err := setcontext.NewNeutralModel(neutralCaptured, sources)
	if err != nil {
		t.Fatal(err)
	}

	referenceBySeed := make(map[uint64]contracts.IRSeedMember, len(referenceCompact.Members))
	for _, member := range referenceCompact.Members {
		referenceBySeed[member.Seed] = member
	}
	if len(referenceBySeed) != len(request.Stochastic.Seeds) {
		t.Fatalf("Selected production reference panel is incomplete")
	}
	baselineStats, err := index.AssignmentStats(index.Incumbent)
	if err != nil {
		t.Fatalf("incumbent physical artifact stats: %v", err)
	}
	selectedOpaqueReasons := referencePanel.OpaqueReasons()

	caseRows := make([]map[string]any, 0, len(input.Cases))
	selectedAllNumericallyMatched := true
	selectedAnyTopologyChange := false
	neutralAllNumericallyMatched := true
	neutralAnyTopologyChange := false
	neutralAnyIncompleteCoverage := len(neutralCaptureUncertainty) != 0 || len(neutralPanel.OpaqueReasons()) != 0
	var top1Stats map[string]float64
	var top1Assignment domain.Assignment
	var nativeCaptureMembers uint64
	for caseIndex, row := range input.Cases {
		if row.Name == "" || (caseIndex > 0 && row.Name == input.Cases[caseIndex-1].Name) {
			t.Fatalf("case labels must be unique and non-empty")
		}
		assignment, err := closeoutAssignment(request, row.Assignment)
		if err != nil {
			t.Fatalf("%s assignment: %v", row.Name, err)
		}
		if err := index.ValidateAssignment(assignment); err != nil {
			t.Fatalf("%s assignment violates physical Selected legality: %v", row.Name, err)
		}
		if caseIndex == 0 {
			top1Assignment = assignment
		} else {
			expectedSlot := map[int]int{1: 1, 2: 3}[caseIndex]
			if err := closeoutAssertSingleItemSwap(top1Assignment, assignment, actorIndex, expectedSlot); err != nil {
				t.Fatalf("%s is not an isolated Chasca item swap against top1: %v", row.Name, err)
			}
		}
		tiers, err := closeoutAssignmentTiers(index, assignment)
		if err != nil {
			t.Fatalf("%s package tiers: %v", row.Name, err)
		}
		if !equalStrings(baseTiers, tiers) {
			t.Fatalf("%s changed a selected bonus tier", row.Name)
		}
		rendered, err := finalists.RenderConfig(request, index, assignment, 1, 1)
		if err != nil {
			t.Fatalf("%s production config render: %v", row.Name, err)
		}
		if !equalConfigFingerprint(request.Context.PreparedConfig.Text, rendered.Text) {
			t.Fatalf("%s changed non-artifact statements, statement order, or non-budget options", row.Name)
		}
		if !equalStrings(declarationOrder, closeoutDeclarationOrder(rendered.Text)) {
			t.Fatalf("%s changed character declaration order", row.Name)
		}

		deltas, err := index.DenseDeltas(assignment)
		if err != nil {
			t.Fatalf("%s artifact deltas: %v", row.Name, err)
		}
		predicted, err := referencePanel.Evaluate(deltas)
		if err != nil {
			t.Fatalf("%s reused Selected formula: %v", row.Name, err)
		}
		if caseIndex == 0 {
			if math.Abs(predicted.MeanDPS-input.ProductionTop1FormulaDPS) > 0.0005001 {
				t.Fatalf("direct evaluator disagrees with production top1 beyond output rounding")
			}
		}

		members := make([]contracts.IRSeedMember, 0, len(request.Stochastic.Seeds))
		topology := make([]closeoutTopology, 0, len(request.Stochastic.Seeds))
		selectedTopologyStable := true
		neutralTopologyStable := true
		for _, seed := range request.Stochastic.Seeds {
			seedRoot := filepath.Join(captureRoot, row.Name, "seed-"+strconv.FormatUint(seed, 10))
			if err := os.MkdirAll(filepath.Dir(seedRoot), 0700); err != nil {
				t.Fatal(err)
			}
			captured, err := selectedBound.RunCompact(ctx, rendered.Text, seedRoot, seed, true)
			if err != nil {
				t.Fatalf("%s seed %d fresh compact capture: %v", row.Name, seed, err)
			}
			nativeCaptureMembers++
			members = append(members, captured.Member)
			baselineMember, ok := referenceBySeed[seed]
			if !ok {
				t.Fatalf("reference panel misses seed %d", seed)
			}
			shape := closeoutChannelTopology(captured.Member)
			baselineShape := closeoutChannelTopology(baselineMember)
			channelSHA := closeoutDigest(shape)
			referenceChannelSHA := closeoutDigest(baselineShape)
			neutralBaseline, ok := neutralBaseTopology[seed]
			if !ok {
				t.Fatalf("neutral panel misses seed %d", seed)
			}
			matchesReference := captured.Member.TopologySHA256 == baselineMember.TopologySHA256 && channelSHA == referenceChannelSHA
			matchesNeutralBase := captured.Member.TopologySHA256 == neutralBaseline.TopologySHA256 && channelSHA == neutralBaseline.ChannelSHA256
			selectedTopologyStable = selectedTopologyStable && matchesReference
			neutralTopologyStable = neutralTopologyStable && matchesNeutralBase
			topology = append(topology, closeoutTopology{
				Seed:                      seed,
				TopologySHA256:            captured.Member.TopologySHA256,
				ReferenceTopologySHA256:   baselineMember.TopologySHA256,
				NeutralBaseTopologySHA256: neutralBaseline.TopologySHA256,
				ChannelCount:              len(shape),
				ChannelSHA256:             channelSHA,
				ReferenceChannelSHA256:    referenceChannelSHA,
				NeutralBaseChannelSHA256:  neutralBaseline.ChannelSHA256,
				ActorTagTypeHitCounts:     closeoutChannelAggregates(shape),
				MatchesReference:          matchesReference,
				MatchesNeutralBase:        matchesNeutralBase,
			})
		}
		selectedAnyTopologyChange = selectedAnyTopologyChange || !selectedTopologyStable
		neutralAnyTopologyChange = neutralAnyTopologyChange || !neutralTopologyStable
		if err := selectedBound.VerifyUnchanged(); err != nil {
			t.Fatalf("Selected engine changed during captures: %v", err)
		}
		freshPanel, err := evaluator.CompileMembers(closeoutActorKeys(request), request.Stochastic.Seeds, members)
		if err != nil {
			t.Fatalf("%s fresh compact zero-delta panel: %v", row.Name, err)
		}
		fresh, err := freshPanel.Evaluate(make([]float64, len(freshPanel.Coordinates())))
		if err != nil {
			t.Fatalf("%s fresh compact zero-delta evaluation: %v", row.Name, err)
		}
		paired, err := closeoutPairedScores(request, referenceCompact, members, referencePanel.Coordinates(), deltas)
		if err != nil {
			t.Fatalf("%s paired seed response: %v", row.Name, err)
		}
		selectedNumericalMatch := !paired.MaterialResidual
		selectedAllNumericallyMatched = selectedAllNumericallyMatched && selectedNumericalMatch

		candidateSetRows, err := closeoutParseSetRows(rendered.Text)
		if err != nil {
			t.Fatalf("%s package set rows: %v", row.Name, err)
		}
		target, err := neutralBase.Replace(candidateSetRows)
		if err != nil {
			t.Fatalf("%s neutral fixed-package target: %v", row.Name, err)
		}
		if closeoutWithoutSets(target.Config()) != neutralText {
			t.Fatalf("%s neutral fixed-package target changed a non-set statement", row.Name)
		}
		neutralHandle, neutralUncertainty, neutralErr := neutralModel.Resolve(target)
		neutralCase := map[string]any{
			"numerical_status":               "unavailable",
			"uncertainty":                    neutralUncertainty,
			"matches_neutral_panel_topology": neutralTopologyStable,
		}
		neutralNumericMatch := false
		neutralCoverageComplete := false
		if neutralErr != nil {
			neutralCase["numerical_status"] = "error"
			neutralCase["error"] = neutralErr.Error()
		} else if neutralHandle == nil {
			neutralCase["numerical_status"] = "unknown_boundary"
		} else {
			neutralCase["route"] = neutralHandle.Route()
			neutralCase["hit_count"] = neutralHandle.HitCount()
			neutralViewPanel, panelErr := neutralHandle.SearchPanel()
			if panelErr != nil {
				neutralCase["numerical_status"] = "panel_unavailable"
				neutralCase["coverage_error"] = panelErr.Error()
			} else {
				neutralIndex, buildErr := domain.Build(request, neutralViewPanel.Coordinates())
				if buildErr != nil {
					neutralCase["numerical_status"] = "artifact_index_error"
					neutralCase["error"] = buildErr.Error()
				} else {
					neutralDeltas, deltaErr := neutralIndex.DenseDeltas(assignment)
					if deltaErr != nil {
						neutralCase["numerical_status"] = "delta_error"
						neutralCase["error"] = deltaErr.Error()
					} else {
						neutralDeltaMap := closeoutDeltaMap(neutralViewPanel.Coordinates(), neutralDeltas)
						neutralPredicted, evalErr := neutralHandle.EvaluateDPS(neutralDeltaMap)
						if evalErr != nil {
							neutralCase["numerical_status"] = "error"
							neutralCase["error"] = evalErr.Error()
						} else {
							neutralCase["predicted_dps"] = neutralPredicted
							residual := fresh.MeanDPS - neutralPredicted
							limit := closeoutResidualLimit(fresh.MeanDPS)
							neutralCase["fresh_zero_delta_dps"] = fresh.MeanDPS
							neutralCase["residual_dps"] = residual
							neutralCase["residual_limit_dps"] = limit
							neutralNumericMatch = math.Abs(residual) <= limit
							neutralCase["numerical_status"] = "material_residual"
							if neutralNumericMatch {
								neutralCase["numerical_status"] = "matches_within_numeric_tolerance"
							}
							coverageReasons := append([]string(nil), neutralUncertainty...)
							coverageReasons = append(coverageReasons, neutralCaptureUncertainty...)
							coverageReasons = append(coverageReasons, neutralViewPanel.OpaqueReasons()...)
							sort.Strings(coverageReasons)
							coverageReasons = closeoutCompactSortedStrings(coverageReasons)
							neutralCoverageComplete = len(coverageReasons) == 0
							neutralCase["source_coverage_status"] = "complete_for_observed_panel"
							if !neutralCoverageComplete {
								neutralCase["source_coverage_status"] = "incomplete_or_uncertain"
							}
							neutralCase["coverage_reasons"] = coverageReasons
						}
					}
				}
			}
		}
		neutralAllNumericallyMatched = neutralAllNumericallyMatched && neutralNumericMatch
		neutralAnyIncompleteCoverage = neutralAnyIncompleteCoverage || !neutralCoverageComplete

		physicalStats, err := index.AssignmentStats(assignment)
		if err != nil {
			t.Fatalf("%s actual physical artifact totals: %v", row.Name, err)
		}
		// AssignmentStats is the source of the exact physical vector passed to
		// RenderConfig. Keep complete Chasca totals, including formula-opaque stats.
		caseStats := copyFloatMap(physicalStats[actorIndex])
		if caseIndex == 0 {
			top1Stats = caseStats
		}
		statDeltaVsTop1 := closeoutStatDelta(top1Stats, caseStats)
		if !closeoutFloatMapsEqual(statDeltaVsTop1, row.StatDeltaVsTop1) {
			t.Fatalf("%s Python and native physical stat deltas disagree", row.Name)
		}
		caseRows = append(caseRows, map[string]any{
			"name":                        row.Name,
			"selection":                   row.Selection,
			"assignment_sha256":           closeoutAssignmentDigest(row.Assignment),
			"chasca_artifact_ids_by_slot": closeoutChascaIDs(request, row.Assignment),
			"chasca_artifact_stat_totals": caseStats,
			"chasca_stat_delta_vs_top1":   statDeltaVsTop1,
			"reused_selected_formula": map[string]any{
				"predicted_dps":          predicted.MeanDPS,
				"sample_sd_dps":          predicted.SampleSDDPS,
				"standard_error_dps":     predicted.StandardErrorDPS,
				"paired_by_seed":         paired.Rows,
				"material_residual":      paired.MaterialResidual,
				"residual_limit_dps":     paired.Limit,
				"numerical_status":       closeoutSelectedStatus(topology, paired.MaterialResidual),
				"formula_opaque_reasons": selectedOpaqueReasons,
			},
			"fresh_selected_zero_delta": map[string]any{
				"mean_dps":           fresh.MeanDPS,
				"sample_sd_dps":      fresh.SampleSDDPS,
				"standard_error_dps": fresh.StandardErrorDPS,
				"topology_by_seed":   topology,
			},
			"neutral_all_sets_fixed_package": neutralCase,
		})
	}
	if err := selectedBound.VerifyUnchanged(); err != nil {
		t.Fatal(err)
	}
	neutralStats := neutralModel.Stats()
	neutralNumericStatus := "matches_within_numeric_tolerance"
	if !neutralAllNumericallyMatched {
		neutralNumericStatus = "material_residual_or_unavailable"
	}
	neutralTopologyStatus := "matches_neutral_panel"
	if neutralAnyTopologyChange {
		neutralTopologyStatus = "changed_from_neutral_panel"
	}
	neutralCoverageStatus := "complete_for_observed_panel"
	if neutralAnyIncompleteCoverage {
		neutralCoverageStatus = "incomplete_or_uncertain"
	}
	selectedNumericStatus := "matches_within_numeric_tolerance"
	if !selectedAllNumericallyMatched {
		selectedNumericStatus = "material_residual"
	}
	selectedTopologyStatus := "matches_selected_reference"
	if selectedAnyTopologyChange {
		selectedTopologyStatus = "changed_from_selected_reference"
	}
	gateStatus := "bounded_case_numeric_response_match"
	if !selectedAllNumericallyMatched || selectedAnyTopologyChange {
		gateStatus = "selected_numeric_or_topology_mismatch"
	} else if !neutralAllNumericallyMatched || neutralAnyTopologyChange {
		gateStatus = "neutral_fixed_package_numeric_or_topology_mismatch"
	} else if neutralAnyIncompleteCoverage || len(selectedOpaqueReasons) != 0 {
		gateStatus = "numeric_match_with_incomplete_or_uncertain_coverage"
	}
	evidence := map[string]any{
		"schema_version":                                 1,
		"schema_kind":                                    "gtt_optimizer_closeout_response_measurement_v1",
		"go_test_source_sha256":                          testSourceSHA,
		"case_count":                                     len(input.Cases),
		"production_ranking_basis":                       "formula",
		"production_top1_formula_dps":                    input.ProductionTop1FormulaDPS,
		"reference_compact_sha256":                       closeoutFileDigest(referenceCompactPath),
		"reference_config_sha256":                        request.Context.PreparedConfig.SHA256,
		"reference_topology_by_seed":                     closeoutReferenceTopology(referenceCompact),
		"non_artifact_config_fingerprint_sha256":         nonArtifactConfigDigest,
		"declaration_order":                              declarationOrder,
		"declaration_order_sha256":                       declarationDigest,
		"selected_incumbent_chasca_artifact_stat_totals": copyFloatMap(baselineStats[actorIndex]),
		"neutral_panel": map[string]any{
			"status":                 "captured_no_set_neutral_panel",
			"capture_members":        len(request.Stochastic.Seeds),
			"trace_topology_by_seed": closeoutTopologyRows(neutralMembers),
			"hit_frame_actor_tag_type_summary_by_seed": neutralFrames,
			"capture_uncertainty":                      neutralCaptureUncertainty,
			"model_stats": map[string]any{
				"requests":               neutralStats.Requests,
				"unavailable":            neutralStats.Unavailable,
				"effect_inputs":          neutralStats.EffectInputs,
				"constant_damage_inputs": neutralStats.ConstantDamageInputs,
			},
		},
		"neutral_model_status": map[string]any{
			"numerical_response": neutralNumericStatus,
			"topology":           neutralTopologyStatus,
			"source_coverage":    neutralCoverageStatus,
		},
		"cases":                                               caseRows,
		"selected_response_numerical_status":                  selectedNumericStatus,
		"selected_response_topology_status":                   selectedTopologyStatus,
		"selected_formula_opaque_reasons":                     selectedOpaqueReasons,
		"neutral_response_all_numerically_matched":            neutralAllNumericallyMatched,
		"neutral_response_any_topology_change":                neutralAnyTopologyChange,
		"neutral_source_coverage_complete_for_observed_panel": !neutralAnyIncompleteCoverage,
		"gate_status":                                         gateStatus,
		"ordinary_n500_stage":                                 map[string]any{"status": "not_run", "reason": "optional; this is only a fixed-package response gate"},
		"trace_seed_capture_members_inside_go":                nativeCaptureMembers + uint64(session.AttemptedCaptureMembers()),
	}
	if nativeCaptureMembers+uint64(session.AttemptedCaptureMembers()) != uint64(len(request.Stochastic.Seeds)*(1+len(input.Cases))) {
		t.Fatalf("actual Go trace seed-member calls differ from the planned budget")
	}
	if err := writeCloseoutEvidence(outputPath, evidence); err != nil {
		t.Fatal(err)
	}
}

type closeoutPairedResult struct {
	Rows             []map[string]any
	MaterialResidual bool
	Limit            float64
}

func closeoutPairedScores(
	request contracts.OptimizerRequest,
	reference contracts.CompactIR,
	fresh []contracts.IRSeedMember,
	coordinates []string,
	deltas []float64,
) (closeoutPairedResult, error) {
	result := closeoutPairedResult{Limit: 0}
	if len(reference.Members) != len(request.Stochastic.Seeds) || len(fresh) != len(request.Stochastic.Seeds) {
		return result, fmt.Errorf("paired response panel is incomplete")
	}
	for index, seed := range request.Stochastic.Seeds {
		if reference.Members[index].Seed != seed || fresh[index].Seed != seed {
			return result, fmt.Errorf("paired response seed order changed")
		}
		basePanel, err := evaluator.CompileMembers(closeoutActorKeys(request), []uint64{seed}, []contracts.IRSeedMember{reference.Members[index]})
		if err != nil {
			return result, err
		}
		baseDelta, err := projectDeltas(basePanel.Coordinates(), coordinates, deltas)
		if err != nil {
			return result, err
		}
		predicted, err := basePanel.Evaluate(baseDelta)
		if err != nil {
			return result, err
		}
		freshPanel, err := evaluator.CompileMembers(closeoutActorKeys(request), []uint64{seed}, []contracts.IRSeedMember{fresh[index]})
		if err != nil {
			return result, err
		}
		actual, err := freshPanel.Evaluate(make([]float64, len(freshPanel.Coordinates())))
		if err != nil {
			return result, err
		}
		residual := actual.MeanDPS - predicted.MeanDPS
		limit := closeoutResidualLimit(actual.MeanDPS)
		result.Limit = math.Max(result.Limit, limit)
		if math.Abs(residual) > limit {
			result.MaterialResidual = true
		}
		result.Rows = append(result.Rows, map[string]any{
			"seed":                 seed,
			"reused_formula_dps":   predicted.MeanDPS,
			"fresh_zero_delta_dps": actual.MeanDPS,
			"residual_dps":         residual,
			"residual_limit_dps":   limit,
		})
	}
	return result, nil
}

func projectDeltas(target, source []string, values []float64) ([]float64, error) {
	if len(source) != len(values) {
		return nil, fmt.Errorf("source coordinate/delta lengths differ")
	}
	byKey := make(map[string]float64, len(source))
	for index, key := range source {
		byKey[key] = values[index]
	}
	result := make([]float64, len(target))
	for index, key := range target {
		result[index] = byKey[key]
	}
	return result, nil
}

func closeoutResidualLimit(value float64) float64 {
	return math.Max(1e-6, math.Abs(value)*1e-9)
}

func closeoutSelectedStatus(topology []closeoutTopology, material bool) string {
	if selectedAnyTopologyFor(topology) {
		return "topology_changed"
	}
	if material {
		return "material_residual"
	}
	return "response_matches_within_numeric_tolerance"
}

func selectedAnyTopologyFor(rows []closeoutTopology) bool {
	for _, row := range rows {
		if !row.MatchesReference {
			return true
		}
	}
	return false
}

func closeoutAssignment(req contracts.OptimizerRequest, rows []contracts.ArtifactAssignment) (domain.Assignment, error) {
	var result domain.Assignment
	if len(rows) != 20 {
		return result, fmt.Errorf("want exactly twenty rows")
	}
	wearerIndex := make(map[string]int, len(req.Wearers))
	for index, wearer := range req.Wearers {
		wearerIndex[wearer.WearerKey] = index
	}
	slotIndex := map[string]int{"flower": 0, "plume": 1, "sands": 2, "goblet": 3, "circlet": 4}
	seen := map[string]bool{}
	for rowIndex, row := range rows {
		w, ok := wearerIndex[row.WearerKey]
		s, slotOK := slotIndex[row.Slot]
		if !ok || !slotOK || row.ArtifactID <= 0 {
			return result, fmt.Errorf("invalid assignment row %d", rowIndex)
		}
		key := row.WearerKey + "/" + row.Slot
		if seen[key] {
			return result, fmt.Errorf("duplicate assignment slot %s", key)
		}
		seen[key] = true
		result[w][s] = row.ArtifactID
	}
	if len(seen) != 20 {
		return result, fmt.Errorf("assignment does not cover all twenty actor/slot pairs")
	}
	return result, nil
}

func closeoutAssertSingleItemSwap(base, candidate domain.Assignment, actorIndex, expectedSlot int) error {
	if actorIndex < 0 || actorIndex >= len(base) || expectedSlot < 0 || expectedSlot >= len(base[0]) {
		return fmt.Errorf("invalid actor or slot index")
	}
	changed := 0
	for actor := range base {
		for slot := range base[actor] {
			if base[actor][slot] == candidate[actor][slot] {
				continue
			}
			changed++
			if actor != actorIndex || slot != expectedSlot {
				return fmt.Errorf("changed item is outside the requested Chasca slot")
			}
		}
	}
	if changed != 1 {
		return fmt.Errorf("got %d changed artifact IDs, want exactly one", changed)
	}
	return nil
}

func closeoutStatDelta(before, after map[string]float64) map[string]float64 {
	keys := make(map[string]bool, len(before)+len(after))
	for key := range before {
		keys[key] = true
	}
	for key := range after {
		keys[key] = true
	}
	ordered := make([]string, 0, len(keys))
	for key := range keys {
		ordered = append(ordered, key)
	}
	sort.Strings(ordered)
	result := make(map[string]float64)
	for _, key := range ordered {
		if delta := after[key] - before[key]; delta != 0 {
			result[key] = delta
		}
	}
	return result
}

func closeoutFloatMapsEqual(left, right map[string]float64) bool {
	if len(left) != len(right) {
		return false
	}
	for key, value := range left {
		if other, ok := right[key]; !ok || math.Abs(value-other) > 1e-8 {
			return false
		}
	}
	return true
}

func closeoutActorIndex(req contracts.OptimizerRequest, actor string) (int, error) {
	for index, wearer := range req.Wearers {
		if wearer.WearerKey == actor {
			return index, nil
		}
	}
	return 0, fmt.Errorf("request has no wearer %s", actor)
}

func closeoutActorKeys(req contracts.OptimizerRequest) []string {
	keys := make([]string, len(req.Wearers))
	for index, wearer := range req.Wearers {
		keys[index] = wearer.WearerKey
	}
	sort.Strings(keys)
	return keys
}

func closeoutAssignmentTiers(index *domain.Index, assignment domain.Assignment) ([]string, error) {
	counts, err := index.SelectedSetCounts(assignment)
	if err != nil {
		return nil, err
	}
	var rows []string
	for wearerIndex, wearer := range index.Wearers {
		for _, set := range counts[wearerIndex] {
			if set.Count >= 2 {
				rows = append(rows, wearer.WearerKey+"/"+set.SetUID+"/2")
			}
			if set.Count >= 4 {
				rows = append(rows, wearer.WearerKey+"/"+set.SetUID+"/4")
			}
		}
	}
	sort.Strings(rows)
	return rows, nil
}

func closeoutChannelTopology(member contracts.IRSeedMember) []closeoutChannelShape {
	rows := make([]closeoutChannelShape, 0, len(member.Channels))
	for _, channel := range member.Channels {
		rows = append(rows, closeoutChannelShape{
			ChannelID:  channel.ChannelID,
			Kind:       channel.Kind,
			ActorKey:   channel.ActorKey,
			AttackTag:  channel.AttackTag,
			DamageType: channel.DamageType,
			HitCount:   channel.HitCount,
		})
	}
	sort.Slice(rows, func(i, j int) bool { return rows[i].ChannelID < rows[j].ChannelID })
	return rows
}

func closeoutChannelAggregates(rows []closeoutChannelShape) []string {
	type totals struct{ channels, hits int }
	counts := map[string]totals{}
	for _, row := range rows {
		key := row.ActorKey + "|" + row.AttackTag + "|" + row.DamageType + "|" + row.Kind
		value := counts[key]
		value.channels++
		value.hits += row.HitCount
		counts[key] = value
	}
	keys := make([]string, 0, len(counts))
	for key := range counts {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	result := make([]string, 0, len(keys))
	for _, key := range keys {
		value := counts[key]
		result = append(result, fmt.Sprintf("%s|channels=%d|hits=%d", key, value.channels, value.hits))
	}
	return result
}

func closeoutTopologyRows(members []contracts.IRSeedMember) []closeoutTopology {
	rows := make([]closeoutTopology, 0, len(members))
	for _, member := range members {
		shape := closeoutChannelTopology(member)
		rows = append(rows, closeoutTopology{
			Seed:                  member.Seed,
			TopologySHA256:        member.TopologySHA256,
			ChannelCount:          len(shape),
			ChannelSHA256:         closeoutDigest(shape),
			ActorTagTypeHitCounts: closeoutChannelAggregates(shape),
		})
	}
	sort.Slice(rows, func(i, j int) bool { return rows[i].Seed < rows[j].Seed })
	return rows
}

func closeoutNeutralFrameEvidence(handle *setcontext.Handle) ([]map[string]any, []string, error) {
	var frames []map[string]any
	var uncertainty []string
	err := handle.VisitEffectSnapshots(func(member contracts.IRSeedMember, output contracts.EffectInputsOutput) error {
		if output.Neutral == nil {
			uncertainty = append(uncertainty, "neutral_hit_frame_sidecar_missing:seed="+strconv.FormatUint(member.Seed, 10))
			return nil
		}
		neutral := output.Neutral
		for _, reason := range neutral.Uncertainty {
			uncertainty = append(uncertainty, "seed="+strconv.FormatUint(member.Seed, 10)+":"+reason)
		}
		actorKeys := make(map[int]string, len(neutral.Context.Characters))
		for _, character := range neutral.Context.Characters {
			actorKeys[character.Index] = character.Key
		}
		hits := make([]closeoutHitFrame, 0, len(neutral.Hits))
		for _, hit := range neutral.Hits {
			actor := actorKeys[hit.Actor]
			if actor == "" {
				actor = "unknown_index_" + strconv.Itoa(hit.Actor)
				uncertainty = append(uncertainty, "neutral_hit_actor_unresolved:"+actor)
			}
			hits = append(hits, closeoutHitFrame{
				HitID: hit.HitID, Actor: actor, Frame: hit.Point.Frame, HitFrame: hit.Point.HitFrame,
				AttackTag: hit.Point.AttackTag, Element: hit.Point.Element,
				EventID: hit.Point.EventID, Mode: hit.Point.Mode,
			})
		}
		sort.Slice(hits, func(i, j int) bool { return hits[i].HitID < hits[j].HitID })
		frames = append(frames, map[string]any{
			"seed":                              member.Seed,
			"duration_frames":                   neutral.Context.DurationFrames,
			"no_sets":                           neutral.Context.NoSets,
			"hit_count":                         len(hits),
			"hit_frame_sha256":                  closeoutDigest(hits),
			"actor_tag_element_mode_hit_counts": closeoutHitAggregates(hits),
		})
		return nil
	})
	sort.Strings(uncertainty)
	sort.Slice(frames, func(i, j int) bool {
		return frames[i]["seed"].(uint64) < frames[j]["seed"].(uint64)
	})
	return frames, uncertainty, err
}

func closeoutHitAggregates(hits []closeoutHitFrame) []string {
	counts := map[string]int{}
	for _, hit := range hits {
		key := hit.Actor + "|" + hit.AttackTag + "|" + hit.Element + "|" + hit.Mode
		counts[key]++
	}
	keys := make([]string, 0, len(counts))
	for key := range counts {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	result := make([]string, 0, len(keys))
	for _, key := range keys {
		result = append(result, fmt.Sprintf("%s|hits=%d", key, counts[key]))
	}
	return result
}

func closeoutRemoveSetRows(text string) (string, int, error) {
	lines := strings.SplitAfter(text, "\n")
	output := make([]string, 0, len(lines))
	removed := 0
	for _, line := range lines {
		bare := strings.TrimSuffix(line, "\n")
		bare = strings.TrimSuffix(bare, "\r")
		if closeoutSetLine.MatchString(bare) {
			removed++
			continue
		}
		if strings.Contains(bare, "add set") {
			return "", removed, fmt.Errorf("unsupported prepared set row")
		}
		output = append(output, line)
	}
	return strings.Join(output, ""), removed, nil
}

func closeoutWithoutSets(text string) string {
	output, _, err := closeoutRemoveSetRows(text)
	if err != nil {
		return ""
	}
	return output
}

func closeoutDeclarationOrder(text string) []string {
	var output []string
	for _, line := range strings.Split(text, "\n") {
		if match := closeoutActorLine.FindStringSubmatch(strings.TrimSuffix(line, "\r")); match != nil {
			output = append(output, match[2])
		}
	}
	return output
}

func equalConfigFingerprint(reference, rendered string) bool {
	left, err := closeoutMaskConfig(reference)
	if err != nil {
		return false
	}
	right, err := closeoutMaskConfig(rendered)
	return err == nil && left == right
}

func closeoutMaskConfig(text string) (string, error) {
	lines := strings.Split(text, "\n")
	for index, line := range lines {
		withoutCR := strings.TrimSuffix(line, "\r")
		if match := closeoutStatsLine.FindStringSubmatch(withoutCR); match != nil {
			lines[index] = match[1] + match[2] + " add stats <physical-artifact-stats>;" + match[3]
			continue
		}
		if match := closeoutSetLine.FindStringSubmatch(withoutCR); match != nil {
			lines[index] = strings.Replace(withoutCR, "count="+match[4], "count=#", 1)
			continue
		}
		if strings.Contains(withoutCR, "add set") {
			return "", fmt.Errorf("unsupported set row in config fingerprint")
		}
		if match := closeoutOptionLine.FindStringSubmatch(withoutCR); match != nil {
			fields := strings.Fields(match[2])
			seenIteration, seenWorkers := 0, 0
			kept := make([]string, 0, len(fields))
			for _, field := range fields {
				key, _, hasValue := strings.Cut(field, "=")
				if !hasValue {
					kept = append(kept, field)
					continue
				}
				switch key {
				case "iteration":
					seenIteration++
				case "workers":
					seenWorkers++
				default:
					kept = append(kept, field)
				}
			}
			if seenIteration != 1 || seenWorkers > 1 {
				return "", fmt.Errorf("options row must contain one iteration and at most one workers token")
			}
			lines[index] = match[1] + strings.Join(kept, " ") + match[3]
		}
	}
	return strings.Join(lines, "\n"), nil
}

func closeoutParseSetRows(text string) (map[string][]setcontext.Set, error) {
	output := map[string][]setcontext.Set{}
	for _, line := range strings.Split(text, "\n") {
		bare := strings.TrimSuffix(line, "\r")
		if match := closeoutSetLine.FindStringSubmatch(bare); match != nil {
			count, err := strconv.Atoi(match[4])
			if err != nil {
				return nil, err
			}
			output[match[2]] = append(output[match[2]], setcontext.Set{UID: match[3], Count: count, Parameters: match[5]})
		} else if strings.Contains(bare, "add set") {
			return nil, fmt.Errorf("unsupported rendered set row")
		}
	}
	return output, nil
}

func closeoutDeltaMap(coordinates []string, values []float64) map[string]float64 {
	output := make(map[string]float64, len(coordinates))
	for index, coordinate := range coordinates {
		output[coordinate] = values[index]
	}
	return output
}

func closeoutChascaIDs(req contracts.OptimizerRequest, rows []contracts.ArtifactAssignment) map[string]int64 {
	output := map[string]int64{}
	for _, row := range rows {
		if row.WearerKey == "chasca" {
			output[row.Slot] = row.ArtifactID
		}
	}
	return output
}

func closeoutAssignmentDigest(rows []contracts.ArtifactAssignment) string {
	return closeoutDigest(rows)
}

func closeoutReferenceTopology(compact contracts.CompactIR) []closeoutTopology {
	rows := closeoutTopologyRows(compact.Members)
	for index := range rows {
		rows[index].ReferenceTopologySHA256 = rows[index].TopologySHA256
		rows[index].ReferenceChannelSHA256 = rows[index].ChannelSHA256
		rows[index].MatchesReference = true
	}
	return rows
}

func closeoutDigest(value any) string {
	payload, _ := json.Marshal(value)
	digest := sha256.Sum256(payload)
	return hex.EncodeToString(digest[:])
}

func closeoutFileDigest(path string) string {
	payload, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	digest := sha256.Sum256(payload)
	return hex.EncodeToString(digest[:])
}

func readCloseoutJSON(path string, target any) error {
	payload, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	decoder := json.NewDecoder(strings.NewReader(string(payload)))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return fmt.Errorf("trailing closeout JSON data")
	}
	return nil
}

func writeCloseoutEvidence(path string, value any) error {
	payload, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	if len(payload) > 128*1024 {
		return fmt.Errorf("compact closeout evidence exceeds 128 KiB")
	}
	return os.WriteFile(path, append(payload, '\n'), 0600)
}

func requiredCloseoutEnv(t *testing.T, key string) string {
	t.Helper()
	value := os.Getenv(key)
	if value == "" {
		t.Fatalf("missing managed closeout input %s", key)
	}
	return value
}

func equalStrings(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}

func copyFloatMap(source map[string]float64) map[string]float64 {
	output := make(map[string]float64, len(source))
	for key, value := range source {
		output[key] = value
	}
	return output
}
