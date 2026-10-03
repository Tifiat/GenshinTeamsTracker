package allsets

// Temporary opt-in full-inventory PROFILE of the source coordinator, not a
// product test. It consumes the already captured saved Flins seed and current
// inventory (reference vectors checked by inventory_profile.py), makes no engine
// calls and retains no generated files. Remove the research gate after installed
// single-team acceptance; keep algorithmic oracles in neutral_coordinator_test.
import (
	"context"
	"encoding/json"
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

func TestNeutralCoordinatorSavedInventoryProfile(t *testing.T) {
	if os.Getenv("GTT_NEUTRAL_INVENTORY_REQUEST") == "" {
		t.Skip("explicit managed inventory profile only")
	}
	if !t.Run("restricted", func(t *testing.T) { profileNeutralInventory(t, true) }) {
		return
	}
	t.Run("expanded", func(t *testing.T) { profileNeutralInventory(t, false) })
}

func profileNeutralInventory(t *testing.T, restricted bool) {
	input := os.Getenv("GTT_NEUTRAL_INVENTORY_REQUEST")
	if input == "" {
		t.Skip("explicit managed full-inventory profile only")
	}
	job := os.Getenv("GTT_SCRATCH_DIR")
	if filepath.Dir(input) != job || job != os.Getenv("GTT_NEUTRAL_CAPTURE_DIR") {
		t.Fatal("unowned profile input")
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
	var req contracts.OptimizerRequest
	var source seteffects.SourceBundle
	read(input, &req)
	read(os.Getenv("GTT_RULE_SOURCE_BUNDLE"), &source)
	suffixes := []string{""}
	if os.Getenv("GTT_NEUTRAL_TWO_SEEDS") == "1" {
		suffixes = append(suffixes, "-second")
	}
	var members, controls []contracts.IRSeedMember
	var effects []contracts.EffectInputsOutput
	for _, suffix := range suffixes {
		var member, control contracts.IRSeedMember
		var effect contracts.EffectInputsOutput
		read(filepath.Join(job, "neutral-member"+suffix+".json"), &member)
		read(filepath.Join(job, "neutral-member"+suffix+".json.effects.json"), &effect)
		read(filepath.Join(job, "control-member"+suffix+".json"), &control)
		members, controls, effects = append(members, member), append(controls, control), append(effects, effect)
	}
	sort.Slice(members, func(i, j int) bool { return members[i].Seed < members[j].Seed })
	sort.Slice(controls, func(i, j int) bool { return controls[i].Seed < controls[j].Seed })
	seeds := make([]uint64, len(members))
	for i := range members {
		seeds[i] = members[i].Seed
	}
	actors := make([]string, len(req.Wearers))
	for i := range req.Wearers {
		actors[i] = req.Wearers[i].WearerKey
	}
	sort.Strings(actors)
	controlPanel, e := evaluator.CompileMembers(actors, seeds, controls)
	if e != nil {
		t.Fatal(e)
	}
	controlDPS, e := controlPanel.EvaluateDPS(make([]float64, len(controlPanel.Coordinates())))
	if e != nil {
		t.Fatal(e)
	}
	// Keep the capture's STRONG reference vectors, but start search from the
	// independently saved WEAK twenty IDs. ForPackages preserves coordinate
	// reference stats; replacing the request baseline would silently mis-score.
	var witness struct {
		Cases []struct {
			Name string                      `json:"name"`
			IDs  map[string]map[string]int64 `json:"artifact_ids"`
		} `json:"cases"`
	}
	read(filepath.Join("..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1", "flins_virtual_artifact_crosscheck_lineage5_v1.json"), &witness)
	var weak map[string]map[string]int64
	keep := map[int64]bool{}
	for _, c := range witness.Cases {
		if c.Name == "virtual_top1" {
			weak = c.IDs
		}
		for _, slots := range c.IDs {
			for _, id := range slots {
				keep[id] = true
			}
		}
	}
	if len(weak) != 4 {
		t.Fatal("missing weak control")
	}
	if restricted {
		items := req.Artifacts[:0:0]
		for _, item := range req.Artifacts {
			if keep[item.ArtifactID] {
				items = append(items, item)
			}
		}
		req.Artifacts = items
	}
	index, e := domain.Build(req, nil)
	if e != nil {
		t.Fatal(e)
	}
	sources, e := seteffects.CompileSourceBundle(source, req.Engine, source.CatalogSHA256)
	if e != nil {
		t.Fatal(e)
	}
	neutralText, e := os.ReadFile(filepath.Join(job, "neutral.txt"))
	if e != nil {
		t.Fatal(e)
	}
	base, e := setcontext.New(setcontext.Binding{Engine: req.Engine, CatalogSHA256: source.CatalogSHA256, ReferenceStatsSHA256: req.Context.PreparedConfig.SHA256, Seeds: seeds}, string(neutralText))
	if e != nil {
		t.Fatal(e)
	}
	initial := map[string][]setcontext.Set{}
	var assignment domain.Assignment
	var packages [4]domain.Package
	for actor, wearer := range req.Wearers {
		counts := map[string]int{}
		for slot, key := range []string{"flower", "plume", "sands", "goblet", "circlet"} {
			id := weak[wearer.WearerKey][key]
			uid, ok := index.ArtifactSetUID(id)
			if !ok {
				t.Fatal("weak item absent", id)
			}
			assignment[actor][slot] = id
			counts[uid]++
		}
		keys := []string{}
		for uid, n := range counts {
			if n >= 2 {
				keys = append(keys, uid)
			}
		}
		sort.Strings(keys)
		for _, uid := range keys {
			count := 2
			if counts[uid] >= 4 {
				count = 4
			}
			packages[actor].Sets = append(packages[actor].Sets, contracts.SetRequirement{SetUID: uid, Count: count})
			initial[wearer.WearerKey] = append(initial[wearer.WearerKey], setcontext.Set{UID: uid, Count: count})
		}
	}
	index, e = index.ForPackages(packages, assignment, index.Coordinates)
	if e != nil {
		t.Fatal(e)
	}
	base, e = base.Replace(initial)
	if e != nil {
		t.Fatal(e)
	}
	calls := 0
	provider := func(_ context.Context, target *setcontext.Context) (setcontext.Capture, error) {
		calls++
		for _, effect := range effects {
			if target.ConfigSHA256() != effect.InputConfigSHA256 {
				t.Fatalf("profile capture/config mismatch %s %s", target.ConfigSHA256(), effect.InputConfigSHA256)
			}
		}
		return setcontext.Capture{ContextSHA256: target.Key(), ConfigSHA256: target.ConfigSHA256(), EngineBindingSHA256: req.Engine.BindingSHA256, Members: members, Effects: effects}, nil
	}
	config := CoordinatorConfig{FinalistLimit: 7, MaxSearchExpansions: 8000000, SearchTime: 60 * time.Second, Search: search.DefaultConfig()}
	// Explicit diagnostic opt-in: finish the configured passes, retaining only
	// the managed job/test watchdog. Production deadlines remain unchanged.
	if os.Getenv("GTT_NEUTRAL_FINISH_PASSES") == "1" {
		config.SearchTime = 0
	}
	result, e := RunNeutral(context.Background(), index, base, sources, provider, config)
	if e != nil {
		t.Fatal(e)
	}
	if calls != 1 || result.Leader.Index == nil {
		t.Fatal("profile capture/leader missing", calls)
	}
	if e = result.Leader.Index.ValidateAssignment(result.Leader.Score.Assignment); e != nil {
		t.Fatal(e)
	}
	if result.Leader.Score.DPS+1e-8 < result.Initial.Score.DPS {
		t.Fatal("profile lost incumbent")
	}
	// Minimal diagnostic identity and the five expensive frontier records only;
	// never publish the full private inventory or thousands of work rows here.
	inventorySHA, e := contracts.CanonicalSHA256(req.Artifacts)
	if e != nil {
		t.Fatal(e)
	}
	work := append([]ContextWork(nil), result.Work...)
	// Hash the complete search receipt without clocks, not only the winner.
	// The paired preparation experiment must preserve every recorded work row.
	for i := range work {
		work[i].SearchSeconds = 0
		work[i].CaptureSeconds = 0
	}
	workSHA, e := contracts.CanonicalSHA256(work)
	if e != nil {
		t.Fatal(e)
	}
	work = append([]ContextWork(nil), result.Work...)
	sort.SliceStable(work, func(i, j int) bool { return work[i].SearchSeconds > work[j].SearchSeconds })
	type cost struct {
		Lane        string
		Packages    [4]string
		Seconds     float64
		Work, Nodes int
		Pending     int64
	}
	slow := []cost{}
	for _, w := range work[:min(5, len(work))] {
		slow = append(slow, cost{w.Lane, w.Packages, w.SearchSeconds, w.Expansions, w.ReducedNodes, w.BudgetUnexpanded})
	}
	row := struct {
		Scope, Stop, InventorySHA                                                      string
		Artifacts, Captures, Work, Pending, Unknown                                    int
		Seconds, InitialDPS, LeaderDPS, ProposalSeconds, SeedSeconds, PotentialSeconds float64
		JointRan                                                                       bool
		JointSeconds                                                                   float64
		Model                                                                          setcontext.NeutralModelStats
		Cycles                                                                         []NeutralCycleCoverage
		Assignment                                                                     domain.Assignment
		SlowFrontiers                                                                  []cost
		Boundaries                                                                     []string
		Restricted                                                                     bool
		InitialAssignment                                                              domain.Assignment
		FinalPackages                                                                  [4]domain.Package
		WorkSHA                                                                        string
		Finalists                                                                      []search.ScoredAssignment
		PanelSeeds                                                                     []uint64
		CaptureMembers                                                                 int
		ControlDPS                                                                     float64
	}{
		Scope: "weak_start_saved_seed_panel_source_not_product_acceptance", Stop: result.StopReason, InventorySHA: inventorySHA, Restricted: restricted,
		PanelSeeds: seeds, CaptureMembers: len(members), ControlDPS: controlDPS,
		Artifacts: len(req.Artifacts), Captures: calls, Work: result.SearchExpansions, Pending: result.Pending, Unknown: result.Unqueued,
		Seconds: result.TotalSeconds, InitialDPS: result.Initial.Score.DPS, LeaderDPS: result.Leader.Score.DPS,
		ProposalSeconds: result.ProposalSeconds, SeedSeconds: result.NeutralSeedSeconds, PotentialSeconds: result.NeutralPotentialSeconds,
		JointRan: result.NeutralJointRan, JointSeconds: result.NeutralJointSeconds, Model: result.NeutralModel,
		Cycles: result.NeutralCycles, Assignment: result.Leader.Score.Assignment, SlowFrontiers: slow, Boundaries: result.Boundaries,
		InitialAssignment: result.Initial.Score.Assignment, FinalPackages: result.Leader.Packages, WorkSHA: workSHA}
	for _, candidate := range result.Finalists {
		row.Finalists = append(row.Finalists, candidate.Score)
	}
	text, e := json.Marshal(row)
	if e != nil {
		t.Fatal(e)
	}
	t.Logf("INVENTORY_PROFILE %s", text)
	// Compare with the independent original-set capture on the SAME seed panel.
	// This is MODEL recall, not n500 or button acceptance.
	if restricted && result.Leader.Score.DPS < controlDPS-1e-6 {
		t.Fatal("restricted search missed saved legal source control; expansion stopped")
	}
}
