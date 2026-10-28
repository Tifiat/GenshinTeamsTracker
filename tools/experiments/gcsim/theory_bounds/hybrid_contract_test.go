package main

import (
	"encoding/json"
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	proto "genshinteamstracker/native/gcsim_optimizer/internal/theoryprototype"
	"genshinteamstracker/native/gcsim_optimizer/internal/theoryteams"
	"testing"
	"time"
)

func TestHybridSeedLegalityAndIndependentStart(t *testing.T) {
	initial := proto.Seed(initialMains(), [4][10]float64{}, 0, 45)
	var gradient [4][10]float64
	for a := range gradient {
		for j := range gradient[a] {
			gradient[a][j] = float64((a + 1) * (j + 2))
		}
	}
	fresh := hybridFresh(initial, gradient)
	bad := initial
	bad.Upgrades[0][0][0] = 100
	for _, warm := range []bool{false, true} {
		seeds := hybridSeedSet(fresh, []proto.State{bad, fresh[0], fresh[1]}, warm)
		if len(seeds) != 3 {
			t.Fatal(len(seeds))
		}
		for _, s := range seeds {
			if !hybridLegal(s) {
				t.Fatal("invalid or not exactly 45", s)
			}
		}
		if warm && seeds[0] != fresh[2] {
			t.Fatal("independent current-formula seed lost")
		}
	}
	short := initial
	short.Upgrades[0][0][0] = 0
	if short != initial && hybridLegal(short) {
		t.Fatal("under-spent state accepted")
	}
}
func TestHybridMonotonicWitnessAndSnapshot(t *testing.T) {
	s := proto.Seed(initialMains(), [4][10]float64{}, 0, 45)
	pool := map[string]feasibleCandidate{}
	a := feasibleCandidate{state: s, value: 10, family: "a"}
	if !hybridOffer(pool, a) {
		t.Fatal("legal incumbent missing")
	}
	saved := hybridCopy(pool)
	a.value = 9
	if hybridOffer(pool, a) || pool["a"].value != 10 {
		t.Fatal("incumbent regressed")
	}
	a.value = 11
	a.state.Upgrades[0][0][0] = .1
	if hybridOffer(pool, a) {
		t.Fatal("illegal transient accepted")
	}
	a.state = s
	a.value = 12
	if !hybridOffer(pool, a) || saved["a"].value != 10 {
		t.Fatal("snapshot mutated")
	}
}
func TestHybridAliasesAndBothNonleaderPairs(t *testing.T) {
	for _, c := range []struct {
		n    int
		want string
	}{{0, "[]"}, {1, "[0]"}, {2, "[0 1]"}, {3, "[0 1 2]"}, {8, "[0 1 5]"}} {
		if got := fmt.Sprint(hybridPairRefineIndices(c.n)); got != c.want {
			t.Fatal("pair nonleader refinement omitted", c.n, got, c.want)
		}
	}
	options := []domain.Package{}
	for i := 0; i < 12; i++ {
		options = append(options, domain.Package{Sets: []contracts.SetRequirement{{SetUID: fmt.Sprintf("set%02d", i), Count: 4}}})
	}
	s := proto.Seed(initialMains(), [4][10]float64{}, 0, 45)
	pool := map[string]feasibleCandidate{}
	aliases := map[string]map[string]bool{}
	for i, p := range options {
		tuple := [4]domain.Package{p, p, p, p}
		f := fmt.Sprintf("f%02d", i)
		pool[f] = feasibleCandidate{tuple, s, float64(100 - i), f}
		hybridAddAlias(aliases, f, theoryteams.Key(tuple))
		hybridAddAlias(aliases, f, theoryteams.Key(tuple))
	}
	alias := pool["f00"].packages
	alias[0] = options[11]
	hybridAddAlias(aliases, "f00", theoryteams.Key(alias))
	if len(hybridAliases(aliases)["f00"]) != 2 {
		t.Fatal("aliases lost/duplicated")
	}
	plan := hybridPairPlan(pool, aliases, options)
	if len(plan) != 192 {
		t.Fatal("unexpected bounded pair plan", len(plan))
	}
	for _, p := range plan {
		if p.Ranks[0] < 3 || p.Ranks[1] < 3 {
			t.Fatal("pair restricted to leaders", p.Ranks)
		}
		before := splitHybridKey(p.Anchor)
		after := splitHybridKey(theoryteams.Key(p.Packages))
		changes := 0
		for a := range before {
			if before[a] != after[a] {
				changes++
			}
		}
		if changes != 2 {
			t.Fatal("not simultaneous two-wearer move", changes)
		}
	}
}
func TestHybridControlEnvironmentCannotChangePlanOrSeeds(t *testing.T) {
	options := []domain.Package{{}, {Sets: []contracts.SetRequirement{{SetUID: "synthetic", Count: 4}}}}
	initial := proto.Seed(initialMains(), [4][10]float64{}, 0, 45)
	makeInput := func() []byte {
		b, e := json.Marshal([]any{hybridInitialTuples([4]domain.Package{}, options), hybridFresh(initial, [4][10]float64{})})
		if e != nil {
			t.Fatal(e)
		}
		return b
	}
	before := string(makeInput())
	t.Setenv("GTT_BOUNDS_CONTROL_PACKAGES", "POISON_CONTROL")
	t.Setenv("GTT_PROGRESSIVE_KNOWN", "missing-control-file.json")
	if string(makeInput()) != before {
		t.Fatal("control data reached policy plan")
	}
}
func TestHybridDeadlineKeepsCompletedLegalWitness(t *testing.T) {
	s := proto.Seed(initialMains(), [4][10]float64{}, 0, 45)
	h := &hybridRun{started: time.Now(), deadline: time.Now(), pool: map[string]feasibleCandidate{}, best: -1, w: &r2World{feasibleWorld: &feasibleWorld{}}}
	h.offer(feasibleCandidate{state: s, value: 10, family: "a"})
	if h.alive() || h.pool["a"].state != s || h.best != 10 {
		t.Fatal("deadline discarded incumbent")
	}
}
func TestHybridGuardRejectsUnusedBudgetAndLateCalls(t *testing.T) {
	short := proto.Seed(initialMains(), [4][10]float64{}, 1, 45)
	full := proto.Seed(initialMains(), [4][10]float64{}, 0, 45)
	calls := 0
	guard := hybridGuard{deadline: time.Now().Add(time.Second), objective: func(s proto.State, g bool) (float64, [4][10]float64, error) {
		calls++
		return float64(100 - calls), [4][10]float64{}, nil
	}}
	_, _, _ = guard.evaluate(short, false)
	if guard.hasBest {
		t.Fatal("under-spent point became a full-budget witness")
	}
	_, _, _ = guard.evaluate(full, false)
	if !guard.hasBest || guard.best != full || guard.value != 98 {
		t.Fatal("full-budget progress not retained")
	}
	guard.deadline = time.Now().Add(-time.Second)
	if _, _, err := guard.evaluate(full, false); err != errProgressiveDeadline || calls != 2 || guard.best != full {
		t.Fatal("deadline lost witness or evaluated late", err, calls)
	}
}
func TestHybridKnownAliasReusesOnlyCompletedFamily(t *testing.T) {
	p := [4]domain.Package{}
	key := theoryteams.Key(p)
	h := &hybridRun{deadline: time.Now().Add(time.Second), visited: map[string]string{key: "same"}, screened: map[string]bool{"same": true}}
	if family, err := h.visit(p); err != nil || family != "same" || h.aliasHits != 1 {
		t.Fatal("known alias did not reuse family", family, err)
	}
	h.deadline = time.Now().Add(-time.Second)
	if _, err := h.visit(p); err != errProgressiveDeadline || h.aliasHits != 1 {
		t.Fatal("alias lookup bypassed deadline", err)
	}
}
