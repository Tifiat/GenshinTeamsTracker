package allsets

import (
	"context"
	"errors"
	"math"
	"os"
	"path/filepath"
	"reflect"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
)

func jointTestPackage(uid string) domain.Package {
	if uid == "" {
		return domain.Package{}
	}
	return domain.Package{Sets: []contracts.SetRequirement{{SetUID: uid, Count: 2}}}
}

func jointTestAssignment() domain.Assignment {
	var assignment domain.Assignment
	for actor := range assignment {
		for slot := range assignment[actor] {
			assignment[actor][slot] = int64(actor*5 + slot + 1)
		}
	}
	return assignment
}

func jointTestCandidate(packs [4]domain.Package, dps float64) Candidate {
	return Candidate{Packages: packs, Score: search.ScoredAssignment{Assignment: jointTestAssignment(), DPS: dps, Source: "synthetic"}}
}

// This finite oracle is deliberately synthetic: it checks scheduler coverage
// and full-team callback flow, not gameplay formulas or source binding. The
// first holder activates one shared bonus, so overlapping copies never stack.
func syntheticSharedBonusScore(packs [4]domain.Package) (score, bonus float64) {
	if packs[0].Key() == "shared:2" {
		score++ // local fixed-assignment value of wearer 0's package
	}
	if packs[0].Key() == "plain:2" {
		score--
	}
	if packs[1].Key() == "plain:2" {
		score += 10
	}
	bonusByActor := [4]float64{2, 20, 0, 0}
	for actor, pack := range packs {
		if pack.Key() == "shared:2" {
			bonus = bonusByActor[actor]
			break // one shared, nonstacking activation
		}
	}
	return score + bonus, bonus
}

func TestExplorePackagePairsFindsSyntheticJointMoveAgainstExhaustiveTuples(t *testing.T) {
	shared, plain := jointTestPackage("shared"), jointTestPackage("plain")
	reserveC, reserveD := jointTestPackage("reserve_c"), jointTestPackage("reserve_d")
	rootPacks := [4]domain.Package{shared, plain, reserveC, reserveD}
	rootScore, _ := syntheticSharedBonusScore(rootPacks)
	root := jointTestCandidate(rootPacks, rootScore)

	// Each coordinate move loses: removing the donor drops the only bonus,
	// while adding a duplicate to wearer 1 leaves the donor's activation in
	// place and sacrifices wearer 1's stronger plain-package value.
	removeDonor := rootPacks
	removeDonor[0] = domain.Package{}
	addDuplicate := rootPacks
	addDuplicate[1] = shared
	removeScore, _ := syntheticSharedBonusScore(removeDonor)
	duplicateScore, _ := syntheticSharedBonusScore(addDuplicate)
	if !(removeScore < rootScore && duplicateScore < rootScore) {
		t.Fatalf("coordinate swaps should lose: root %.0f, remove %.0f, duplicate %.0f", rootScore, removeScore, duplicateScore)
	}

	// The exact finite domain is intentionally tiny: three package states for
	// each of the two effective wearers, with the other two fixed.
	actor0 := []domain.Package{shared, plain, {}}
	actor1 := []domain.Package{plain, shared, {}}
	exhaustiveBest := math.Inf(-1)
	var exhaustivePacks [4]domain.Package
	for _, first := range actor0 {
		for _, second := range actor1 {
			packs := [4]domain.Package{first, second, reserveC, reserveD}
			score, _ := syntheticSharedBonusScore(packs)
			if score > exhaustiveBest {
				exhaustiveBest, exhaustivePacks = score, packs
			}
		}
	}
	if exhaustiveBest != 20 || exhaustivePacks[0].Key() != "none" || exhaustivePacks[1].Key() != shared.Key() {
		t.Fatalf("unexpected exhaustive witness: score %.0f packages %q / %q", exhaustiveBest, exhaustivePacks[0].Key(), exhaustivePacks[1].Key())
	}

	choices := [4][]packageChoice{
		{{Pack: plain, DPS: 8}, {Pack: jointTestPackage(""), DPS: 7}},
		{{Pack: shared, DPS: 9}, {Pack: jointTestPackage(""), DPS: 6}},
	}
	var retained []Candidate
	var stats PackageJointStats
	evaluate := func(_ Candidate, move packagePairMove) ([]Candidate, error) {
		if move.Actors != [2]int{0, 1} {
			return nil, nil // the finite oracle has exactly two effective wearers
		}
		score, _ := syntheticSharedBonusScore(move.Packs) // re-score the complete tuple
		candidate := jointTestCandidate(move.Packs, score)
		return []Candidate{candidate}, nil
	}
	err := explorePackagePairs(context.Background(), []Candidate{root}, choices, evaluate,
		func(c Candidate) (Candidate, error) { return c, nil },
		func(c Candidate) { retained = append(retained, c) }, &stats)
	if err != nil {
		t.Fatal(err)
	}
	if !stats.Finished || stats.Roots != 1 || stats.Refined > jointPackageWidth {
		t.Fatalf("unexpected bounded-lane counts: %+v", stats)
	}
	best := math.Inf(-1)
	var winner Candidate
	for _, c := range retained {
		if c.Score.DPS > best {
			best, winner = c.Score.DPS, c
		}
	}
	if best != exhaustiveBest || winner.Packages[0].Key() != "none" || winner.Packages[1].Key() != shared.Key() {
		t.Fatalf("scheduler missed exhaustive finite witness: best %.0f tuple %q / %q, exhaustive %.0f", best, winner.Packages[0].Key(), winner.Packages[1].Key(), exhaustiveBest)
	}
	if winner.Score.Assignment != root.Score.Assignment {
		t.Fatal("synthetic callback changed the fixed physical assignment")
	}
}

func TestSyntheticSharedBonusIsZeroWhenNoPackageActivatesIt(t *testing.T) {
	packs := [4]domain.Package{{}, jointTestPackage("plain"), jointTestPackage("reserve_c"), jointTestPackage("reserve_d")}
	score, bonus := syntheticSharedBonusScore(packs)
	if bonus != 0 || score != 10 {
		t.Fatalf("inactive synthetic bonus contributed: score %.0f bonus %.0f", score, bonus)
	}
}

func TestPackageTeamFrontierOrdersNearTiesByRawDPS(t *testing.T) {
	makeCandidate := func(uid string, dps float64) Candidate {
		return jointTestCandidate([4]domain.Package{jointTestPackage(uid), jointTestPackage("b"), jointTestPackage("c"), jointTestPackage("d")}, dps)
	}
	rows := offerPackageTeam(nil, makeCandidate("a", 1))
	rows = offerPackageTeam(rows, makeCandidate("b", 1+0.75e-9))
	rows = offerPackageTeam(rows, makeCandidate("c", 1+1.5e-9))
	if got := []string{rows[0].Packages[0].Key(), rows[1].Packages[0].Key(), rows[2].Packages[0].Key()}; !reflect.DeepEqual(got, []string{"c:2", "b:2", "a:2"}) {
		t.Fatalf("near-tie team ordering is not raw-DPS transitive: %v", got)
	}
	rows = offerPackageTeam(rows, makeCandidate("c", 1+1.75e-9))
	if rows[0].Score.DPS != 1+1.75e-9 {
		t.Fatalf("same-tuple replacement ignored a real raw-DPS increase: %.12f", rows[0].Score.DPS)
	}
}

func TestPackageJointFrontiersAreDiverseAndDeterministic(t *testing.T) {
	buildChoices := func() []packageChoice {
		var rows []packageChoice
		for _, offer := range []packageChoice{
			{jointTestPackage("gamma"), 10},
			{jointTestPackage("alpha"), 10},
			{jointTestPackage("beta"), 9},
			{jointTestPackage("delta"), 8},
			{jointTestPackage("gamma"), 11},
			{jointTestPackage("gamma"), 7},
			{jointTestPackage("ignored_nan"), math.NaN()},
			{jointTestPackage("ignored_inf"), math.Inf(1)},
		} {
			rows = offerPackageChoice(rows, offer.Pack, offer.DPS)
		}
		return rows
	}
	choices := buildChoices()
	if !reflect.DeepEqual(choices, buildChoices()) {
		t.Fatal("package-choice frontier changed across identical input")
	}
	wantKeys := []string{"gamma:2", "alpha:2", "beta:2"}
	if len(choices) != jointPackageWidth {
		t.Fatalf("choice frontier width = %d, want %d", len(choices), jointPackageWidth)
	}
	for i, key := range wantKeys {
		if choices[i].Pack.Key() != key {
			t.Fatalf("choice[%d] = %q, want %q", i, choices[i].Pack.Key(), key)
		}
	}

	makeTeams := func() []Candidate {
		var rows []Candidate
		for _, row := range []struct {
			last string
			dps  float64
		}{
			{"d", 10}, {"e", 10}, {"f", 9}, {"g", 8}, {"d", 12}, {"d", 5}, {"nan", math.NaN()},
		} {
			packs := [4]domain.Package{jointTestPackage("a"), jointTestPackage("b"), jointTestPackage("c"), jointTestPackage(row.last)}
			rows = offerPackageTeam(rows, jointTestCandidate(packs, row.dps))
		}
		return rows
	}
	teams := makeTeams()
	if !reflect.DeepEqual(teams, makeTeams()) {
		t.Fatal("package-team frontier changed across identical input")
	}
	if len(teams) != jointPackageWidth {
		t.Fatalf("team frontier width = %d, want %d", len(teams), jointPackageWidth)
	}
	if got := []string{teams[0].Packages[3].Key(), teams[1].Packages[3].Key(), teams[2].Packages[3].Key()}; !reflect.DeepEqual(got, []string{"d:2", "e:2", "f:2"}) {
		t.Fatalf("team frontier lacks diverse deterministic tuples: %v", got)
	}
	if teams[0].Score.DPS != 12 {
		t.Fatalf("duplicate tuple did not retain its better complete team: %.0f", teams[0].Score.DPS)
	}
	if !samePackageTeams(teams, append([]Candidate(nil), teams...)) {
		t.Fatal("identical package teams reported different")
	}
	changedAssignment := append([]Candidate(nil), teams...)
	changedAssignment[0].Score.Assignment[0][0]++
	if samePackageTeams(teams, changedAssignment) {
		t.Fatal("physical assignment change was ignored when comparing package teams")
	}
}

func TestExplorePackagePairsCapsRootsAndRefinements(t *testing.T) {
	var roots []Candidate
	for i := 0; i < 6; i++ {
		packs := [4]domain.Package{jointTestPackage("root_" + string(rune('a'+i))), jointTestPackage("b"), jointTestPackage("c"), jointTestPackage("d")}
		roots = append(roots, jointTestCandidate(packs, float64(100-i)))
	}
	seenRoots := map[string]bool{}
	refined := 0
	var stats PackageJointStats
	err := explorePackagePairs(context.Background(), roots, [4][]packageChoice{},
		func(anchor Candidate, _ packagePairMove) ([]Candidate, error) {
			seenRoots[anchor.Packages[0].Key()] = true
			return nil, nil
		},
		func(c Candidate) (Candidate, error) { refined++; return c, nil },
		func(Candidate) {}, &stats)
	if err != nil {
		t.Fatal(err)
	}
	if !stats.Finished || stats.Roots != jointPackageWidth || stats.Refined != jointPackageWidth || refined != jointPackageWidth {
		t.Fatalf("root/refine work escaped strict frontier width: stats=%+v callbacks=%d", stats, refined)
	}
	for i := 0; i < jointPackageWidth; i++ {
		key := jointTestPackage("root_" + string(rune('a'+i))).Key()
		if !seenRoots[key] {
			t.Fatalf("top root %q was not evaluated", key)
		}
	}
	for _, uid := range []string{"root_d", "root_e", "root_f"} {
		if seenRoots[jointTestPackage(uid).Key()] {
			t.Fatalf("root below the bounded frontier was evaluated: %s", uid)
		}
	}
}

func TestExplorePackagePairsRetainsPartialWorkOnCancellationAndErrors(t *testing.T) {
	shared, plain := jointTestPackage("shared"), jointTestPackage("plain")
	packs := [4]domain.Package{shared, plain, jointTestPackage("reserve_c"), jointTestPackage("reserve_d")}
	root := jointTestCandidate(packs, 13)
	choices := [4][]packageChoice{{{Pack: jointTestPackage(""), DPS: 1}}, {{Pack: shared, DPS: 1}}}

	t.Run("cancellation after scored partial", func(t *testing.T) {
		ctx, cancel := context.WithCancel(context.Background())
		defer cancel()
		partialPacks := packs
		partialPacks[0] = domain.Package{}
		partial := jointTestCandidate(partialPacks, 17)
		var retained []Candidate
		var stats PackageJointStats
		err := explorePackagePairs(ctx, []Candidate{root}, choices,
			func(Candidate, packagePairMove) ([]Candidate, error) {
				cancel()
				return []Candidate{partial}, nil
			},
			func(c Candidate) (Candidate, error) { return c, nil },
			func(c Candidate) { retained = append(retained, c) }, &stats)
		if !errors.Is(err, context.Canceled) {
			t.Fatalf("cancellation error = %v", err)
		}
		if len(retained) != 1 || retained[0].Score.DPS != partial.Score.DPS || stats.Finished {
			t.Fatalf("valid scored partial was not retained before cancellation: retained=%+v stats=%+v", retained, stats)
		}
	})

	for _, phase := range []string{"evaluate", "refine"} {
		t.Run(phase+" callback error", func(t *testing.T) {
			callbackErr := errors.New("synthetic callback failure")
			var retained []Candidate
			var stats PackageJointStats
			var err error
			if phase == "evaluate" {
				partialPacks := packs
				partialPacks[0] = domain.Package{}
				partial := jointTestCandidate(partialPacks, 18)
				err = explorePackagePairs(context.Background(), []Candidate{root}, choices,
					func(Candidate, packagePairMove) ([]Candidate, error) { return []Candidate{partial}, callbackErr },
					func(c Candidate) (Candidate, error) { return c, nil },
					func(c Candidate) { retained = append(retained, c) }, &stats)
				if !hasRetainedScore(retained, partial.Score.DPS) {
					t.Fatal("evaluate partial candidate was dropped on error")
				}
			} else {
				partial := root
				partial.Score.DPS = 19
				err = explorePackagePairs(context.Background(), []Candidate{root}, choices,
					func(Candidate, packagePairMove) ([]Candidate, error) { return nil, nil },
					func(Candidate) (Candidate, error) { return partial, callbackErr },
					func(c Candidate) { retained = append(retained, c) }, &stats)
				if !hasRetainedScore(retained, partial.Score.DPS) {
					t.Fatal("refine partial incumbent was dropped on error")
				}
			}
			if !errors.Is(err, callbackErr) || stats.Finished {
				t.Fatalf("callback error/bounded completion mismatch: err=%v stats=%+v", err, stats)
			}
		})
	}
}

func hasRetainedScore(rows []Candidate, score float64) bool {
	for _, row := range rows {
		if row.Score.DPS == score {
			return true
		}
	}
	return false
}

func TestPackagePairSeedsPreserveReservationsAndExactNone(t *testing.T) {
	fixtureDir := filepath.Join("..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1")
	raw, err := os.ReadFile(filepath.Join(fixtureDir, "request_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	request, err := contracts.DecodeRequest(raw)
	if err != nil {
		t.Fatal(err)
	}
	// The saved fixture has exactly four five-piece sets. Add one real ID per
	// slot in a distinct set so the exact-none wearer has a legal 0-1-per-set
	// completion after the other two wearers stay reserved.
	maxID := int64(0)
	bySlot := map[string]contracts.Artifact{}
	for _, artifact := range request.Artifacts {
		if artifact.ArtifactID > maxID {
			maxID = artifact.ArtifactID
		}
		if _, found := bySlot[artifact.Slot]; !found {
			bySlot[artifact.Slot] = artifact
		}
	}
	for i, slot := range []string{"flower", "plume", "sands", "goblet", "circlet"} {
		artifact, found := bySlot[slot]
		if !found {
			t.Fatalf("fixture missing slot %q", slot)
		}
		artifact.ArtifactID = maxID + int64(i) + 1
		artifact.SetUID = "joint_none_" + slot
		request.Artifacts = append(request.Artifacts, artifact)
	}
	index, err := domain.Build(request, nil)
	if err != nil {
		t.Fatal(err)
	}
	var packs [4]domain.Package
	for actor, wearer := range request.Wearers {
		packs[actor] = domain.Package{Sets: wearer.SetRequirements()}
	}
	anchor := Candidate{Index: index, Packages: packs, Score: search.ScoredAssignment{Assignment: index.Incumbent}}
	movePacks := packs
	movePacks[0] = domain.Package{} // donor is replaced by an exact-none package
	movePacks[1] = packs[0]         // its package moves to the other wearer
	move := packagePairMove{Actors: [2]int{0, 1}, Packs: movePacks}
	var priorities [4]map[int64]float64
	for actor := range priorities {
		priorities[actor] = map[int64]float64{}
	}
	seeds, err := packagePairSeeds(context.Background(), anchor, move, priorities)
	if err != nil {
		t.Fatal(err)
	}
	if len(seeds) == 0 {
		t.Fatal("both real-ID allocation orders failed to seed the legal pair move")
	}
	seen := map[domain.Assignment]bool{}
	for _, seed := range seeds {
		if seen[seed] {
			t.Fatal("pair allocator returned a duplicate physical assignment")
		}
		seen[seed] = true
		for _, actor := range []int{2, 3} {
			if seed[actor] != anchor.Score.Assignment[actor] {
				t.Fatalf("reserved actor %d changed: got %v want %v", actor, seed[actor], anchor.Score.Assignment[actor])
			}
		}
		view, viewErr := index.ForPackages(move.Packs, seed, index.Coordinates)
		if viewErr != nil {
			t.Fatalf("pair seed is not legal under exact package view: %v", viewErr)
		}
		if viewErr = view.ValidateAssignment(seed); viewErr != nil {
			t.Fatalf("pair seed violates physical ID/slot legality: %v", viewErr)
		}
		counts := map[string]int{}
		for _, id := range seed[0] {
			uid, ok := index.ArtifactSetUID(id)
			if !ok {
				t.Fatalf("none wearer references unknown artifact %d", id)
			}
			counts[uid]++
		}
		for uid, count := range counts {
			if count > 1 {
				t.Fatalf("exact-none wearer formed an unselected bonus %s:%d", uid, count)
			}
		}
	}
	repeated, err := packagePairSeeds(context.Background(), anchor, move, priorities)
	if err != nil || !reflect.DeepEqual(repeated, seeds) {
		t.Fatalf("real-ID pair seed allocation is not deterministic: err=%v", err)
	}
}
