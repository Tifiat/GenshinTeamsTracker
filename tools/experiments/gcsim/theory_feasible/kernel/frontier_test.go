package theoryprototype

import (
	"math"
	"testing"
)

// Two binary set choices, followed by a paired main/line jump. Either set
// alone is worse than neither; for the joint set, either structural change
// alone is worse than leaving both unchanged.
func tinyFrontierScore(combo, main, line int) float64 {
	score := 10.0
	if combo&1 != 0 {
		score -= 1
	}
	if combo&2 != 0 {
		score -= .5
	}
	if main != 0 {
		score -= .4
	}
	if line != 0 {
		score -= .4
	}
	if combo == 3 && main != 0 && line != 0 {
		score += 10
	}
	return score
}

func exactTinyRegionUpper(mask uint8) float64 {
	best := math.Inf(-1)
	for combo := 0; combo < 4; combo++ {
		if mask&(1<<combo) == 0 {
			continue
		}
		for main := 0; main < 2; main++ {
			for line := 0; line < 2; line++ {
				best = math.Max(best, tinyFrontierScore(combo, main, line))
			}
		}
	}
	return best
}

func TestBoundQueueBestFirstTopTwoAndCoverage(t *testing.T) {
	type node struct {
		mask     uint8
		children []int
	}
	// Bit c means set combination c remains possible. Every branch replaces
	// its parent by disjoint children whose union is exactly its coverage.
	tree := map[int]node{
		0: {mask: 0b1111, children: []int{1, 2}},
		1: {mask: 0b0101, children: []int{5, 6}}, // first wearer has no set
		2: {mask: 0b1010, children: []int{3, 4}}, // first wearer has set
		3: {mask: 0b0010},                        // set A only
		4: {mask: 0b1000},                        // both sets
		5: {mask: 0b0001},                        // neither set
		6: {mask: 0b0100},                        // set B only
	}
	if tree[0].mask != 0b1111 || math.Abs(exactTinyRegionUpper(tree[0].mask)-17.7) > 1e-12 {
		t.Fatal("root does not cover the exact tiny domain")
	}
	var queue BoundQueue
	push := func(id int) {
		n := tree[id]
		if err := queue.Push(BoundRegion{ID: id, Upper: exactTinyRegionUpper(n.mask), Potential: float64(-id)}); err != nil {
			t.Fatal(err)
		}
	}
	push(0)
	scores := map[string]float64{}
	visited := []int{}
	pruned := 0
	maxAfterBest := math.NaN()
	for {
		region, ok, discarded := queue.Pop(KthLower(scores, 2))
		pruned += discarded
		if !ok {
			break
		}
		visited = append(visited, region.ID)
		n := tree[region.ID]
		if len(n.children) > 0 {
			union := uint8(0)
			for _, childID := range n.children {
				child := tree[childID]
				if union&child.mask != 0 {
					t.Fatal("children overlap")
				}
				union |= child.mask
				push(childID)
			}
			if union != n.mask {
				t.Fatalf("branch %d lost combinations", region.ID)
			}
			continue
		}
		combo := -1
		for c := 0; c < 4; c++ {
			if n.mask == uint8(1<<c) {
				combo = c
			}
		}
		if combo < 0 {
			t.Fatal("leaf does not identify one set combination")
		}
		// Its score is a valid feasible lower bound for this bonus group.
		scores[string(rune('0'+combo))] = exactTinyRegionUpper(n.mask)
		if combo == 3 {
			maxAfterBest = queue.MaxUpper()
		}
	}
	if len(visited) != 5 || visited[0] != 0 || visited[1] != 2 ||
		visited[2] != 4 || visited[3] != 1 || visited[4] != 5 {
		t.Fatalf("unexpected best-first coverage order %v", visited)
	}
	if math.Abs(scores["3"]-17.7) > 1e-12 || scores["0"] != 10 || KthLower(scores, 2) != 10 ||
		pruned != 2 || queue.Len() != 0 || !math.IsInf(queue.MaxUpper(), -1) || maxAfterBest != 10 {
		t.Fatalf("top-two result scores=%v pruned=%d maxAfterBest=%g", scores, pruned, maxAfterBest)
	}
	// A global feasible lower bound may prune a branch containing no witness
	// for that lower bound. The both-set witness is outside the no-A branch.
	var outside BoundQueue
	if err := outside.Push(BoundRegion{ID: 1, Upper: exactTinyRegionUpper(tree[1].mask), Potential: 0}); err != nil {
		t.Fatal(err)
	}
	_, ok, discarded := outside.Pop(scores["3"])
	if ok || discarded != 1 {
		t.Fatal("global feasible lower did not prune outside branch")
	}
}

func TestBoundQueueTiesUnknownBoundsAndInvalidNumbers(t *testing.T) {
	var queue BoundQueue
	for _, region := range []BoundRegion{
		{ID: 9, Upper: 10, Potential: 5},
		{ID: 2, Upper: 10, Potential: 5},
		{ID: 1, Upper: 10, Potential: 4},
		{ID: 7, Upper: 9.9, Potential: 100},
		{ID: 30, Upper: math.Inf(1), Potential: math.Inf(1)},
		{ID: 31, Upper: math.Inf(1), Potential: -1},
	} {
		if err := queue.Push(region); err != nil {
			t.Fatal(err)
		}
	}
	for _, want := range []int{31, 30, 2, 9, 1} {
		region, ok, pruned := queue.Pop(10)
		if !ok || pruned != 0 || region.ID != want {
			t.Fatalf("strict-tie ordering got %+v, ok=%t pruned=%d, want %d", region, ok, pruned, want)
		}
	}
	_, ok, pruned := queue.Pop(10)
	if ok || pruned != 1 {
		t.Fatalf("strictly lower region survived: ok=%t pruned=%d", ok, pruned)
	}
	if err := queue.Push(BoundRegion{Upper: math.NaN()}); err == nil {
		t.Fatal("NaN upper accepted")
	}
	if err := queue.Push(BoundRegion{Upper: 1, Potential: math.NaN()}); err == nil {
		t.Fatal("NaN potential accepted")
	}
	if err := queue.Push(BoundRegion{ID: 5, Upper: 1}); err != nil {
		t.Fatal(err)
	}
	if _, ok, _ := queue.Pop(math.NaN()); !ok {
		t.Fatal("invalid threshold caused unsafe pruning")
	}
}

func TestKthLowerGroupsFiniteFeasibleScores(t *testing.T) {
	scores := map[string]float64{
		"none": 10, "both": 17.7,
		"invalid_nan": math.NaN(), "invalid_inf": math.Inf(1),
	}
	if math.Abs(KthLower(scores, 1)-17.7) > 1e-12 || KthLower(scores, 2) != 10 ||
		!math.IsInf(KthLower(scores, 3), -1) || !math.IsInf(KthLower(scores, 0), -1) {
		t.Fatalf("invalid or unfilled grouped lower bound: %g %g %g", KthLower(scores, 1), KthLower(scores, 2), KthLower(scores, 3))
	}
}
