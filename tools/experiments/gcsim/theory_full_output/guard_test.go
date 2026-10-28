package theorysearch

import (
	"context"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
)

type stage15GuardFixture struct{ calls *int }

func (f *stage15GuardFixture) Resolve(context.Context, [4]domain.Package) (*Entry, []string, error) {
	return &Entry{Objective: func(alloc.State, bool) (float64, [4][10]float64, error) {
		*f.calls++
		return 7, [4][10]float64{}, nil
	}}, nil, nil
}
func (f *stage15GuardFixture) Fork() (Resolver, error) {
	return &stage15GuardFixture{calls: f.calls}, nil
}
func (f *stage15GuardFixture) Close() {}

func TestStage15GuardCountsAllForkWorkWithoutChangingValues(t *testing.T) {
	calls := 0
	r, err := NewStage15Resolver(&stage15GuardFixture{calls: &calls}, time.Now().Add(time.Minute), 946)
	if err != nil {
		t.Fatal(err)
	}
	entry, _, err := r.Resolve(context.Background(), [4]domain.Package{})
	if err != nil {
		t.Fatal(err)
	}
	value, _, err := entry.Objective(alloc.State{}, false)
	if value != 7 || err != nil {
		t.Fatal(value, err)
	}
	clone, err := r.Fork()
	if err != nil {
		t.Fatal(err)
	}
	other, _, err := clone.Resolve(context.Background(), [4]domain.Package{})
	if err != nil {
		t.Fatal(err)
	}
	value, _, err = other.Objective(alloc.State{}, true)
	if value != 7 || err != nil || calls != 2 || r.Totals().Formula != 2 || r.Totals().Gradient != 1 {
		t.Fatal(value, err, calls, r.Totals())
	}
	r.guard.totals.Formula = 800000
	if _, _, err = other.Objective(alloc.State{}, false); err == nil || calls != 2 || r.Totals().Formula != 800001 {
		t.Fatal("over-limit delegated or not counted", err, calls, r.Totals())
	}
	clone.Close()
	if _, _, err = other.Objective(alloc.State{}, false); err == nil {
		t.Fatal("closed objective survived")
	}
}
func TestStage15GuardDeadlineAndBranchResolveLimit(t *testing.T) {
	calls := 0
	r, _ := NewStage15Resolver(&stage15GuardFixture{calls: &calls}, time.Now().Add(-time.Second), 1)
	if _, _, err := r.Resolve(context.Background(), [4]domain.Package{}); err == nil || calls != 0 {
		t.Fatal("expired guard delegated", err, calls)
	}
	r, _ = NewStage15Resolver(&stage15GuardFixture{calls: &calls}, time.Now().Add(time.Minute), 1)
	r.resolveCalls = r.resolveLimit
	if _, _, err := r.Resolve(context.Background(), [4]domain.Package{}); err == nil {
		t.Fatal("branch resolve guard did not stop")
	}
}
