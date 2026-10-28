package main

import (
	"fmt"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	proto "genshinteamstracker/native/gcsim_optimizer/internal/theoryprototype"
	"genshinteamstracker/native/gcsim_optimizer/internal/theoryteams"
)

func TestCommonHConfigurationAndLegacyDefault(t *testing.T) {
	first, err := commonHConfiguration("first", 946)
	if err != nil || first.CatalogPasses != 1 {
		t.Fatal(first, err)
	}
	full, err := commonHConfiguration("full", 946)
	if err != nil || full.CatalogPasses != 2 {
		t.Fatal(full, err)
	}
	copy := first
	copy.Depth, copy.CatalogPasses = full.Depth, full.CatalogPasses
	if copy != full || commonHPasses(&hybridRun{}) != 2 {
		t.Fatal("first/full settings differ beyond continuation selection")
	}
	for _, bad := range []string{"", "auto", "3", "nilou"} {
		if _, err := commonHConfiguration(bad, 946); err == nil {
			t.Fatal("unsupported depth accepted", bad)
		}
	}
	if _, err := commonHConfiguration("first", 0); err == nil {
		t.Fatal("empty catalog accepted")
	}
	t.Setenv("GTT_BOUNDS_CONTROL_PACKAGES", "POISON_CONTROL")
	t.Setenv("GTT_PROGRESSIVE_KNOWN", "missing-control-file.json")
	if again, _ := commonHConfiguration("first", 946); again != first {
		t.Fatal("control environment changed policy")
	}
}

func TestCommonHWorkCapsBlockCallsAndKeepIncumbent(t *testing.T) {
	cfg, _ := commonHConfiguration("full", 946)
	s := proto.Seed(initialMains(), [4][10]float64{}, 0, 45)
	h := &hybridRun{researchH: &cfg, deadline: time.Now().Add(time.Minute), pool: map[string]feasibleCandidate{}, best: -1,
		w: &r2World{feasibleWorld: &feasibleWorld{}}}
	h.offer(feasibleCandidate{state: s, value: 10, family: "legal"})
	for _, cause := range []string{"formula", "gradient", "resolve"} {
		h.w.work = feasibleWork{}
		h.w.extra.Requests = 0
		switch cause {
		case "formula":
			h.w.work.Formula = cfg.FormulaLimit
		case "gradient":
			h.w.work.Gradient = cfg.GradientLimit
		case "resolve":
			h.w.extra.Requests = cfg.ResolveLimit
		}
		if h.alive() || commonHWorkStop(h) == "" {
			t.Fatal("work limit did not stop", cause)
		}
		if _, _, err := h.objective(&feasibleEntry{}, [4]domain.Package{})(s, true); err != errProgressiveDeadline {
			t.Fatal("work limit allowed objective", cause, err)
		}
		if _, err := h.resolve([4]domain.Package{}); err != errProgressiveDeadline {
			t.Fatal("work limit allowed resolve", cause, err)
		}
		if h.pool["legal"].state != s || h.pool["legal"].value != 10 {
			t.Fatal("work guard discarded legal incumbent")
		}
	}
}

func TestCommonHAuditPlanFrozenDistinctAndAllActorPairs(t *testing.T) {
	options := []domain.Package{}
	pool := map[string]feasibleCandidate{}
	aliases := map[string]map[string]bool{}
	s := proto.Seed(initialMains(), [4][10]float64{}, 0, 45)
	for i := 0; i < 12; i++ {
		p := domain.Package{Sets: []contracts.SetRequirement{{SetUID: fmt.Sprintf("set%02d", i), Count: 4}}}
		options = append(options, p)
		tuple := [4]domain.Package{p, p, p, p}
		family := fmt.Sprintf("f%02d", i)
		pool[family] = feasibleCandidate{tuple, s, float64(100 - i), family}
		hybridAddAlias(aliases, family, theoryteams.Key(tuple))
	}
	before := hybridCopy(pool)
	plan := commonHAuditPlan(pool, aliases, options)
	if len(plan) != 8 {
		t.Fatal("audit is not two alternatives plus six actor pairs", len(plan))
	}
	keys := map[string]bool{}
	pairs := map[[2]int]bool{}
	for i, target := range plan {
		key := theoryteams.Key(target.Packages)
		if keys[key] {
			t.Fatal("duplicate audit target")
		}
		keys[key] = true
		if i >= 2 {
			if target.Ranks[0] < 3 || target.Ranks[1] < 3 || pairs[target.Actors] || hybridDistance(target.Packages, pool["f00"].packages) != 2 {
				t.Fatal("pair audit lost nonleader or pair coverage", target)
			}
			pairs[target.Actors] = true
		}
	}
	if len(pairs) != 6 || len(pool) != len(before) {
		t.Fatal("audit plan changed policy or missed actor pairs")
	}
}

func TestCommonHAuditBudgetRetainsOnlyCompletedLegalPoint(t *testing.T) {
	calls := 0
	s := proto.Seed(initialMains(), [4][10]float64{}, 0, 45)
	g := commonHAuditGuard{FormulaMax: 2, GradMax: 1, guard: hybridGuard{deadline: time.Now().Add(time.Minute),
		objective: func(proto.State, bool) (float64, [4][10]float64, error) {
			calls++
			return float64(calls), [4][10]float64{}, nil
		}}}
	if _, _, err := g.evaluate(s, true); err != nil {
		t.Fatal(err)
	}
	if _, _, err := g.evaluate(s, true); err != errProgressiveDeadline || calls != 1 {
		t.Fatal("gradient budget exceeded", err, calls)
	}
	if _, _, err := g.evaluate(s, false); err != nil {
		t.Fatal(err)
	}
	if _, _, err := g.evaluate(s, false); err != errProgressiveDeadline || calls != 2 || g.guard.value != 2 || g.guard.best != s {
		t.Fatal("formula budget exceeded or incumbent lost", err, calls)
	}
}

func TestCommonHAuditDuplicateStartsAreNotExtraEvidence(t *testing.T) {
	a := proto.Seed(initialMains(), [4][10]float64{}, 0, 45)
	var gradient [4][10]float64
	gradient[0][9] = 2
	b := proto.Seed(initialMains(), gradient, 0, 45)
	if a == b || !hybridLegal(b) {
		t.Fatal("distinct legal fixture missing")
	}
	if got := commonHAuditStarts([]proto.State{a, b, a}); len(got) != 2 || got[0] != a || got[1] != b {
		t.Fatal("distinct fallback was not used")
	}
	if got := commonHAuditStarts([]proto.State{a, a, a}); len(got) != 1 || got[0] != a {
		t.Fatal("duplicate seed was counted twice")
	}
	permuted := a
	permuted.Lines[0][0][0], permuted.Lines[0][0][1] = permuted.Lines[0][0][1], permuted.Lines[0][0][0]
	permuted.Upgrades[0][0][0], permuted.Upgrades[0][0][1] = permuted.Upgrades[0][0][1], permuted.Upgrades[0][0][0]
	if got := commonHAuditStarts([]proto.State{a, a, permuted}); len(got) != 1 {
		t.Fatal("permuted equivalent seed was counted twice")
	}
}
