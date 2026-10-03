package allsets

// Opt-in paired seed-response diagnostic. It compares one source-bound
// formula prediction with an ordinary capture of the same physical winner;
// it is not an optimizer or acceptance test.
import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

func TestMatrixWinnerSeedResponse(t *testing.T) {
	run := os.Getenv("GTT_MATRIX_SEED_RESPONSE_RUN")
	if run == "" {
		t.Skip("explicit managed winner seed-response diagnosis only")
	}
	scratch := os.Getenv("GTT_SCRATCH_DIR")
	cache := os.Getenv("GOCACHE")
	if scratch == "" || filepath.Dir(run) != scratch || cache == "" || filepath.Dir(cache) != scratch {
		t.Fatal("managed workspace and child Go cache required")
	}
	read := func(path string, value any) {
		t.Helper()
		data, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if err = json.Unmarshal(data, value); err != nil {
			t.Fatal(err)
		}
	}
	var request contracts.OptimizerRequest
	var bundle seteffects.SourceBundle
	var winner struct {
		Assignment domain.Assignment `json:"Assignment"`
		Expected   float64           `json:"Expected"`
	}
	read(filepath.Join(run, "request.json"), &request)
	read(filepath.Join(run, "set-sources.json"), &bundle)
	read(filepath.Join(run, "winner.json"), &winner)
	if err := request.Validate(); err != nil {
		t.Fatal(err)
	}
	if len(request.Stochastic.Seeds) != 2 || request.Stochastic.Seeds[0] >= request.Stochastic.Seeds[1] {
		t.Fatal("winner response requires exactly two sorted distinct request seeds")
	}
	if math.IsNaN(winner.Expected) || math.IsInf(winner.Expected, 0) {
		t.Fatal("saved formula mean is nonfinite")
	}
	requestSHA, err := contracts.CanonicalSHA256(request)
	if err != nil {
		t.Fatal(err)
	}
	sources, err := seteffects.CompileSourceBundleForInventory(bundle, request.Engine, bundle.CatalogSHA256, request.Artifacts)
	if err != nil {
		t.Fatal(err)
	}
	binding := setcontext.Binding{
		Engine: request.Engine, CatalogSHA256: bundle.CatalogSHA256,
		ReferenceStatsSHA256: requestSHA, Seeds: request.Stochastic.Seeds,
	}
	base, err := setcontext.New(binding, request.Context.PreparedConfig.Text)
	if err != nil {
		t.Fatal(err)
	}
	changes := make(map[string][]setcontext.Set, len(request.Wearers))
	for _, wearer := range request.Wearers {
		changes[wearer.WearerKey] = nil
	}
	neutral, err := base.Replace(changes)
	if err != nil {
		t.Fatal(err)
	}
	index, err := domain.Build(request, nil)
	if err != nil {
		t.Fatal(err)
	}
	captures := filepath.Join(run, "captures")
	if err = os.MkdirAll(captures, 0700); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()

	neutralRoot := filepath.Join(captures, "neutral")
	if err = os.Mkdir(neutralRoot, 0700); err != nil {
		t.Fatal(err)
	}
	neutralProvider, err := setcontext.NewEffectEngineProvider(binding, neutralRoot)
	if err != nil {
		t.Fatal(err)
	}
	neutralSession, err := setcontext.NewSession(neutralProvider.Capture, 2)
	if err != nil {
		t.Fatal(err)
	}
	neutralHandle, err := neutralSession.Resolve(ctx, neutral, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	// Preserve seed duration/topology before NewNeutralModel releases the
	// borrowed capture payload.
	neutralMembers, err := neutralHandle.EnergyMembers()
	if err != nil {
		t.Fatal(err)
	}
	if len(neutralMembers) != 2 {
		t.Fatalf("neutral capture returned %d seed members, want 2", len(neutralMembers))
	}
	neutralBySeed := make(map[uint64]contracts.IRSeedMember, len(neutralMembers))
	for i, member := range neutralMembers {
		if member.Seed != request.Stochastic.Seeds[i] || member.DurationMS <= 0 || member.TopologySHA256 == "" {
			t.Fatalf("invalid neutral member metadata: %+v", member)
		}
		neutralBySeed[member.Seed] = member
	}
	model, err := setcontext.NewNeutralModel(neutralHandle, sources)
	if err != nil {
		t.Fatal(err)
	}
	if err = neutralProvider.Close(); err != nil {
		t.Fatal(err)
	}

	var packages [4]domain.Package
	for actor, wearer := range request.Wearers {
		counts := make(map[string]int)
		for _, id := range winner.Assignment[actor] {
			uid, ok := index.ArtifactSetUID(id)
			if !ok {
				t.Fatalf("winner references missing physical artifact ID %d", id)
			}
			counts[uid]++
		}
		keys := make([]string, 0, len(counts))
		for uid := range counts {
			keys = append(keys, uid)
		}
		sort.Strings(keys)
		for _, uid := range keys {
			count := counts[uid]
			if count < 2 {
				continue
			}
			if count >= 4 {
				count = 4
			} else {
				count = 2
			}
			packages[actor].Sets = append(packages[actor].Sets, contracts.SetRequirement{SetUID: uid, Count: count})
			changes[wearer.WearerKey] = append(changes[wearer.WearerKey], setcontext.Set{UID: uid, Count: count})
		}
	}
	target, err := base.Replace(changes)
	if err != nil {
		t.Fatal(err)
	}
	boundHandle, codes, err := model.Resolve(target)
	if err != nil {
		t.Fatal(err)
	}
	if boundHandle == nil {
		encoded, _ := json.Marshal(map[string]any{"codes": codes, "expected_formula_mean_dps": winner.Expected})
		fmt.Printf("SEED_RESPONSE_BOUNDARY %s\n", encoded)
		return
	}
	boundPanel, err := boundHandle.SearchPanel()
	if err != nil {
		t.Fatal(err)
	}
	view, err := index.ForPackages(packages, winner.Assignment, boundPanel.Coordinates())
	if err != nil {
		t.Fatal(err)
	}
	if err = view.ValidateAssignment(winner.Assignment); err != nil {
		t.Fatalf("winner physical assignment: %v", err)
	}
	deltas, err := view.DenseDeltas(winner.Assignment)
	if err != nil {
		t.Fatal(err)
	}
	predictedDPS, err := boundPanel.EvaluateDPS(deltas)
	if err != nil {
		t.Fatal(err)
	}
	if math.Abs(predictedDPS-winner.Expected) > 1e-6 {
		t.Fatalf("saved formula mean changed: %.12f vs %.12f", predictedDPS, winner.Expected)
	}
	score := search.ScoredAssignment{Assignment: winner.Assignment, DPS: predictedDPS}
	candidate := Candidate{Score: score, Context: target, Handle: boundHandle, Index: view, Packages: packages}
	renderer, err := FinalistRenderer(request, base, []Candidate{candidate})
	if err != nil {
		t.Fatal(err)
	}
	rendered, err := renderer(score, 1, 1)
	if err != nil {
		t.Fatal(err)
	}
	nativeContext, err := setcontext.New(binding, rendered.Text)
	if err != nil {
		t.Fatal(err)
	}
	nativeRoot := filepath.Join(captures, "winner")
	if err = os.Mkdir(nativeRoot, 0700); err != nil {
		t.Fatal(err)
	}
	nativeProvider, err := setcontext.NewEffectEngineProvider(binding, nativeRoot)
	if err != nil {
		t.Fatal(err)
	}
	nativeSession, err := setcontext.NewSession(nativeProvider.Capture, 2)
	if err != nil {
		t.Fatal(err)
	}
	nativeHandle, err := nativeSession.Resolve(ctx, nativeContext, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	nativeMembers, err := nativeHandle.EnergyMembers()
	if err != nil {
		t.Fatal(err)
	}
	if len(nativeMembers) != 2 {
		t.Fatalf("native capture returned %d seed members, want 2", len(nativeMembers))
	}
	nativePanel, err := nativeHandle.SearchPanel()
	if err != nil {
		t.Fatal(err)
	}
	nativeScore, err := nativePanel.Evaluate(make([]float64, len(nativePanel.Coordinates())))
	if err != nil {
		t.Fatal(err)
	}
	actors := make([]string, len(request.Wearers))
	for i, wearer := range request.Wearers {
		actors[i] = wearer.WearerKey
	}
	sort.Strings(actors)
	perSeedDPS := make(map[uint64]float64, len(nativeMembers))
	for _, member := range nativeMembers {
		panel, compileErr := evaluator.CompileMembers(actors, []uint64{member.Seed}, []contracts.IRSeedMember{member})
		if compileErr != nil {
			t.Fatal(compileErr)
		}
		seedScore, evaluateErr := panel.Evaluate(make([]float64, len(panel.Coordinates())))
		if evaluateErr != nil {
			t.Fatal(evaluateErr)
		}
		perSeedDPS[member.Seed] = seedScore.MeanDPS
	}
	if err = nativeProvider.Close(); err != nil {
		t.Fatal(err)
	}
	for _, seed := range request.Stochastic.Seeds {
		neutralMember := neutralBySeed[seed]
		nativeMember, found := memberForSeed(nativeMembers, seed)
		if !found {
			t.Fatalf("native capture omitted seed %d", seed)
		}
		row, _ := json.Marshal(map[string]any{
			"seed": seed, "native_dps": perSeedDPS[seed],
			"neutral_duration_ms": neutralMember.DurationMS, "native_duration_ms": nativeMember.DurationMS,
			"duration_equal":          neutralMember.DurationMS == nativeMember.DurationMS,
			"neutral_topology_sha256": neutralMember.TopologySHA256, "native_topology_sha256": nativeMember.TopologySHA256,
			"topology_equal": neutralMember.TopologySHA256 == nativeMember.TopologySHA256,
			"codes":          codes,
		})
		fmt.Printf("SEED_RESPONSE %s\n", row)
	}
	meanRow, _ := json.Marshal(map[string]any{
		"predicted_mean_dps": predictedDPS, "native_mean_dps": nativeScore.MeanDPS,
		"residual_dps":         predictedDPS - nativeScore.MeanDPS,
		"native_sample_sd_dps": nativeScore.SampleSDDPS, "native_standard_error_dps": nativeScore.StandardErrorDPS,
		"expected_formula_mean_dps": winner.Expected, "formula_mean_drift_dps": predictedDPS - winner.Expected,
		"codes": codes, "uncertainty": boundPanel.OpaqueReasons(),
	})
	fmt.Printf("SEED_RESPONSE_MEAN %s\n", meanRow)
}

func memberForSeed(members []contracts.IRSeedMember, seed uint64) (contracts.IRSeedMember, bool) {
	for _, member := range members {
		if member.Seed == seed {
			return member, true
		}
	}
	return contracts.IRSeedMember{}, false
}
