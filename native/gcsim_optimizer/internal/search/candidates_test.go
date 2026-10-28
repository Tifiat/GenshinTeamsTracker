package search

// Tiny real-item controls for the 2026-09-20 candidate policy. Synthetic formula
// fixtures test search arithmetic/legality, not GCSIM response or product speed.
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

func TestCandidatesTinyOracleBudgetAndCancel(t *testing.T) {
	req, ir := searchFixtures(t)
	for slot := 0; slot < 5; slot++ {
		for k := 0; k < 2; k++ {
			a := req.Artifacts[slot]
			a.ArtifactID = int64(1000 + slot*2 + k)
			a.Substats = append([]contracts.StatValue(nil), a.Substats...)
			if k == 1 {
				for i := range a.Substats {
					v, _ := strconv.ParseFloat(a.Substats[i].Value, 64)
					a.Substats[i].Value = strconv.FormatFloat(v*1.2, 'g', -1, 64)
				}
			}
			req.Artifacts = append(req.Artifacts, a)
		}
	}
	ir.RequestSHA256, _ = contracts.CanonicalSHA256(req)
	p, err := evaluator.Compile(req, ir)
	if err != nil {
		t.Fatal(err)
	}
	d, err := domain.Build(req, p.Coordinates())
	if err != nil {
		t.Fatal(err)
	}
	e, err := NewInventory(d, p, DefaultConfig())
	if err != nil {
		t.Fatal(err)
	}
	got, err := e.RefineCandidates(context.Background(), d.Incumbent, 0, 4096)
	if err != nil {
		t.Fatal(err)
	}
	best, trial := math.Inf(-1), d.Incumbent
	var visit func(int)
	visit = func(slot int) {
		if slot == 5 {
			if d.ValidateAssignment(trial) != nil {
				return
			}
			v, e := e.score(trial)
			if e != nil {
				t.Fatal(e)
			}
			best = math.Max(best, v)
			return
		}
		for _, id := range d.CandidateIDsBySlot[slot] {
			trial[0][slot] = id
			visit(slot + 1)
		}
	}
	visit(0)
	if !got.Exhaustive || got.Step.BoundEvaluations != 0 || math.Abs(got.Step.Finalists[0].DPS-best) > 1e-9 {
		t.Fatal("candidate oracle", got, best)
	}
	for _, limit := range []int{0, 1, 5} {
		r, err := e.ScreenCandidates(context.Background(), d.Incumbent, 0, limit)
		if err != nil || r.Step.Expanded > limit || len(r.Step.Finalists) == 0 {
			t.Fatal("screen budget", limit, r, err)
		}
		for _, row := range r.Step.Finalists {
			if d.ValidateAssignment(row.Assignment) != nil {
				t.Fatal("invalid candidate")
			}
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	r, err := e.RefineCandidates(ctx, d.Incumbent, 0, 4096)
	if !errors.Is(err, context.Canceled) || len(r.Step.Finalists) == 0 {
		t.Fatal("cancel lost incumbent", r, err)
	}
}

func TestCandidatesGapIsOnlyHeuristicAndNeedsDiverseEvidence(t *testing.T) {
	r := CandidateReport{Samples: 5, PairSamples: 1, Low: 125, High: 126}
	if !r.DeferBelow(140) || r.DeferBelow(127) || r.DeferBelow(math.Inf(-1)) {
		t.Fatal("gap policy")
	}
	r.PairSamples = 0
	if r.DeferBelow(140) {
		t.Fatal("singles alone cannot defer")
	}
	r.PairSamples = 1
	r.Samples = 4
	if r.DeferBelow(140) {
		t.Fatal("insufficient sample")
	}
}

func TestCandidatesPairedMoveEscapesWorseSingles(t *testing.T) {
	req, ir := searchFixtures(t)
	for slot := 0; slot < 5; slot++ {
		count := 10 // force the non-exhaustive route without adding new stat effects
		if slot < 2 {
			count = 1
		}
		for k := 0; k < count; k++ {
			a := req.Artifacts[slot]
			a.ArtifactID = int64(1000 + slot*20 + k)
			a.Substats = append([]contracts.StatValue(nil), a.Substats...)
			if slot < 2 {
				found := false
				for i := range a.Substats {
					if a.Substats[i].Key == "hp_percent" {
						v, _ := strconv.ParseFloat(a.Substats[i].Value, 64)
						a.Substats[i].Value = strconv.FormatFloat(v+.2, 'g', -1, 64)
						found = true
					}
				}
				if !found {
					a.Substats = append(a.Substats, contracts.StatValue{Key: "hp_percent", Value: "0.2"})
				}
				sort.Slice(a.Substats, func(i, j int) bool { return a.Substats[i].Key < a.Substats[j].Key })
			}
			req.Artifacts = append(req.Artifacts, a)
		}
	}
	for i := range ir.Members {
		m := &ir.Members[i]
		m.Nodes = []contracts.IRNode{
			{NodeID: 1, Operation: "constant", Value: "100", Inputs: []contracts.IRInput{}},
			{NodeID: 2, Operation: "artifact_stat", Coordinate: "actor_a.hp_percent", Inputs: []contracts.IRInput{}},
			{NodeID: 3, Operation: "constant", Value: "-0.3", Inputs: []contracts.IRInput{}},
			{NodeID: 4, Operation: "add", Inputs: []contracts.IRInput{{NodeID: 2, Relation: "x"}, {NodeID: 3, Relation: "offset"}}},
			{NodeID: 5, Operation: "multiply", Inputs: []contracts.IRInput{{NodeID: 2, Relation: "x"}, {NodeID: 4, Relation: "offset"}}},
			{NodeID: 6, Operation: "add", Inputs: []contracts.IRInput{{NodeID: 1, Relation: "base"}, {NodeID: 5, Relation: "pair_gain"}}},
		}
		m.Channels[0].RootNodeID = 6
		m.Channels[0].BaselineDamage = "100"
		m.Channels[0].ResponseCoordinates = []string{"actor_a.hp_percent"}
		m.OpaqueBoundaries = []contracts.IROpaqueBoundary{}
	}
	ir.RequestSHA256, _ = contracts.CanonicalSHA256(req)
	p, err := evaluator.Compile(req, ir)
	if err != nil {
		t.Fatal(err)
	}
	d, err := domain.Build(req, p.Coordinates())
	if err != nil {
		t.Fatal(err)
	}
	e, err := NewInventory(d, p, DefaultConfig())
	if err != nil {
		t.Fatal(err)
	}
	base, _ := e.score(d.Incumbent)
	for slot := 0; slot < 2; slot++ {
		a := d.Incumbent
		a[0][slot] = int64(1000 + slot*20)
		v, _ := e.score(a)
		if v >= base {
			t.Fatal("single is not worse")
		}
	}
	for _, screen := range []bool{true, false} {
		var r CandidateReport
		if screen {
			r, err = e.ScreenCandidates(context.Background(), d.Incumbent, 0, 100)
		} else {
			r, err = e.RefineCandidates(context.Background(), d.Incumbent, 0, 20000)
		}
		if err != nil || r.Exhaustive || r.Step.Finalists[0].DPS <= base || r.Step.BoundEvaluations != 0 {
			t.Fatal("missed paired escape", screen, r, err)
		}
	}
}
