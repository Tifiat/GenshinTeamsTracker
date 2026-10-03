package search

import "testing"

func TestObjectiveOrderingIsStrictAcrossNearEqualScores(t *testing.T) {
	values := []objective{
		{feasible: true, dps: 0}, {feasible: true, dps: .75e-9}, {feasible: true, dps: 1.5e-9},
		{shortage: 0, dps: 0}, {shortage: .75e-9, dps: 20}, {shortage: 1.5e-9, dps: 40},
	}
	for i, a := range values {
		if objectiveRanksBefore(a, a) {
			t.Fatal("not irreflexive", i)
		}
		for j, b := range values {
			if objectiveRanksBefore(a, b) && objectiveRanksBefore(b, a) {
				t.Fatal("not asymmetric", i, j)
			}
			for k, c := range values {
				if objectiveRanksBefore(a, b) && objectiveRanksBefore(b, c) && !objectiveRanksBefore(a, c) {
					t.Fatal("not transitive", i, j, k)
				}
			}
		}
	}
	if betterObjective(values[1], values[0]) || !objectiveRanksBefore(values[1], values[0]) {
		t.Fatal("acceptance tolerance and exact ordering were not kept separate")
	}
}

func TestScoredOrderingDoesNotCycleOnEpsilonTies(t *testing.T) {
	engine := &Engine{}
	base := []ScoredAssignment{{DPS: 0}, {DPS: .75e-9}, {DPS: 1.5e-9}}
	for i := range base {
		base[i].Assignment[0][0] = int64(i + 1)
	}
	for _, permutation := range [][3]int{{0, 1, 2}, {0, 2, 1}, {1, 0, 2}, {1, 2, 0}, {2, 0, 1}, {2, 1, 0}} {
		rows := []ScoredAssignment{base[permutation[0]], base[permutation[1]], base[permutation[2]]}
		engine.sortScored(rows)
		for i, want := range []int64{3, 2, 1} {
			if rows[i].Assignment[0][0] != want {
				t.Fatal("order depends on insertion", permutation, rows)
			}
		}
	}
}
