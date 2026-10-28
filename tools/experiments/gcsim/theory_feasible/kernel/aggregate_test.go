package theoryprototype

import (
	"math"
	"testing"
	"time"
)

func aggregateCapState(circlet string) State {
	mains := [4][5]string{}
	for actor := range mains {
		mains[actor] = [5]string{"hp", "atk", "atk_percent", "pyro_damage_bonus", "atk_percent"}
		if circlet != "" {
			mains[actor][4] = circlet
		}
	}
	return Seed(mains, [4][10]float64{}, 0, 20)
}

func TestAggregateFlowProducesCheckedFixedIncidenceWitness(t *testing.T) {
	template := Seed(testMains(), [4][10]float64{}, 0, 20)
	var want AggregateUpgradeTotals
	want[0][0], want[0][1] = 3.25, 1.75
	got, err := DecomposeAggregate(template, want, 25, true)
	if err != nil {
		t.Fatal(err)
	}
	if err := got.Validate(25, true); err != nil {
		t.Fatalf("flow output is not a quarter witness: %v", err)
	}
	actual := AggregateUpgrades(got)
	for stat, value := range want[0] {
		if math.Abs(actual[0][stat]-value) > 1e-10 {
			t.Fatalf("aggregate actor 0 stat %d = %g, want %g", stat, actual[0][stat], value)
		}
	}
	for slot := range got.Upgrades[0] {
		slotTotal := 0.0
		for _, upgrade := range got.Upgrades[0][slot] {
			slotTotal += upgrade
		}
		if slotTotal > 5+1e-10 {
			t.Fatalf("slot %d exceeds five upgrades: %g", slot, slotTotal)
		}
	}
}

func TestAggregateFlowRejectsUnsupportedAndOverCapacityTotals(t *testing.T) {
	template := Seed(testMains(), [4][10]float64{}, 0, 20)
	var unsupported AggregateUpgradeTotals
	unsupported[0][6] = .25 // EM is absent from every fixed line in actor 0.
	if _, err := DecomposeAggregate(template, unsupported, 45, true); err == nil {
		t.Fatal("accepted an upgrade demand with no eligible line arc")
	}

	var actorOver AggregateUpgradeTotals
	actorOver[0][0] = 25.25
	if _, err := DecomposeAggregate(template, actorOver, 45, true); err == nil {
		t.Fatal("accepted more than the actor's 25 upgrade units")
	}

	singleSlot := template
	singleSlot.Lines[0] = [5][4]int{
		{0, 1, 2, 3},
		{1, 2, 4, 5},
		{0, 1, 2, 4},
		{0, 1, 2, 4},
		{0, 1, 2, 4},
	}
	var slotOver AggregateUpgradeTotals
	slotOver[0][3] = 5.25 // This stat has only one eligible slot arc.
	if _, err := DecomposeAggregate(singleSlot, slotOver, 45, true); err == nil {
		t.Fatal("accepted more than the eligible slot's five upgrade units")
	}
}

func TestAggregateSubsetCapsReflectMainExclusion(t *testing.T) {
	const critDamage, critRate = 2, 3
	allEligible := aggregateCapState("")
	cdCap, err := AggregateSubsetCapacity(allEligible, 0, 1<<critDamage, 45)
	if err != nil {
		t.Fatal(err)
	}
	if cdCap != 30 {
		t.Fatalf("single-stat cap = %g; want 30", cdCap)
	}
	cdExcluded := aggregateCapState("crit_damage")
	cdCap, err = AggregateSubsetCapacity(cdExcluded, 0, 1<<critDamage, 45)
	if err != nil {
		t.Fatal(err)
	}
	if cdCap != 24 {
		t.Fatalf("single-stat cap with circlet main exclusion = %g; want 24", cdCap)
	}

	critMask := uint16((1 << critDamage) | (1 << critRate))
	bothCrits, err := AggregateSubsetCapacity(allEligible, 0, critMask, 45)
	if err != nil {
		t.Fatal(err)
	}
	if bothCrits != 35 {
		t.Fatalf("both-crit cap = %g; want 35", bothCrits)
	}
	critRateExcluded := aggregateCapState("crit_rate")
	withCritMain, err := AggregateSubsetCapacity(critRateExcluded, 0, critMask, 45)
	if err != nil {
		t.Fatal(err)
	}
	if withCritMain != 34 {
		t.Fatalf("both-crit cap with circlet main exclusion = %g; want 34", withCritMain)
	}
}

func TestFreeLineHullPointNeedNotHaveFourLineWitness(t *testing.T) {
	// Mix five legal one-item layouts. Each layout has four distinct lines and
	// gives each present line 1.25 upgrades, so its present stats total 2.25.
	// Averaging over the five omitted-stat choices gives 1.8 on all five stats.
	var hullPoint [5]float64
	for omitted := range hullPoint {
		for stat := range hullPoint {
			if stat != omitted {
				hullPoint[stat] += 2.25 / 5
			}
		}
	}
	total := 0.0
	for _, value := range hullPoint {
		if value <= 0 {
			t.Fatalf("expected every stat to be positive in the convex-hull point: %v", hullPoint)
		}
		total += value
	}
	if math.Abs(total-9) > 1e-12 {
		t.Fatalf("convex-hull point totals %g; want 9", total)
	}
	for subsetSize := 1; subsetSize <= 5; subsetSize++ {
		cap := math.Min(4, float64(subsetSize))
		if subsetSize > 0 {
			cap += 5
		}
		subsetTotal := float64(subsetSize) * 1.8
		if subsetTotal > cap+1e-12 {
			t.Fatalf("subset of size %d violates relaxed upper cap: %g > %g", subsetSize, subsetTotal, cap)
		}
	}
	// Five positive totals require five line identities in a single artifact;
	// a physical item has only four. The convex combination is therefore not a
	// physical witness, even though every relaxed subset upper cap is respected.
	t.Logf("free-line hull point=%v total=%g: subset caps pass, but no four-line physical witness exists", hullPoint, total)
}

func TestAggregateSearchMatchesSmallExhaustiveAndMeasuresSlotSPG(t *testing.T) {
	initial := Seed(testMains(), [4][10]float64{}, 0, 20)
	base := initial.Rolls()
	targetCD, targetCR := base[0][2]+.25, base[0][3]+.25
	objective := func(state State, needGradient bool) (float64, [4][10]float64, error) {
		rolls := state.Rolls()
		dcd := rolls[0][2] - targetCD
		dcr := rolls[0][3] - targetCR
		var gradient [4][10]float64
		gradient[0][2] = -2 * dcd
		gradient[0][3] = -2 * dcr
		return -(dcd*dcd + dcr*dcr), gradient, nil
	}
	slotObjective := objective

	aggregateStart := time.Now()
	aggregate, err := OptimizeAggregate(objective, initial, AggregateConfig{Budget: 20.5, MaxIterations: 80, Polish: true})
	aggregateElapsed := time.Since(aggregateStart)
	if err != nil {
		t.Fatal(err)
	}
	if err := aggregate.State.Validate(20.5, true); err != nil {
		t.Fatalf("aggregate result is not a validated quarter witness: %v", err)
	}

	slotStart := time.Now()
	slot, err := Optimize(slotObjective, initial, Config{Budget: 20.5, Method: "spg", MaxIterations: 80, LineSearch: true, Polish: true})
	slotElapsed := time.Since(slotStart)
	if err != nil {
		t.Fatal(err)
	}
	if err := slot.State.Validate(20.5, true); err != nil {
		t.Fatalf("slot SPG result is not a validated quarter witness: %v", err)
	}

	best := math.Inf(-1)
	consider := func(upgrades AggregateUpgradeTotals) {
		witness, err := DecomposeAggregate(initial, upgrades, 20.5, true)
		if err != nil {
			return
		}
		value, _, err := objective(witness, false)
		if err == nil {
			best = math.Max(best, value)
		}
	}
	consider(AggregateUpgradeTotals{})
	for first := 0; first < len(StatKeys); first++ {
		var one AggregateUpgradeTotals
		one[0][first] = .25
		consider(one)
		for second := first; second < len(StatKeys); second++ {
			var two AggregateUpgradeTotals
			two[0][first] += .25
			two[0][second] += .25
			consider(two)
		}
	}
	if math.Abs(aggregate.Value-best) > 1e-10 {
		t.Fatalf("aggregate score %.12g; exhaustive quarter optimum %.12g", aggregate.Value, best)
	}
	if slot.Value > best+1e-10 {
		t.Fatalf("slot SPG score %.12g exceeds exhaustive optimum %.12g", slot.Value, best)
	}
	t.Logf("fixed-incidence toy: aggregate=10 vars/actor, slot=20 vars/actor; aggregate %.12g/%d evals/%s/%v, slot-SPG %.12g/%d evals/%s/%v, exhaustive %.12g; both final witnesses validated",
		aggregate.Value, aggregate.Evaluations, aggregate.Stop, aggregateElapsed, slot.Value, slot.Evaluations, slot.Stop, slotElapsed, best)
}
