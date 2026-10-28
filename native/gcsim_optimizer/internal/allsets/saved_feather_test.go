package allsets

// Temporary managed diagnosis: replay the USER'S saved neutral capture, without
// an optimizer search or another engine capture. Remove with the Flins research
// helpers after acceptance; compact evidence belongs to the Go design receipt.
import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"strconv"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

func TestSavedFeatherDiagnosis(t *testing.T) {
	run := os.Getenv("GTT_SAVED_FEATHER_RUN")
	if run == "" {
		t.Skip("explicit saved-run diagnosis only")
	}
	job := os.Getenv("GTT_SCRATCH_DIR")
	if job == "" || filepath.Dir(os.Getenv("GOCACHE")) != job {
		t.Fatal("managed scratch required")
	}
	read := func(path string, value any) {
		t.Helper()
		b, e := os.ReadFile(path)
		if e != nil {
			t.Fatal(e)
		}
		if e = json.Unmarshal(b, value); e != nil {
			t.Fatal(e)
		}
	}
	var req contracts.OptimizerRequest
	var bundle seteffects.SourceBundle
	var output struct {
		Verification struct {
			Winner struct {
				Assignment domain.Assignment `json:"assignment"`
				DPS        float64           `json:"formula_dps"`
			} `json:"winner"`
		} `json:"verification"`
	}
	read(filepath.Join(run, "request.json"), &req)
	read(filepath.Join(run, "set-sources.json"), &bundle)
	read(filepath.Join(run, "optimizer-output.json"), &output)
	sha, e := contracts.CanonicalSHA256(req)
	if e != nil {
		t.Fatal(e)
	}
	sources, e := seteffects.CompileSourceBundle(bundle, req.Engine, bundle.CatalogSHA256)
	if e != nil {
		t.Fatal(e)
	}
	base, e := setcontext.New(setcontext.Binding{Engine: req.Engine, CatalogSHA256: bundle.CatalogSHA256, ReferenceStatsSHA256: sha, Seeds: req.Stochastic.Seeds}, req.Context.PreparedConfig.Text)
	if e != nil {
		t.Fatal(e)
	}
	changes := map[string][]setcontext.Set{}
	for _, w := range req.Wearers {
		changes[w.WearerKey] = nil
	}
	neutral, e := base.Replace(changes)
	if e != nil {
		t.Fatal(e)
	}
	provider := func(_ context.Context, target *setcontext.Context) (setcontext.Capture, error) {
		if target.Key() != neutral.Key() {
			t.Fatal("unexpected capture context")
		}
		capture := setcontext.Capture{ContextSHA256: target.Key(), ConfigSHA256: target.ConfigSHA256(), EngineBindingSHA256: req.Engine.BindingSHA256}
		for _, seed := range req.Stochastic.Seeds {
			path := filepath.Join(run, "verification", "contexts", "context-"+target.Key(), "seed-"+strconv.FormatUint(seed, 10), "member.json")
			var member contracts.IRSeedMember
			var effects contracts.EffectInputsOutput
			read(path, &member)
			read(path+".effects.json", &effects)
			if effects.InputConfigSHA256 != target.ConfigSHA256() {
				t.Fatal("capture identity mismatch")
			}
			capture.Members = append(capture.Members, member)
			capture.Effects = append(capture.Effects, effects)
		}
		return capture, nil
	}
	session, e := setcontext.NewSession(provider, len(req.Stochastic.Seeds))
	if e != nil {
		t.Fatal(e)
	}
	captured, e := session.Resolve(context.Background(), neutral, nil, nil)
	if e != nil {
		t.Fatal(e)
	}
	model, e := setcontext.NewNeutralModel(captured, sources)
	if e != nil {
		t.Fatal(e)
	}
	index, e := domain.Build(req, nil)
	if e != nil {
		t.Fatal(e)
	}
	assignment := output.Verification.Winner.Assignment
	var packs [4]domain.Package
	flins := -1
	for actor, w := range req.Wearers {
		if w.WearerKey == "flins" {
			flins = actor
		}
		counts := map[string]int{}
		for _, id := range assignment[actor] {
			uid, ok := index.ArtifactSetUID(id)
			if !ok {
				t.Fatal("missing artifact")
			}
			counts[uid]++
		}
		changes[w.WearerKey] = nil
		for uid, count := range counts {
			if count < 2 {
				continue
			}
			if count >= 4 {
				count = 4
			} else {
				count = 2
			}
			packs[actor].Sets = append(packs[actor].Sets, contracts.SetRequirement{SetUID: uid, Count: count})
			changes[w.WearerKey] = append(changes[w.WearerKey], setcontext.Set{UID: uid, Count: count})
		}
	}
	if flins < 0 || assignment[flins][1] != 1534 {
		t.Fatal("unexpected winner")
	}
	target, e := base.Replace(changes)
	if e != nil {
		t.Fatal(e)
	}
	h, codes, e := model.Resolve(target)
	if e != nil || h == nil {
		t.Fatal(e, codes)
	}
	panel, e := h.SearchPanel()
	if e != nil {
		t.Fatal(e)
	}
	view, e := index.ForPackages(packs, assignment, panel.Coordinates())
	if e != nil {
		t.Fatal(e)
	}
	dense, e := view.DenseDeltas(assignment)
	if e != nil {
		t.Fatal(e)
	}
	original, e := panel.EvaluateDPS(dense)
	if e != nil {
		t.Fatal(e)
	}
	if math.Abs(original-output.Verification.Winner.DPS) > 1e-6 {
		t.Fatalf("saved formula mismatch %g vs %g", original, output.Verification.Winner.DPS)
	}
	for _, id := range []int64{1534, 1535, 2, 1533, 1536} {
		candidate := assignment
		candidate[flins][1] = id
		x, e := view.DenseDeltas(candidate)
		if e != nil {
			t.Fatal(e)
		}
		dps, e := panel.EvaluateDPS(x)
		if e != nil {
			t.Fatal(e)
		}
		fmt.Printf("FEATHER_FORMULA id=%d dps=%.12f delta=%.12f\n", id, dps, dps-original)
	}
	for _, delta := range []struct {
		key   string
		value float64
	}{{"atk_percent", -.035}, {"crit_rate", .008}, {"crit_damage", .032}, {"hp", 239}} {
		x := append([]float64(nil), dense...)
		for i, coordinate := range panel.Coordinates() {
			if coordinate == "flins."+delta.key {
				x[i] += delta.value
			}
		}
		dps, e := panel.EvaluateDPS(x)
		if e != nil {
			t.Fatal(e)
		}
		fmt.Printf("FEATHER_COMPONENT %s=%g delta_dps=%.12f\n", delta.key, delta.value, dps-original)
	}
	// The existing per-wearer refiner must be tested at the FINAL team anchor,
	// not at the earlier package-screen anchor used in the two-cycle run.
	solver, e := search.NewInventory(view, panel, search.DefaultConfig())
	if e != nil {
		t.Fatal(e)
	}
	started := time.Now()
	local, e := solver.RefineCandidates(context.Background(), assignment, flins, 20000)
	if e != nil || len(local.Step.Finalists) == 0 {
		t.Fatal(e)
	}
	best := local.Step.Finalists[0]
	fmt.Printf("FEATHER_FINAL_LOCAL dps=%.12f ids=%v work=%d stop=%s seconds=%g\n", best.DPS, best.Assignment[flins], local.Step.Expanded, local.Stop, time.Since(started).Seconds())
	if best.DPS <= original || best.Assignment[flins][1] != 1535 {
		t.Fatal("final local pass did not recover the better plume")
	}
	started = time.Now()
	joint, e := solver.RefineJoint(context.Background(), assignment, 20000)
	if e != nil {
		t.Fatal(e)
	}
	fmt.Printf("FEATHER_FINAL_JOINT dps=%.12f ids=%v work=%d budget=%v seconds=%g\n", joint.Leader.DPS, joint.Leader.Assignment[flins], joint.PairEvaluated, joint.PairBudgetExhausted, time.Since(started).Seconds())
	started = time.Now()
	stable, e := solver.Stabilize(context.Background(), assignment, 20000)
	if e != nil || !stable.SingleStationary || stable.Leader.DPS < best.DPS || stable.Leader.Assignment[flins][1] != 1535 {
		t.Fatal("terminal stabilization failed", stable, e)
	}
	fmt.Printf("FEATHER_STABILIZED dps=%.12f ids=%v work=%d stop=%s stationary=%v seconds=%g\n", stable.Leader.DPS, stable.Leader.Assignment, stable.Evaluations, stable.Stop, stable.SingleStationary, time.Since(started).Seconds())
	// A direct full N1 oracle at the returned team detects stale-owner passes.
	for actor := 0; actor < 4; actor++ {
		for slot, pool := range view.CandidateIDsBySlot {
			for _, id := range pool {
				a := stable.Leader.Assignment
				a[actor][slot] = id
				if view.ValidateAssignment(a) != nil {
					continue
				}
				x, err := view.DenseDeltas(a)
				if err != nil {
					t.Fatal(err)
				}
				v, err := panel.EvaluateDPS(x)
				if err != nil || v > stable.Leader.DPS+1e-6 {
					t.Fatal("false saved N1 certificate", a, v, err)
				}
			}
		}
	}
	var history struct {
		Work []struct {
			Assignment domain.Assignment `json:"assignment"`
		} `json:"search_work"`
	}
	read(filepath.Join(run, "optimizer-output.json"), &history)
	oldAnchor := history.Work[1].Assignment
	oldChanges := map[string][]setcontext.Set{}
	var oldPacks [4]domain.Package
	for actor, w := range req.Wearers {
		counts := map[string]int{}
		for _, id := range oldAnchor[actor] {
			uid, _ := index.ArtifactSetUID(id)
			counts[uid]++
		}
		for uid, count := range counts {
			if count < 2 {
				continue
			}
			if count >= 4 {
				count = 4
			} else {
				count = 2
			}
			oldPacks[actor].Sets = append(oldPacks[actor].Sets, contracts.SetRequirement{SetUID: uid, Count: count})
			oldChanges[w.WearerKey] = append(oldChanges[w.WearerKey], setcontext.Set{UID: uid, Count: count})
		}
	}
	oldContext, e := base.Replace(oldChanges)
	if e != nil {
		t.Fatal(e)
	}
	oldHandle, codes, e := model.Resolve(oldContext)
	if e != nil || oldHandle == nil {
		t.Fatal(e, codes)
	}
	oldPanel, e := oldHandle.SearchPanel()
	if e != nil {
		t.Fatal(e)
	}
	oldView, e := index.ForPackages(oldPacks, oldAnchor, oldPanel.Coordinates())
	if e != nil {
		t.Fatal(e)
	}
	for _, id := range []int64{1534, 1535} {
		candidate := oldAnchor
		candidate[flins][1] = id
		x, e := oldView.DenseDeltas(candidate)
		if e != nil {
			t.Fatal(e)
		}
		dps, e := oldPanel.EvaluateDPS(x)
		if e != nil {
			t.Fatal(e)
		}
		fmt.Printf("FEATHER_OLD_ANCHOR id=%d dps=%.12f\n", id, dps)
	}
}
