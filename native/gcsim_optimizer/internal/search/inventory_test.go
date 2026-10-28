package search

import (
	"container/heap"
	"context"
	"errors"
	"math"
	"strconv"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
)

func TestInventorySearchExactSmallDomainAndSpecialization(t *testing.T) {
	req, ir := searchFixtures(t)
	// This is a complete synthetic arithmetic oracle, not the source fixture's
	// intentionally unknown side effect. Unknowns get their own no-prune control.
	for i := range ir.Members {
		ir.Members[i].OpaqueBoundaries = []contracts.IROpaqueBoundary{}
		for j := range ir.Members[i].Nodes {
			if ir.Members[i].Nodes[j].Operation == "opaque_frozen" {
				ir.Members[i].Nodes[j].Operation = "constant"
			}
		}
	}
	for slot := 0; slot < 5; slot++ {
		for k := 0; k < 3; k++ {
			a := req.Artifacts[slot]
			a.ArtifactID = int64(1000 + slot*3 + k)
			a.Substats = append([]contracts.StatValue(nil), a.Substats...)
			for j := range a.Substats {
				v, _ := strconv.ParseFloat(a.Substats[j].Value, 64)
				a.Substats[j].Value = strconv.FormatFloat(v+float64((k+j)%3)/10, 'f', -1, 64)
			}
			req.Artifacts = append(req.Artifacts, a)
		}
	}
	ir.RequestSHA256, _ = contracts.CanonicalSHA256(req)
	panel, e := evaluator.Compile(req, ir)
	if e != nil {
		t.Fatal(e)
	}
	index, e := domain.Build(req, panel.Coordinates())
	if e != nil {
		t.Fatal(e)
	}
	engine, e := NewInventory(index, panel, Config{1, 1, 100000, 8, 1, 8})
	if e != nil {
		t.Fatal(e)
	}
	step, e := engine.RefineWearer(context.Background(), index.Incumbent, 0)
	if e != nil {
		t.Fatal(e)
	}
	best := math.Inf(-1)
	leaves := 0
	trial := index.Incumbent
	var enumerate func(int)
	enumerate = func(slot int) {
		if slot == 5 {
			if index.ValidateAssignment(trial) != nil {
				return
			}
			v, e := engine.score(trial)
			if e != nil {
				t.Fatal(e)
			}
			best = math.Max(best, v)
			leaves++
			return
		}
		for _, id := range index.CandidateIDsBySlot[slot] {
			trial[0][slot] = id
			enumerate(slot + 1)
		}
	}
	enumerate(0)
	if math.Abs(step.Finalists[0].DPS-best) > 1e-8 || step.BudgetUnexpanded != 0 {
		t.Fatalf("exact small inventory failed: best=%g oracle=%g leaves=%d step=%+v", step.Finalists[0].DPS, best, leaves, step)
	}
	if step.ReducedNodes == 0 || step.BoundEvaluations == 0 {
		t.Fatal("new solver not exercised")
	}
	potential, e := engine.WearerPotential(context.Background(), index.Incumbent, 0)
	if e != nil || potential.PendingPatterns != 0 || potential.Upper < best-1e-8 || potential.Priority < best-1e-8 {
		t.Fatal("package potential is below exhaustive oracle", potential, best, e)
	}
	// Nonzero foreign-owner anchor must stay frozen, not accidentally zeroed.
	delta, _ := index.DenseDeltas(index.Incumbent)
	for j := range delta {
		delta[j] = .01 * float64(j+1)
	}
	for actor, key := range panel.ActorKeys() {
		p, e := panel.ArtifactProgram(delta, actor)
		if e != nil {
			t.Fatal(e)
		}
		local := make([]float64, len(p.Coordinates()))
		for j, k := range p.Coordinates() {
			for d, all := range panel.Coordinates() {
				if k == all {
					local[j] = delta[d]
				}
			}
		}
		got, e := p.Evaluate(local)
		if e != nil {
			t.Fatal(e)
		}
		want, e := panel.EvaluateDPS(delta)
		if e != nil {
			t.Fatal(e)
		}
		if math.Abs(got-want) > 1e-8 {
			t.Fatalf("%s specialization anchor mismatch %g %g", key, got, want)
		}
	}
}

type deadlineAfterChecks struct {
	context.Context
	checks, limit int
}

func (c *deadlineAfterChecks) Err() error {
	c.checks++
	if c.checks > c.limit {
		return context.DeadlineExceeded
	}
	return nil
}

func TestInventoryDeadlineKeepsImprovementInsideWearer(t *testing.T) {
	req, ir := searchFixtures(t)
	a := req.Artifacts[0]
	a.ArtifactID = 99001
	a.Substats = []contracts.StatValue{{Key: "hp_percent", Value: "1"}}
	req.Artifacts = append(req.Artifacts, a)
	ir.RequestSHA256, _ = contracts.CanonicalSHA256(req)
	panel, err := evaluator.Compile(req, ir)
	if err != nil {
		t.Fatal(err)
	}
	index, err := domain.Build(req, panel.Coordinates())
	if err != nil {
		t.Fatal(err)
	}
	engine, err := NewInventory(index, panel, Config{1, 1, 1000, 8, 1, 8})
	if err != nil {
		t.Fatal(err)
	}
	ctx := &deadlineAfterChecks{Context: context.Background(), limit: 3}
	result, err := engine.Run(ctx)
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatal("missing controlled deadline", err)
	}
	if result.Leader.Assignment[0][0] != a.ArtifactID || result.Leader.DPS <= result.Initial.DPS || len(result.Finalists) == 0 {
		t.Fatal("within-wearer incumbent lost", result)
	}
	if result.StopReason != "search_deadline" {
		t.Fatal(result.StopReason)
	}
}

func TestInventoryUnknownModelDoesNotPruneOrSpendBoundWork(t *testing.T) {
	req, ir := searchFixtures(t)
	p, err := evaluator.Compile(req, ir)
	if err != nil {
		t.Fatal(err)
	}
	index, err := domain.Build(req, p.Coordinates())
	if err != nil {
		t.Fatal(err)
	}
	engine, err := NewInventory(index, p, Config{1, 1, 1000, 8, 1, 8})
	if err != nil {
		t.Fatal(err)
	}
	step, err := engine.RefineWearer(context.Background(), index.Incumbent, 0)
	if err != nil {
		t.Fatal(err)
	}
	if step.BoundPrunedBuilds != 0 || step.BoundEvaluations == 0 {
		t.Fatal("unknown-dependent pruning", step)
	}
}

func TestInventoryQueueUsesGlobalPotentialAndFIFOUnknowns(t *testing.T) {
	q := &inventoryRegionQueue{}
	for _, r := range []inventoryRegion{{upper: 10, order: 0}, {upper: 30, order: 1}, {upper: 20, order: 2}, {upper: math.Inf(1), order: 3}, {upper: math.Inf(1), order: 4}} {
		r.potential = r.upper
		heap.Push(q, r)
	}
	for _, order := range []int{3, 4, 1, 2, 0} {
		if got := heap.Pop(q).(inventoryRegion).order; got != order {
			t.Fatal(got, order)
		}
	}
}

func TestInventoryQueueApproximatePotentialDoesNotBecomePruningBound(t *testing.T) {
	q := &inventoryRegionQueue{}
	heap.Push(q, inventoryRegion{upper: math.Inf(1), potential: 10, order: 0})
	heap.Push(q, inventoryRegion{upper: math.Inf(1), potential: 100, order: 1})
	r := heap.Pop(q).(inventoryRegion)
	if r.order != 1 || !math.IsInf(r.upper, 1) {
		t.Fatal(r)
	}
}

func TestJointInventoryCanTransferOccupiedItemWithoutRetainedDonorBuild(t *testing.T) {
	req, ir := searchFixtures(t)
	req.Artifacts[0].Substats = []contracts.StatValue{{Key: "hp_percent", Value: "0.5"}}
	req.Artifacts[5].Substats = []contracts.StatValue{{Key: "hp_percent", Value: "0"}}
	replacement := req.Artifacts[0]
	replacement.ArtifactID = 99002
	replacement.Substats = []contracts.StatValue{{Key: "hp_percent", Value: "0.4"}}
	req.Artifacts = append(req.Artifacts, replacement)
	for i := range ir.Members {
		m := &ir.Members[i]
		m.Nodes = append(m.Nodes,
			contracts.IRNode{NodeID: 8, Operation: "artifact_stat", Coordinate: "actor_b.hp_percent", Inputs: []contracts.IRInput{}},
			contracts.IRNode{NodeID: 9, Operation: "constant", Value: "400", Inputs: []contracts.IRInput{}},
			contracts.IRNode{NodeID: 10, Operation: "multiply", Inputs: []contracts.IRInput{{NodeID: 8, Relation: "stat"}, {NodeID: 9, Relation: "scale"}}},
			contracts.IRNode{NodeID: 11, Operation: "add", Inputs: []contracts.IRInput{{NodeID: 7, Relation: "a"}, {NodeID: 10, Relation: "b"}}})
		m.Channels[0].RootNodeID = 11
		m.Channels[0].ResponseCoordinates = append(m.Channels[0].ResponseCoordinates, "actor_b.hp_percent")
	}
	ir.RequestSHA256, _ = contracts.CanonicalSHA256(req)
	p, err := evaluator.Compile(req, ir)
	if err != nil {
		t.Fatal(err)
	}
	index, err := domain.Build(req, p.Coordinates())
	if err != nil {
		t.Fatal(err)
	}
	engine, err := NewInventory(index, p, Config{1, 1, 1000, 8, 1, 8})
	if err != nil {
		t.Fatal(err)
	}
	dps, err := engine.score(index.Incumbent)
	if err != nil {
		t.Fatal(err)
	}
	anchor := ScoredAssignment{index.Incumbent, dps, "initial"}
	retained := [][]ScoredAssignment{{anchor}, {anchor}, {anchor}, {anchor}}
	legacy, err := New(index, p, DefaultConfig())
	if err != nil {
		t.Fatal(err)
	}
	old, _, _, _, _, _, _, err := legacy.refinePairs(context.Background(), anchor, retained)
	if err != nil || old.DPS != dps {
		t.Fatal("invalid old-row-only control", old, err)
	}
	engine.pairWorkLimit = 1000
	got, _, _, _, evaluated, _, _, err := engine.refinePairs(context.Background(), anchor, retained)
	if err != nil {
		t.Fatal(err)
	}
	if got.Assignment[0][0] != replacement.ArtifactID || got.Assignment[1][0] != 1 || got.DPS <= dps {
		t.Fatal("joint transfer missed", got)
	}
	if evaluated > engine.pairWorkLimit || index.ValidateAssignment(got.Assignment) != nil {
		t.Fatal("budget or physical legality lost")
	}
	engine.pairWorkLimit = 0
	_, _, _, _, evaluated, _, _, err = engine.refinePairs(context.Background(), anchor, retained)
	if err != nil || evaluated != 0 || !engine.pairBudgetExhausted {
		t.Fatal("joint allowance ignored", evaluated, err)
	}
}

func TestInventoryBudgetDoesNotClaimExhaustionOrLoseAnchor(t *testing.T) {
	req, ir := searchFixtures(t)
	// More than the already evaluated incumbent: a one-build domain legitimately
	// completes without spending a new point/bound evaluation after preparation.
	for i := 0; i < 2; i++ {
		a := req.Artifacts[0]
		a.ArtifactID = int64(2001 + i)
		a.Substats = []contracts.StatValue{{Key: "hp_percent", Value: strconv.FormatFloat(.2+float64(i)*.1, 'f', -1, 64)}}
		req.Artifacts = append(req.Artifacts, a)
	}
	ir.RequestSHA256, _ = contracts.CanonicalSHA256(req)
	p, e := evaluator.Compile(req, ir)
	if e != nil {
		t.Fatal(e)
	}
	index, e := domain.Build(req, p.Coordinates())
	if e != nil {
		t.Fatal(e)
	}
	engine, e := NewInventory(index, p, Config{1, 1, 1, 2, 1, 2})
	if e != nil {
		t.Fatal(e)
	}
	step, e := engine.RefineWearer(context.Background(), index.Incumbent, 0)
	if e != nil {
		t.Fatal(e)
	}
	if step.Expanded > 1 || step.BudgetUnexpanded == 0 || len(step.Finalists) == 0 {
		t.Fatalf("budget lost: %+v", step)
	}
	cancelled, cancel := context.WithCancel(context.Background())
	cancel()
	if _, e = engine.RefineWearer(cancelled, index.Incumbent, 0); e == nil {
		t.Fatal("cancel ignored")
	}
}
