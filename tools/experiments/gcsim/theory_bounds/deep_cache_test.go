package main

// Pure cache-contract checks. The managed bounds runner copies this beside the
// round-two harness; these tests do not construct a model or call the engine.
import (
	"errors"
	"testing"

	proto "genshinteamstracker/native/gcsim_optimizer/internal/theoryprototype"
)

func TestR2CompleteKeyCoversFullInput(t *testing.T) {
	start := proto.Seed(initialMains(), [4][10]float64{}, 0, 45)
	if err := start.Validate(45, true); err != nil {
		t.Fatal(err)
	}
	entry := &feasibleEntry{family: "source-validated-family", coords: []string{"wearer.atk"}, baseline: []float64{1.25}}
	entry.indices[0][0] = 0
	plan := r2CompleteAlternatingPlan()
	key := func(e *feasibleEntry, s proto.State, settings r2AlternatingPlan, method string) [32]byte {
		t.Helper()
		value, err := r2CompleteKey(method, e, s, settings)
		if err != nil {
			t.Fatal(err)
		}
		return value
	}
	base := key(entry, start, plan, r2AlternatingMethod)
	if base != key(entry, start, plan, r2AlternatingMethod) {
		t.Fatal("same full input changed key")
	}
	changedStart := start
	changedStart.Upgrades[0][0][0] += .25
	changedStart.Upgrades[0][0][1] -= .25
	if err := changedStart.Validate(45, true); err != nil {
		t.Fatal(err)
	}
	if base == key(entry, changedStart, plan, r2AlternatingMethod) {
		t.Fatal("different initial upgrades reused complete solve")
	}
	changedLines := start
	changedLines.Lines[0][0][0], changedLines.Lines[0][0][1] = changedLines.Lines[0][0][1], changedLines.Lines[0][0][0]
	if err := changedLines.Validate(45, true); err != nil {
		t.Fatal(err)
	}
	if base == key(entry, changedLines, plan, r2AlternatingMethod) {
		t.Fatal("different initial line layout reused complete solve")
	}
	changedConfig := plan
	changedConfig.LinesConfig.MaxIterations++
	if base == key(entry, start, changedConfig, r2AlternatingMethod) {
		t.Fatal("different line configuration reused complete solve")
	}
	changedSearch := plan
	changedSearch.LastSearch.InnerIterations++
	if base == key(entry, start, changedSearch, r2AlternatingMethod) {
		t.Fatal("different final search configuration reused complete solve")
	}
	changedFirst := plan
	changedFirst.First.Search.InnerIterations++
	if base == key(entry, start, changedFirst, r2AlternatingMethod) {
		t.Fatal("different first search configuration reused complete solve")
	}
	if base == key(entry, start, plan, r2AlternatingMethod+"_new") {
		t.Fatal("different method version reused complete solve")
	}
	other := *entry
	other.family = "different-source-family"
	if base == key(&other, start, plan, r2AlternatingMethod) {
		t.Fatal("different source family reused complete solve")
	}
	other = *entry
	other.coords = []string{"wearer.hp"}
	if base == key(&other, start, plan, r2AlternatingMethod) {
		t.Fatal("different coordinates reused complete solve")
	}
	other = *entry
	other.baseline = []float64{1.5}
	if base == key(&other, start, plan, r2AlternatingMethod) {
		t.Fatal("different reference baseline reused complete solve")
	}
	other = *entry
	other.indices[0][0] = -1
	if base == key(&other, start, plan, r2AlternatingMethod) {
		t.Fatal("different coordinate mapping reused complete solve")
	}
	// Exercise the actual memoizer with distinct complete keys, not just the
	// hash builder. Only the repeated base request may avoid the callback.
	w := &feasibleWorld{numericReuse: true}
	calls := 0
	solve := func() (proto.Result, error) {
		calls++
		return proto.Result{State: start, Value: float64(calls), Evaluations: 1}, nil
	}
	if _, hit, err := r2MemoizedResult(w, base, 45, solve); err != nil || hit {
		t.Fatal("base solve did not run", hit, err)
	}
	changedFamily := *entry
	changedFamily.family = "different-source-family"
	changedRef := *entry
	changedRef.baseline = []float64{1.5}
	variants := [][32]byte{
		key(entry, changedStart, plan, r2AlternatingMethod),
		key(entry, start, changedConfig, r2AlternatingMethod),
		key(&changedFamily, start, plan, r2AlternatingMethod),
		key(&changedRef, start, plan, r2AlternatingMethod),
	}
	for index, variant := range variants {
		if _, hit, err := r2MemoizedResult(w, variant, 45, solve); err != nil || hit || calls != index+2 {
			t.Fatal("changed complete input failed to run fresh", index, hit, calls, err)
		}
	}
	if _, hit, err := r2MemoizedResult(w, base, 45, solve); err != nil || !hit || calls != 5 {
		t.Fatal("same full input repeated work", hit, calls, err)
	}
}

func TestR2MemoizedResultFullHitAndCopy(t *testing.T) {
	state := proto.Seed(initialMains(), [4][10]float64{}, 0, 45)
	w := &feasibleWorld{numericReuse: true}
	key := [32]byte{1}
	calls := 0
	solve := func() (proto.Result, error) {
		calls++
		return proto.Result{State: state, Value: 123, Evaluations: 77, Stop: "completed"}, nil
	}
	first, hit, err := r2MemoizedResult(w, key, 45, solve)
	if err != nil || hit || calls != 1 || first.Evaluations != 77 {
		t.Fatalf("first complete solve: hit=%t calls=%d result=%+v err=%v", hit, calls, first, err)
	}
	first.State.Upgrades[0][0][0] = 999
	second, hit, err := r2MemoizedResult(w, key, 45, solve)
	if err != nil || !hit || calls != 1 || second.Evaluations != 0 || second.State != state || second.Value != 123 {
		t.Fatalf("cached complete solve: hit=%t calls=%d result=%+v err=%v", hit, calls, second, err)
	}
	second.State.Mains[0][2] = "em"
	third, hit, err := r2MemoizedResult(w, key, 45, solve)
	if err != nil || !hit || calls != 1 || third.State != state {
		t.Fatal("return mutation changed cached witness", hit, calls, err)
	}
}

func TestR2MemoizedResultRetriesErrorsAndInvalidCompletions(t *testing.T) {
	state := proto.Seed(initialMains(), [4][10]float64{}, 0, 45)
	w := &feasibleWorld{numericReuse: true}
	key := [32]byte{2}
	transient := errors.New("transient solve error")
	calls := 0
	solve := func() (proto.Result, error) {
		calls++
		switch calls {
		case 1, 2:
			return proto.Result{}, transient
		case 3:
			return proto.Result{Value: 1}, nil // Invalid zero-value witness.
		default:
			return proto.Result{State: state, Value: 7, Evaluations: 4}, nil
		}
	}
	for i := 0; i < 2; i++ {
		_, hit, err := r2MemoizedResult(w, key, 45, solve)
		if hit || !errors.Is(err, transient) || len(w.numericCache) != 0 {
			t.Fatal("error was cached", i, hit, err)
		}
	}
	if _, hit, err := r2MemoizedResult(w, key, 45, solve); hit || err == nil || len(w.numericCache) != 0 {
		t.Fatal("invalid completed result was cached", hit, err)
	}
	if _, hit, err := r2MemoizedResult(w, key, 45, solve); hit || err != nil || calls != 4 {
		t.Fatal("retry did not complete fresh", hit, calls, err)
	}
	if _, hit, err := r2MemoizedResult(w, key, 45, solve); !hit || err != nil || calls != 4 {
		t.Fatal("valid completion was not cached", hit, calls, err)
	}
}
