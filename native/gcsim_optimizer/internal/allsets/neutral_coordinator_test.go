package allsets

// Synthetic inventory oracle bound to the active SOURCE set implementations,
// not to a simulated team. Only one wearer's HP enters this deliberately tiny
// graph; all four physical assignments remain legal. No engine invocation,
// ordinary DPS acceptance or account mutation occurs in these tests.
import (
	"context"
	"encoding/json"
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
	"math"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestNeutralSearchIndependentOfResultLimits(t *testing.T) {
	index, base, originalSources, capture, cfg := coordinatorFixture(t)
	// Use unique set identities so this small synthetic inventory has one
	// no-bonus package group and needs no source-rule fixture. The duplicated
	// slot choices still exercise real candidate search and finalist polish.
	indexCopy := *index
	indexCopy.Artifacts = append([]domain.IndexedArtifact(nil), index.Artifacts...)
	for i := range indexCopy.Artifacts {
		indexCopy.Artifacts[i].SetUID = fmt.Sprintf("testset_%d", indexCopy.Artifacts[i].ArtifactID)
	}
	for i := range indexCopy.Wearers {
		indexCopy.Wearers[i].SelectedSets = nil
	}
	index = &indexCopy
	sources := &seteffects.SourceCatalog{
		EngineSHA256:         originalSources.EngineSHA256,
		SourceManifestSHA256: originalSources.SourceManifestSHA256,
		CatalogSHA256:        originalSources.CatalogSHA256,
	}
	provider := func(ctx context.Context, target *setcontext.Context) (setcontext.Capture, error) {
		result, err := capture(ctx, target)
		if err != nil {
			return result, err
		}
		actors := target.Actors()
		for i := range result.Effects {
			member := result.Members[i]
			frames := int(math.Round(float64(member.DurationMS) * 60 / 1000))
			if frames < 1 {
				frames = 1
			}
			neutral := &contracts.NeutralInputs{
				Reads: []contracts.NeutralReadRoot{}, ReadsComplete: true,
				SchemaVersion: 1,
				Context:       contracts.NeutralContext{DurationFrames: frames, NoSets: true, Active: 0, Moonsign: 2},
				Ledger:        contracts.CombatEventLedger{Events: []contracts.CombatEvent{}},
				Stats:         []contracts.NeutralStatInput{}, Hits: []contracts.NeutralHitPoint{},
				Effects: []contracts.NeutralEffectPoint{},
				World:   &contracts.NeutralWorldLedger{Complete: true, States: []contracts.NeutralWorldState{{Order: 1, Active: 0, Modifiers: []contracts.NeutralModifierIdentity{}}}},
			}
			for actor, key := range actors {
				neutral.Context.Characters = append(neutral.Context.Characters, contracts.NeutralCharacter{
					Index: actor, Key: key,
					Base:  contracts.EventValue{Kind: "object", Fields: map[string]contracts.EventValue{}},
					Stats: contracts.EventValue{Kind: "object", Fields: map[string]contracts.EventValue{}},
					Facts: map[string]contracts.EventValue{},
				})
			}
			result.Effects[i].Neutral = neutral
		}
		return result, nil
	}
	cfg.MaxSearchExpansions = 2000
	cfg.Search = search.Config{FirstFrontierWidth: 2, RecheckFrontierWidth: 2, MaxExpandedPerActor: 12, FinalistLimit: 5, MaxCycles: 1, PairFinalistLimit: 8}

	type coreResult struct {
		Expansions    int
		StopReason    string
		Leader        search.ScoredAssignment
		Work          []ContextWork
		Cycles        []NeutralCycleCoverage
		Stabilization []search.Stabilization
	}
	var baseline coreResult
	for attempt, limits := range [][2]int{{3, 2}, {5, 7}, {50, 50}} {
		cfg.ResultGroups, cfg.ResultAlternatives = limits[0], limits[1]
		result, err := RunNeutral(context.Background(), index, base, sources, provider, cfg)
		if err != nil {
			t.Fatal("result limits", limits, err)
		}
		if len(result.Finalists) > limits[0]*limits[1] {
			t.Fatalf("output exceeded %dx%d limit: %d", limits[0], limits[1], len(result.Finalists))
		}
		work := append([]ContextWork(nil), result.Work...)
		for i := range work {
			work[i].SearchSeconds = 0
			work[i].CaptureSeconds = 0
		}
		current := coreResult{
			Expansions: result.SearchExpansions, StopReason: result.StopReason,
			Leader: result.Leader.Score, Work: work,
			Cycles:        append([]NeutralCycleCoverage(nil), result.NeutralCycles...),
			Stabilization: append([]search.Stabilization(nil), result.NeutralStabilization...),
		}
		if len(current.Stabilization) == 0 {
			t.Fatalf("no fixed core finalist was stabilized at %dx%d", limits[0], limits[1])
		}
		if attempt == 0 {
			baseline = current
			continue
		}
		if !reflect.DeepEqual(current, baseline) {
			t.Fatalf("core search changed at %dx%d output limits", limits[0], limits[1])
		}
	}
}

func TestNeutralCoordinatorOneCaptureInventoryOracle(t *testing.T) {
	sourcePath := os.Getenv("GTT_RULE_SOURCE_BUNDLE")
	if sourcePath == "" {
		t.Skip("managed active-source envelope only")
	}
	read := func(path string, out any) {
		t.Helper()
		b, e := os.ReadFile(path)
		if e != nil {
			t.Fatal(e)
		}
		if e = json.Unmarshal(b, out); e != nil {
			t.Fatal(e)
		}
	}
	var bundle seteffects.SourceBundle
	read(sourcePath, &bundle)
	var req contracts.OptimizerRequest
	var compact contracts.CompactIR
	root := filepath.Join("..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1")
	read(filepath.Join(root, "request_v1.json"), &req)
	read(filepath.Join(root, "compact_ir_v1.json"), &compact)
	req.Engine.ArtifactSHA256 = bundle.EngineSHA256
	req.Engine.SourceManifestSHA256 = bundle.SourceManifestSHA256
	sources, e := seteffects.CompileSourceBundle(bundle, req.Engine, bundle.CatalogSHA256)
	if e != nil {
		t.Fatal(e)
	}
	sets := []string{"obsidiancodex", "tenacityofthemillelith", "maidenbeloved", "wandererstroupe"}
	actors := []string{}
	config := ""
	for i := range req.Wearers {
		w := &req.Wearers[i]
		w.SelectedSetUID = sets[i]
		w.SelectedSets = nil
		actors = append(actors, w.WearerKey)
		config += fmt.Sprintf("%s char lvl=90/90;\n%s add set=%q count=4;\n%s add stats hp=1;\n", w.WearerKey, w.WearerKey, sets[i], w.WearerKey)
	}
	config += "options ignore_burst_energy=true;\nactive actor_a;\nactor_a attack;\n"
	// Four original copies per slot and a fifth excellent isolated piece. These
	// unmatched source families can legally form the optimized no-bonus option.
	extraSets := []string{"nightoftheskysunveiling", "emblemofseveredfate", "goldentroupe", "huskofopulentdreams", "deepwoodmemories"}
	hp := map[int64]float64{}
	for i := range req.Artifacts {
		a := &req.Artifacts[i]
		a.SetUID = sets[i/5]
		a.Substats = []contracts.StatValue{}
		if a.MainStat.Key == "damage_bonus" {
			a.MainStat.Key = "pyro_damage_bonus"
		}
		if a.MainStat.Key == "hp_percent" {
			x, _ := strconv.ParseFloat(a.MainStat.Value, 64)
			hp[a.ArtifactID] = x
		}
	}
	for slot := 0; slot < 5; slot++ {
		a := req.Artifacts[slot]
		a.ArtifactID = int64(100 + slot)
		a.SetUID = extraSets[slot]
		a.Substats = []contracts.StatValue{{Key: "hp_percent", Value: "0.8"}}
		hp[a.ArtifactID] = hp[req.Artifacts[slot].ArtifactID] + .8
		req.Artifacts = append(req.Artifacts, a)
	}
	index, e := domain.Build(req, nil)
	if e != nil {
		t.Fatal(e)
	}
	seeds := []uint64{}
	for i := range compact.Members {
		m := &compact.Members[i]
		seeds = append(seeds, m.Seed)
		m.Nodes = append(m.Nodes,
			contracts.IRNode{NodeID: 8, Operation: "constant", Value: "0", Inputs: []contracts.IRInput{}},
			contracts.IRNode{NodeID: 9, Operation: "multiply", Inputs: []contracts.IRInput{{NodeID: 3, Relation: "scale"}, {NodeID: 8, Relation: "effect"}}},
			contracts.IRNode{NodeID: 10, Operation: "add", Inputs: []contracts.IRInput{{NodeID: 7, Relation: "neutral"}, {NodeID: 9, Relation: "effect"}}})
		m.Channels[0].RootNodeID = 10
	}
	base, e := setcontext.New(setcontext.Binding{Engine: req.Engine, CatalogSHA256: sources.CatalogSHA256, ReferenceStatsSHA256: contracts.TextSHA256(config), Seeds: seeds}, config)
	if e != nil {
		t.Fatal(e)
	}
	calls := 0
	provider := func(ctx context.Context, target *setcontext.Context) (setcontext.Capture, error) {
		calls++
		if err := ctx.Err(); err != nil {
			return setcontext.Capture{}, err
		}
		for _, actor := range actors {
			if len(target.Sets(actor)) != 0 {
				return setcontext.Capture{}, fmt.Errorf("per-package recapture forbidden")
			}
		}
		capture := setcontext.Capture{ContextSHA256: target.Key(), ConfigSHA256: target.ConfigSHA256(), EngineBindingSHA256: req.Engine.BindingSHA256, Members: compact.Members}
		for _, m := range compact.Members {
			n := &contracts.NeutralInputs{Context: contracts.NeutralContext{NoSets: true, Active: 0, Moonsign: 2}, Ledger: contracts.CombatEventLedger{Events: []contracts.CombatEvent{}}, World: &contracts.NeutralWorldLedger{Complete: true, States: []contracts.NeutralWorldState{{Order: 1, Active: 0, Modifiers: []contracts.NeutralModifierIdentity{}}}}, Stats: []contracts.NeutralStatInput{{NodeID: 8, Kind: "stat", Owner: actors[0], Stat: "hp%", Point: contracts.NeutralInputPoint{Order: 20, Frame: 10, Mode: "stat"}}}}
			for i, actor := range actors {
				n.Context.Characters = append(n.Context.Characters, contracts.NeutralCharacter{Index: i, Key: actor, Base: contracts.EventValue{Kind: "object", Fields: map[string]contracts.EventValue{}}, Facts: map[string]contracts.EventValue{"Weapon": {Kind: "object", Fields: map[string]contracts.EventValue{"Class": {Kind: "number", Type: "github.com/genshinsim/gcsim/pkg/core/info.WeaponClass", Number: 0}}}}})
			}
			n.Context.DurationFrames = int(math.Round(float64(m.DurationMS) * 60 / 1000))
			capture.Effects = append(capture.Effects, contracts.EffectInputsOutput{SchemaVersion: 1, Capability: contracts.EffectInputsCapability, ContextSHA256: target.ConfigSHA256(), InputConfigSHA256: target.ConfigSHA256(), SourceManifestBodySHA256: req.Engine.SourceManifestSHA256, Seed: strconv.FormatUint(m.Seed, 10), CharacterKeys: actors, Neutral: n})
		}
		return capture, nil
	}
	cfg := CoordinatorConfig{FinalistLimit: 5, MaxSearchExpansions: 300000, SearchTime: time.Minute, Search: search.Config{FirstFrontierWidth: 1, RecheckFrontierWidth: 1, MaxExpandedPerActor: 5000, FinalistLimit: 5, MaxCycles: 2, PairFinalistLimit: 8}}
	result, e := RunNeutral(context.Background(), index, base, sources, provider, cfg)
	if e != nil {
		t.Fatal(e)
	}
	if calls != 1 || result.CaptureMembers != len(seeds) {
		t.Fatal("ordinary package recaptures", calls, result.CaptureMembers)
	}
	if len(result.NeutralPackageJoint) == 0 || result.SearchExpansions > cfg.MaxSearchExpansions {
		t.Fatal("joint package lane missing or renewed global allowance", result.NeutralPackageJoint, result.SearchExpansions)
	}
	for _, lane := range result.NeutralPackageJoint {
		if !lane.Finished || !lane.Heuristic || lane.Roots > jointPackageWidth || lane.Refined > jointPackageWidth || lane.Proposals == 0 {
			t.Fatal("joint package lane completion/heuristic/frontier contract", lane)
		}
	}
	if result.Leader.Index == nil || result.Leader.Index.ValidateAssignment(result.Leader.Score.Assignment) != nil {
		t.Fatal("illegal/missing leader")
	}
	if result.Leader.Index.Incumbent != result.Leader.Score.Assignment {
		t.Fatal("stale joint-search seed")
	}
	// A completed actor block must be the next actor's actual anchor, not
	// another copy of the cycle-start team. This tiny oracle improves actor0,
	// so retaining a stale anchor is observably different even without RNG.
	var blockStart, previousComplete ContextWork
	nextActor, completedBlocks := 0, 0
	insideBlock := false
	for _, work := range result.Work {
		if !strings.HasPrefix(work.Lane, "neutral_actor_") {
			continue
		}
		if work.Lane == fmt.Sprintf("neutral_actor_%d:anchor", nextActor) && !insideBlock {
			if nextActor > 0 && (work.Assignment != previousComplete.Assignment || work.FormulaDPS != previousComplete.FormulaDPS) {
				t.Fatal("next actor uses stale conditional team", work, previousComplete)
			}
			blockStart, insideBlock = work, true
		} else if work.Lane == fmt.Sprintf("neutral_actor_%d:complete", nextActor) && insideBlock {
			if work.FormulaDPS < blockStart.FormulaDPS {
				t.Fatal("actor block decreased the incumbent", blockStart, work)
			}
			if completedBlocks == 0 && work.FormulaDPS <= blockStart.FormulaDPS {
				t.Fatal("fixture did not exercise a changed actor anchor")
			}
			previousComplete, insideBlock = work, false
			nextActor = (nextActor + 1) % 4
			completedBlocks++
		} else {
			t.Fatal("incomplete/out-of-order actor block", nextActor, work.Lane)
		}
	}
	if insideBlock || completedBlocks != 4*len(result.NeutralCycles) {
		t.Fatal("missing sequential anchor coverage", completedBlocks, result.NeutralCycles)
	}
	if result.Leader.Packages[0].Key() != "none" {
		t.Fatal("strong isolated pieces excluded", result.Leader.Packages[0])
	}
	// Neutral views must cross the SAME ordinary-finalist rendering boundary as
	// the CLI, including a winner with no bonus. Do not reassemble a second
	// research-only config or carry source bonus values into artifact stat rows.
	req.Context.PreparedConfig.Text = base.Config()
	render, e := FinalistRenderer(req, base, result.Finalists)
	if e != nil {
		t.Fatal(e)
	}
	frame := func(text string) string {
		rows := []string{}
		for _, row := range strings.Split(text, "\n") {
			if strings.TrimSpace(row) != "" && !strings.Contains(row, " add set=") && !strings.Contains(row, " add stats ") && !strings.HasPrefix(row, "options ") {
				rows = append(rows, row)
			}
		}
		return strings.Join(rows, "\n")
	}
	for _, candidate := range result.Finalists {
		rendered, err := render(candidate.Score, 500, 2)
		if err != nil {
			t.Fatal("neutral finalist cannot reach ordinary verifier", err)
		}
		if frame(rendered.Text) != frame(base.Config()) || !strings.Contains(rendered.Text, "ignore_burst_energy=true iteration=500 workers=2") || contracts.TextSHA256(rendered.Text) != rendered.SHA256 {
			t.Fatal("neutral finalist changed run frame/options/identity")
		}
		for actor, pack := range candidate.Packages {
			prefix := actors[actor] + " add set="
			if strings.Count(rendered.Text, prefix) != len(pack.Sets) {
				t.Fatal("neutral finalist retained or lost set bonus", actors[actor], pack.Key())
			}
		}
	}
	// Every complete actor-A slot vector is physically extendable: four pieces
	// remain per slot for three other wearers. Other source effects have no team
	// HP bonus on this empty tape. Enumerate all5^5 vectors, independently of the
	// region scheduler; obtain source bonus values from the neutral model itself.
	changes := map[string][]setcontext.Set{}
	for _, a := range actors {
		changes[a] = nil
	}
	neutral, e := base.Replace(changes)
	if e != nil {
		t.Fatal(e)
	}
	session, _ := setcontext.NewSession(provider, len(seeds))
	h, e := session.Resolve(context.Background(), neutral, nil, nil)
	if e != nil {
		t.Fatal(e)
	}
	model, e := setcontext.NewNeutralModel(h, sources)
	if e != nil {
		t.Fatal(e)
	}
	oracleModels := map[string]*setcontext.Handle{}
	reference := 0.0
	for _, id := range index.Incumbent[0] {
		reference += hp[id]
	}
	best := math.Inf(-1)
	ids := [5]int64{}
	var enumerate func(int)
	enumerate = func(slot int) {
		if slot < 5 {
			for _, id := range index.CandidateIDsBySlot[slot] {
				ids[slot] = id
				enumerate(slot + 1)
			}
			return
		}
		counts := map[string]int{}
		sum := 0.0
		for _, id := range ids {
			uid, _ := index.ArtifactSetUID(id)
			counts[uid]++
			sum += hp[id]
		}
		keys := []string{}
		for key, count := range counts {
			if count >= 2 {
				keys = append(keys, key)
			}
		}
		sort.Strings(keys)
		targetSets := []setcontext.Set{}
		signature := []string{}
		for _, key := range keys {
			count := 2
			if counts[key] >= 4 {
				count = 4
			}
			targetSets = append(targetSets, setcontext.Set{UID: key, Count: count})
			signature = append(signature, fmt.Sprintf("%s:%d", key, count))
		}
		key := strings.Join(signature, "+")
		handle, ok := oracleModels[key]
		if !ok {
			target, e := base.Replace(map[string][]setcontext.Set{actors[0]: targetSets})
			if e != nil {
				t.Fatal(e)
			}
			var boundaries []string
			handle, boundaries, e = model.Resolve(target)
			if e != nil || handle == nil {
				t.Fatal(key, boundaries, e)
			}
			oracleModels[key] = handle
		}
		score, e := handle.EvaluateDPS(map[string]float64{actors[0] + ".hp_percent": sum - reference})
		if e != nil {
			t.Fatal(e)
		}
		best = math.Max(best, score)
	}
	enumerate(0)
	if math.Abs(result.Leader.Score.DPS-best) > 1e-9 {
		t.Fatal("inventory oracle missed", result.Leader.Score.DPS, best)
	}
	for _, c := range result.Finalists {
		if c.Score.Assignment == result.Initial.Score.Assignment {
			continue
		}
		found := false
		for _, s := range result.NeutralStabilization {
			if s.Leader.Assignment == c.Score.Assignment && s.SingleStationary {
				found = true
			}
		}
		if !found {
			t.Fatal("unpolished finalist reintroduced", c.Score)
		}
	}
	t.Logf("one-capture tiny oracle: modeled=%d refinements=%d work=%d best=%g stop=%s seconds=%.3f", result.Queued, len(result.Work), result.SearchExpansions, best, result.StopReason, result.TotalSeconds)
	for _, cycle := range result.NeutralCycles {
		if cycle.Prepared != cycle.Total || cycle.NotPrepared != 0 || cycle.NotProcessed != 0 || cycle.Queued != cycle.Processed+cycle.ModelDeferred {
			t.Fatal("completed coordinate pass concealed work", cycle)
		}
	}
	// The whole run owns one budget. A package with many legal slot patterns
	// must not overdraw it, and unstarted packages cannot disappear from coverage.
	for _, limit := range []int{1, 3, 24} {
		cfg.MaxSearchExpansions = limit
		beforeCalls := calls
		partial, err := RunNeutral(context.Background(), index, base, sources, provider, cfg)
		if err != nil || calls-beforeCalls != 1 || partial.SearchExpansions > limit || partial.StopReason != "search_expansion_budget" || len(partial.Finalists) == 0 {
			t.Fatal("shared budget/partial incumbent", limit, partial.SearchExpansions, partial.StopReason, err)
		}
		if partial.Pending == 0 || len(partial.NeutralCycles) == 0 {
			t.Fatal("missing unstarted package work", limit, partial.NeutralCycles)
		}
		for _, cycle := range partial.NeutralCycles {
			if cycle.Prepared+cycle.NotPrepared != cycle.Total || cycle.Processed+cycle.NotProcessed+cycle.ModelDeferred != cycle.Queued || cycle.Queued+cycle.ModelUnavailable+cycle.ReservationDeferred != cycle.Prepared {
				t.Fatal("partial coverage accounting", cycle)
			}
		}
	}
}
