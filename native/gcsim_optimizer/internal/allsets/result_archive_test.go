package allsets

import (
	"fmt"
	"reflect"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

func TestNeutralStabilizationPanelIgnoresExpandedOutputLimits(t *testing.T) {
	index, base, _, _, _ := coordinatorFixture(t)
	core := newResultArchive(1)
	outputs := map[int]*resultArchive{
		2:  newResultArchive(2),
		7:  newResultArchive(7),
		50: newResultArchive(50),
	}
	for group := 0; group < 12; group++ {
		packs := archiveFourPiece(fmt.Sprintf("set_%02d", group))
		var bestSlots, alternateSlots []int
		for slot := 0; slot < 5; slot++ {
			if group&(1<<slot) != 0 {
				bestSlots = append(bestSlots, slot)
			}
			if (group+12)&(1<<slot) != 0 {
				alternateSlots = append(alternateSlots, slot)
			}
		}
		best := archiveCandidate(index, base, packs, archiveAssignmentWithCopies(index, bestSlots...), 200-float64(group))
		alternate := archiveCandidate(index, base, packs, archiveAssignmentWithCopies(index, alternateSlots...), 100-float64(group))
		core.offer(best)
		core.offer(alternate)
		for _, output := range outputs {
			output.offer(best)
			output.offer(alternate)
		}
	}

	const coreLimit = 7
	want := neutralStabilizationFinalists(core, coreLimit)
	if len(want) != coreLimit {
		t.Fatalf("core panel has %d groups, want %d", len(want), coreLimit)
	}
	for rank, candidate := range want {
		wantSet := fmt.Sprintf("set_%02d", rank)
		if candidate.Packages[0].Sets[0].SetUID != wantSet || candidate.Score.DPS != 200-float64(rank) {
			t.Fatalf("core panel did not keep the best group leader at rank %d: %+v", rank, candidate)
		}
	}
	for _, limits := range [][2]int{{3, 2}, {5, 7}, {50, 50}} {
		groups, alternatives := limits[0], limits[1]
		display := outputs[alternatives]
		shown := display.top(groups)
		if len(shown) > groups*alternatives {
			t.Fatalf("display returned %d rows for %dx%d", len(shown), groups, alternatives)
		}
		got := neutralStabilizationFinalists(core, coreLimit)
		if !reflect.DeepEqual(got, want) {
			t.Fatalf("core panel changed for %dx%d output limits", groups, alternatives)
		}
	}

	// The old output-derived stabilization choice widened its work when an
	// expanded request asked for more than seven groups.
	largeDisplay := outputs[50]
	oldLimit := 50
	old := chooseFinalists(largeDisplay.top(oldLimit), oldLimit)
	if len(old) <= len(want) {
		t.Fatalf("fixture does not distinguish the old output-derived panel: old=%d core=%d", len(old), len(want))
	}
}

func archiveFourPiece(uid string) [4]domain.Package {
	var packs [4]domain.Package
	for actor := range packs {
		packs[actor] = domain.Package{Sets: []contracts.SetRequirement{{SetUID: uid, Count: 4}}}
	}
	return packs
}

func archiveTwoPlusTwo(left, right string) [4]domain.Package {
	var packs [4]domain.Package
	for actor := range packs {
		packs[actor] = domain.Package{Sets: []contracts.SetRequirement{
			{SetUID: left, Count: 2},
			{SetUID: right, Count: 2},
		}}
	}
	return packs
}

func archiveCandidate(
	index *domain.Index,
	ctx *setcontext.Context,
	packs [4]domain.Package,
	assignment domain.Assignment,
	dps float64,
) Candidate {
	return Candidate{
		Index:    index,
		Context:  ctx,
		Packages: packs,
		Score:    search.ScoredAssignment{Assignment: assignment, DPS: dps, Source: "archive-test"},
	}
}

func archiveAssignmentWithCopy(index *domain.Index, slot int) domain.Assignment {
	assignment := index.Incumbent
	// The coordinator fixture contains one duplicate copy of every inventory
	// item at ID+20. Replacing one slot keeps a complete, globally unique team.
	assignment[0][slot] += 20
	return assignment
}

func archiveAssignmentWithCopies(index *domain.Index, slots ...int) domain.Assignment {
	assignment := index.Incumbent
	for _, slot := range slots {
		assignment[0][slot] += 20
	}
	return assignment
}

func TestResultArchiveKeepsBestAlternativesPerCanonicalPackageGroup(t *testing.T) {
	index, base, _, _, _ := coordinatorFixture(t)
	fourA := archiveFourPiece("set_a")
	fourB := archiveFourPiece("set_b")
	twoTwo := archiveTwoPlusTwo("set_a", "set_b")
	keyA, keyB, keyTwoTwo := packageIdentity(fourA), packageIdentity(fourB), packageIdentity(twoTwo)
	if keyA == keyB || keyA == keyTwoTwo || keyB == keyTwoTwo {
		t.Fatalf("4p and 2+2 packages collapsed: %q, %q, %q", keyA, keyB, keyTwoTwo)
	}

	archive := newResultArchive(2)
	assignment := index.Incumbent
	a1 := archiveAssignmentWithCopy(index, 0)
	a2 := archiveAssignmentWithCopy(index, 1)
	a3 := archiveAssignmentWithCopy(index, 2)
	archive.offer(archiveCandidate(index, base, fourA, assignment, 99))
	archive.offer(archiveCandidate(index, base, fourA, assignment, 120)) // replace weaker same assignment
	archive.offer(archiveCandidate(index, base, fourA, a1, 110))
	archive.offer(archiveCandidate(index, base, fourA, a2, 105)) // outside this group's top two
	archive.offer(archiveCandidate(index, base, fourB, assignment, 120))
	archive.offer(archiveCandidate(index, base, fourB, a2, 110))
	archive.offer(archiveCandidate(index, base, twoTwo, assignment, 120))
	archive.offer(archiveCandidate(index, base, twoTwo, a3, 110))

	rows := archive.groups[keyA]
	if len(rows) != 2 || rows[0].Score.DPS != 120 || rows[1].Score.DPS != 110 {
		t.Fatalf("same-group replacement/top-K failed: %+v", rows)
	}
	if rows[0].Score.Assignment != assignment || rows[1].Score.Assignment != a1 {
		t.Fatalf("weak duplicate was not replaced or sorted: %+v", rows)
	}

	top := archive.top(3)
	seenAssignments := map[domain.Assignment]bool{}
	selectedGroups := map[string]bool{}
	for _, candidate := range top {
		key := packageIdentity(candidate.Packages)
		selectedGroups[key] = true
		if seenAssignments[candidate.Score.Assignment] {
			t.Fatalf("top returned the same full assignment twice: %v", candidate.Score.Assignment)
		}
		seenAssignments[candidate.Score.Assignment] = true
		if err := index.ValidateAssignment(candidate.Score.Assignment); err != nil {
			t.Fatalf("archive returned an assignment with reused/invalid IDs: %v", err)
		}
	}
	if len(selectedGroups) != 3 {
		t.Fatalf("top(3) returned %d package groups, want 3: %v", len(selectedGroups), selectedGroups)
	}
	if !seenAssignments[assignment] || !seenAssignments[a1] || !seenAssignments[a2] || !seenAssignments[a3] {
		t.Fatalf("top lost a distinct group alternative: %v", seenAssignments)
	}
}

func TestResultArchiveTiesAreDeterministicAndGroupsCanReenter(t *testing.T) {
	index, base, _, _, _ := coordinatorFixture(t)
	groupA := archiveFourPiece("set_a")
	groupB := archiveFourPiece("set_b")
	groupC := archiveTwoPlusTwo("set_a", "set_b")
	baseAssignment := index.Incumbent
	a1 := archiveAssignmentWithCopy(index, 0)
	a2 := archiveAssignmentWithCopy(index, 1)
	a3 := archiveAssignmentWithCopy(index, 2)
	a4 := archiveAssignmentWithCopy(index, 3)

	// Equal scores arrive in different orders. DPS then complete assignment and
	// canonical package identity must define the same output order every time.
	tied := []Candidate{
		archiveCandidate(index, base, groupA, a2, 100),
		archiveCandidate(index, base, groupB, a1, 100),
		archiveCandidate(index, base, groupA, baseAssignment, 100),
		archiveCandidate(index, base, groupC, a3, 100),
	}
	first, second := newResultArchive(2), newResultArchive(2)
	for _, row := range tied {
		first.offer(row)
	}
	for i := len(tied) - 1; i >= 0; i-- {
		second.offer(tied[i])
	}
	if !reflect.DeepEqual(first.top(3), second.top(3)) {
		t.Fatalf("equal-score archive order depends on offer order:\n%+v\n%+v", first.top(3), second.top(3))
	}
	topTwo := first.top(2)
	groupKeys := map[string]bool{}
	for _, candidate := range topTwo {
		groupKeys[packageIdentity(candidate.Packages)] = true
	}
	if len(groupKeys) != 2 || len(topTwo) > 4 {
		t.Fatalf("top(2) selected %d groups with %d rows", len(groupKeys), len(topTwo))
	}

	archive := newResultArchive(2)
	archive.offer(archiveCandidate(index, base, groupA, baseAssignment, 130))
	archive.offer(archiveCandidate(index, base, groupA, a1, 125))
	archive.offer(archiveCandidate(index, base, groupB, a2, 120))
	archive.offer(archiveCandidate(index, base, groupB, a3, 115))
	archive.offer(archiveCandidate(index, base, groupC, a4, 100))
	archive.offer(archiveCandidate(index, base, groupC, archiveAssignmentWithCopies(index, 0, 1), 95))
	before := archive.top(2)
	for _, candidate := range before {
		if packageIdentity(candidate.Packages) == packageIdentity(groupC) {
			t.Fatal("low-ranked group unexpectedly occupied one of the top two slots")
		}
	}
	if len(archive.groups[packageIdentity(groupC)]) != 2 {
		t.Fatal("dropped group did not retain its alternatives")
	}

	archive.offer(archiveCandidate(index, base, groupC, a4, 140))
	after := archive.top(2)
	var groupCAlternatives []domain.Assignment
	for _, candidate := range after {
		if packageIdentity(candidate.Packages) == packageIdentity(groupC) {
			groupCAlternatives = append(groupCAlternatives, candidate.Score.Assignment)
		}
	}
	if len(groupCAlternatives) != 2 || groupCAlternatives[0] != a4 || groupCAlternatives[1] != archiveAssignmentWithCopies(index, 0, 1) {
		t.Fatalf("re-entering group lost its retained alternative: %v", groupCAlternatives)
	}
}
