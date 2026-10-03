package search

import (
	"context"
	"errors"
	"math"
	"sort"
	"strconv"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
)

func coupledStabilization(t *testing.T) (*Engine, *domain.Index) {
	t.Helper()
	r, ir := searchFixtures(t)
	for actor := 0; actor < 2; actor++ {
		a := r.Artifacts[actor*5]
		a.ArtifactID = int64(1000 + actor)
		a.Substats = append([]contracts.StatValue(nil), a.Substats...)
		found := false
		for i := range a.Substats {
			if a.Substats[i].Key == "hp_percent" {
				v, _ := strconv.ParseFloat(a.Substats[i].Value, 64)
				a.Substats[i].Value = strconv.FormatFloat(v+1, 'g', -1, 64)
				found = true
			}
		}
		if !found {
			a.Substats = append(a.Substats, contracts.StatValue{Key: "hp_percent", Value: "1"})
		}
		sort.Slice(a.Substats, func(i, j int) bool { return a.Substats[i].Key < a.Substats[j].Key })
		r.Artifacts = append(r.Artifacts, a)
	}
	for i := range ir.Members {
		m := &ir.Members[i]
		m.Nodes = []contracts.IRNode{
			{NodeID: 1, Operation: "constant", Value: "100", Inputs: []contracts.IRInput{}},
			{NodeID: 2, Operation: "artifact_stat", Coordinate: "actor_a.hp_percent", Inputs: []contracts.IRInput{}},
			{NodeID: 3, Operation: "artifact_stat", Coordinate: "actor_b.hp_percent", Inputs: []contracts.IRInput{}},
			{NodeID: 4, Operation: "multiply", Inputs: []contracts.IRInput{{NodeID: 2, Relation: "x"}, {NodeID: 3, Relation: "y"}}},
			{NodeID: 5, Operation: "constant", Value: "-0.5", Inputs: []contracts.IRInput{}},
			{NodeID: 6, Operation: "multiply", Inputs: []contracts.IRInput{{NodeID: 2, Relation: "x"}, {NodeID: 5, Relation: "scale"}}},
			{NodeID: 7, Operation: "add", Inputs: []contracts.IRInput{{NodeID: 1, Relation: "base"}, {NodeID: 3, Relation: "y"}, {NodeID: 4, Relation: "xy"}, {NodeID: 6, Relation: "loss"}}},
		}
		m.Channels[0].RootNodeID = 7
		m.Channels[0].BaselineDamage = "100"
		m.Channels[0].ResponseCoordinates = []string{"actor_a.hp_percent", "actor_b.hp_percent"}
		m.OpaqueBoundaries = []contracts.IROpaqueBoundary{}
	}
	ir.RequestSHA256, _ = contracts.CanonicalSHA256(r)
	p, e := evaluator.Compile(r, ir)
	if e != nil {
		t.Fatal(e)
	}
	d, e := domain.Build(r, p.Coordinates())
	if e != nil {
		t.Fatal(e)
	}
	s, e := NewInventory(d, p, DefaultConfig())
	if e != nil {
		t.Fatal(e)
	}
	return s, d
}

func TestStabilizationRevisitsCrossOwnerDependenciesAndCertifiesSingles(t *testing.T) {
	e, d := coupledStabilization(t)
	initial, _ := e.score(d.Incumbent)
	first, err := e.RefineSingles(context.Background(), d.Incumbent, 0, 10000)
	if err != nil || first.Step.Finalists[0].DPS > initial+1e-12 {
		t.Fatal("fixture must require revisiting the first owner", first, err)
	}
	r, err := e.Stabilize(context.Background(), d.Incumbent, 10000)
	if err != nil || !r.SingleStationary || r.Stop != "single_stationary_sampled_pairs_stable" || r.Leader.DPS <= initial {
		t.Fatal(r, err)
	}
	// Independent direct enumeration of the complete N1 neighborhood, no priority
	// list. Every physically legal alternative must fail to improve the result.
	for actor := 0; actor < 4; actor++ {
		for slot, pool := range d.CandidateIDsBySlot {
			for _, id := range pool {
				a := r.Leader.Assignment
				a[actor][slot] = id
				if d.ValidateAssignment(a) != nil {
					continue
				}
				v, err := e.score(a)
				if err != nil || improvesDPS(v, r.Leader.DPS) {
					t.Fatal("false N1 certificate", a, v, r, err)
				}
			}
		}
	}
	// The two physical flowers have equal stats and may exchange owners.
	if r.Leader.Assignment[0][0]+r.Leader.Assignment[1][0] != 2001 || r.Leader.Assignment[0][0] < 1000 || r.Leader.Assignment[1][0] < 1000 {
		t.Fatal("lost coupled improvement", r)
	}
}

func TestStabilizationBudgetCancelMonotonicity(t *testing.T) {
	e, d := coupledStabilization(t)
	base, _ := e.score(d.Incumbent)
	for _, n := range []int{0, 1, 2, 8, 32} {
		r, err := e.Stabilize(context.Background(), d.Incumbent, n)
		if err != nil || r.Evaluations > n || r.Leader.DPS < base-1e-9 || d.ValidateAssignment(r.Leader.Assignment) != nil {
			t.Fatal(n, r, err)
		}
		v, _ := e.score(r.Leader.Assignment)
		if math.Abs(v-r.Leader.DPS) > 1e-9 {
			t.Fatal("stale score")
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	r, err := e.Stabilize(ctx, d.Incumbent, 10000)
	if !errors.Is(err, context.Canceled) || r.SingleStationary || r.Leader.Assignment != d.Incumbent {
		t.Fatal(r, err)
	}
}
