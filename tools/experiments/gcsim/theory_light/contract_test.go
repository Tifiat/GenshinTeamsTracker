package main

import (
	"fmt"
	"reflect"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	proto "genshinteamstracker/native/gcsim_optimizer/internal/theoryprototype"
	"genshinteamstracker/native/gcsim_optimizer/internal/theoryteams"
)

func lightFixture() (*hybridRun, []domain.Package) {
	h := &hybridRun{w: &r2World{feasibleWorld: &feasibleWorld{}}, pool: map[string]feasibleCandidate{},
		aliases: map[string]map[string]bool{}, refined: map[string]int{}, best: 100}
	s := proto.Seed(initialMains(), [4][10]float64{}, 0, 45)
	options := []domain.Package{}
	for i := 0; i < 12; i++ {
		p := domain.Package{Sets: []contracts.SetRequirement{{SetUID: fmt.Sprintf("set%02d", i), Count: 4}}}
		options = append(options, p)
		tuple := [4]domain.Package{p, p, p, p}
		family := fmt.Sprintf("family%02d", i)
		h.pool[family] = feasibleCandidate{tuple, s, 100 - float64(i)/5, family}
		hybridAddAlias(h.aliases, family, theoryteams.Key(tuple))
	}
	return h, options
}

func TestLightLegacyDefaultAndNoHiddenDeep(t *testing.T) {
	legacy, _ := lightFixture()
	if !lightDeepEnabled(legacy) {
		t.Fatal("legacy baseline disabled")
	}
	legacy.researchLight = &lightObservation{}
	if !lightDeepEnabled(legacy) {
		t.Fatal("observed baseline disabled")
	}
	legacy.researchLight.SkipDeep = true
	if lightDeepEnabled(legacy) {
		t.Fatal("light still requires deep bundle")
	}
	if commonHPasses(legacy) != 2 {
		t.Fatal("light changed legacy catalog passes")
	}
	if 135+180+lightAuditSeconds+lightChecksSeconds >= lightOverallSeconds {
		t.Fatal("no overall slack")
	}
}

func TestLightObserverIsPureAndRejectsMutation(t *testing.T) {
	h, _ := lightFixture()
	h.researchLight = &lightObservation{SkipDeep: true}
	before := lightFingerprint(h)
	lightObserve(h, "fixture", func(string) []feasibleCandidate { return r2Sorted(h.pool) })
	if lightFingerprint(h) != before || h.researchLight.Count != 1 {
		t.Fatal("observation changed search")
	}
	rejected := false
	func() {
		defer func() { rejected = recover() != nil }()
		lightObserve(h, "bad", func(string) []feasibleCandidate {
			c := h.pool["family00"]
			c.value++
			h.pool[c.family] = c
			return nil
		})
	}()
	if !rejected {
		t.Fatal("observer mutation escaped")
	}
}

func TestLightAuditReservedPairAndDistinctTargets(t *testing.T) {
	light, options := lightFixture()
	baseline, _ := lightFixture()
	delete(light.pool, "family04")
	c := light.pool["family03"]
	c.value -= 3
	light.pool[c.family] = c
	beforeL, beforeB := lightFingerprint(light), lightFingerprint(baseline)
	plan := lightAuditPlan(light, baseline, options, 100)
	if len(plan) != 4 {
		t.Fatal("expected four targets", len(plan))
	}
	if plan[0].Reason != "reserved_both_nonleader_from_frozen_light_leader" || plan[0].Ranks[0] < 3 || plan[0].Ranks[1] < 3 || hybridDistance(plan[0].Packages, light.pool["family00"].packages) != 2 {
		t.Fatal("reserved pair missing", plan[0])
	}
	if plan[1].BaselineFamily != "family04" || plan[1].LightLower != nil || plan[1].LightRank != 0 {
		t.Fatal("missing family invented a value", plan[1])
	}
	if plan[2].BaselineFamily != "family03" || plan[2].LightLower == nil {
		t.Fatal("underestimated direction missing", plan[2])
	}
	keys := map[string]bool{}
	for _, p := range plan {
		key := theoryteams.Key(p.Packages)
		if keys[key] {
			t.Fatal("duplicate audit")
		}
		keys[key] = true
	}
	if beforeL != lightFingerprint(light) || beforeB != lightFingerprint(baseline) {
		t.Fatal("target selection changed policy")
	}
	again := lightAuditPlan(light, baseline, options, 100)
	if !reflect.DeepEqual(plan, again) {
		t.Fatal("target selection is not deterministic")
	}
}

func TestLightAliasesDoNotInventMissingFamily(t *testing.T) {
	light, options := lightFixture()
	baseline, _ := lightFixture()
	// Same canonical family, alternate package representative and alias. Package
	// inequality alone must not send this family to the missing-family category.
	c := light.pool["family00"]
	c.packages[0] = options[2]
	light.pool[c.family] = c
	hybridAddAlias(light.aliases, c.family, theoryteams.Key(c.packages))
	for _, p := range lightAuditPlan(light, baseline, options, 100) {
		if p.Reason == "strongest_baseline_family_unseen_by_light" {
			t.Fatal("alias misclassified as missing family", p)
		}
	}
}

func TestLightPerTupleQuotaDoesNotStarveNextTuple(t *testing.T) {
	state := proto.Seed(initialMains(), [4][10]float64{}, 0, 45)
	for tuple := 0; tuple < 4; tuple++ {
		calls := 0
		g := commonHAuditGuard{FormulaMax: 2, GradMax: 1, guard: hybridGuard{deadline: time.Now().Add(time.Second),
			objective: func(proto.State, bool) (float64, [4][10]float64, error) {
				calls++
				return float64(calls), [4][10]float64{}, nil
			}}}
		if _, _, err := g.evaluate(state, true); err != nil {
			t.Fatal(tuple, err)
		}
		if _, _, err := g.evaluate(state, false); err != nil {
			t.Fatal(tuple, err)
		}
		if _, _, err := g.evaluate(state, false); err != errProgressiveDeadline || calls != 2 || !g.guard.hasBest || g.guard.value != 2 {
			t.Fatal("quota or incumbent failed", tuple, err)
		}
	}
}

func TestLightFinalObservationCannotHideWallGuard(t *testing.T) {
	h, _ := lightFixture()
	h.deadline = time.Now().Add(-time.Second)
	h.completedPasses = 2
	if lightPolicyStopReason(h, nil) != "policy_or_global_wall_guard_including_observations" {
		t.Fatal("completed pass hid expired observation clock")
	}
	h.deadline = time.Now().Add(time.Minute)
	if lightPolicyStopReason(h, nil) != "" {
		t.Fatal("unexpired complete policy marked partial")
	}
}
