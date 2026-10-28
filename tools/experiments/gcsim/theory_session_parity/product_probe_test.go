// Scratch-only contracts copied beside product_probe.go into the managed
// native overlay. No engine, capture, product API, or gameplay evidence.
package theorysearch

import (
	"context"
	"errors"
	"reflect"
	"strings"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
	"genshinteamstracker/native/gcsim_optimizer/internal/theoryteams"
)

type parityProbeTestResolver struct {
	value          float64
	objectiveCalls int
	resolveCalls   int
	closed         bool
}

func (r *parityProbeTestResolver) Resolve(context.Context, [4]domain.Package) (*Entry, []string, error) {
	r.resolveCalls++
	return &Entry{Family: "program:" + strings.Repeat("a", 64) + ":" + strings.Repeat("b", 64), Uncertainty: []string{"fixture"}, Objective: func(_ alloc.State, gradient bool) (float64, [4][10]float64, error) {
		r.objectiveCalls++
		var g [4][10]float64
		if gradient {
			g[0][8] = 1.5
		}
		return r.value, g, nil
	}}, []string{"fixture-code"}, nil
}
func (r *parityProbeTestResolver) Fork() (Resolver, error) {
	out := *r
	return &out, nil
}
func (r *parityProbeTestResolver) Close() { r.closed = true }

func parityProbePackages(uid string) [4]domain.Package {
	var packages [4]domain.Package
	packages[0] = domain.Package{Sets: []contracts.SetRequirement{{SetUID: uid, Count: 2}}}
	return packages
}

func TestParityFamilyNormalizationKeepsResearchKeysAndRemovesOnlyFrame(t *testing.T) {
	hash, frame := strings.Repeat("a", 64), strings.Repeat("B", 64)
	for _, test := range []struct{ source, want string }{
		{"program:" + hash, "program:" + hash},
		{"context:" + hash, "context:" + hash},
		{"program:" + hash + ":" + frame, "program:" + hash},
		{"context:" + hash + ":" + frame, "context:" + hash},
		{"fixture:" + frame, "fixture:" + frame},
		{"program:" + hash + ":" + strings.Repeat("g", 64), "program:" + hash + ":" + strings.Repeat("g", 64)},
		{"program:" + hash + ":" + frame[:63], "program:" + hash + ":" + frame[:63]},
		{"", ""},
	} {
		if got := normalizeParityFamily(test.source); got != test.want {
			t.Fatalf("normalized %q to %q; want %q", test.source, got, test.want)
		}
	}
}

func TestParityResolverForkOwnsRouteAndSharesCumulativeGuards(t *testing.T) {
	inner := &parityProbeTestResolver{value: 7}
	parent := NewParityResolver(inner, time.Time{})
	first := parityProbePackages("first")
	entry, _, err := parent.Resolve(context.Background(), first)
	if err != nil {
		t.Fatal(err)
	}
	if value, gradient, err := entry.Objective(alloc.State{}, true); err != nil || value != 7 || gradient[0][8] != 1.5 {
		t.Fatal("wrapper changed objective arithmetic", value, gradient, err)
	}
	ParityRecordAnchor(&branch{world: parent}, 0, 0, first)
	forked, err := parent.Fork()
	if err != nil {
		t.Fatal(err)
	}
	child := forked.(*ParityResolver)
	childInner := child.inner.(*parityProbeTestResolver)
	childInner.value = 9
	second := parityProbePackages("second")
	childEntry, _, err := child.Resolve(context.Background(), second)
	if err != nil {
		t.Fatal(err)
	}
	ParityRecordAnchor(&branch{world: child}, 1, 2, second)
	if value, gradient, err := childEntry.Objective(alloc.State{}, false); err != nil || value != 9 || gradient != [4][10]float64{} {
		t.Fatal("child callback was not independent", value, gradient, err)
	}
	if value, _, err := entry.Objective(alloc.State{}, false); err != nil || value != 7 {
		t.Fatal("child callback changed the parent", value, err)
	}
	wantTotals := ParityTotals{Formula: 3, Gradient: 1}
	if parent.Totals() != wantTotals || child.Totals() != wantTotals || parent.guard != child.guard {
		t.Fatal("fork lost cumulative guard state")
	}
	if !reflect.DeepEqual(parent.Route(), []string{theoryteams.Key(first)}) || !reflect.DeepEqual(child.Route(), []string{theoryteams.Key(first), theoryteams.Key(second)}) {
		t.Fatal("fork route did not preserve ordered independent traces")
	}
	if len(parent.Anchors()) != 1 || len(child.Anchors()) != 2 || child.Anchors()[0] != parent.Anchors()[0] || child.Anchors()[1] != (ParityAnchor{Pass: 1, Actor: 2, Tuple: theoryteams.Key(second)}) {
		t.Fatal("fork lost actual independent anchor traces")
	}
	anchors := child.Anchors()
	anchors[0].Tuple = "changed"
	if child.Anchors()[0].Tuple != theoryteams.Key(first) {
		t.Fatal("returned anchors alias resolver state")
	}
	route := child.Route()
	route[0] = "changed"
	if child.Route()[0] != theoryteams.Key(first) {
		t.Fatal("returned route aliases resolver state")
	}
	session := &Session{active: &branch{world: child}}
	if !reflect.DeepEqual(session.ParityRoute(), child.Route()) || !reflect.DeepEqual(session.ParityAnchors(), child.Anchors()) {
		t.Fatal("session did not expose its active branch route")
	}
	parent.Close()
	if !inner.closed || childInner.closed {
		t.Fatal("closing parent did not delegate or closed the child")
	}
	if _, _, err := entry.Objective(alloc.State{}, true); err == nil {
		t.Fatal("closed parent accepted a retained callback")
	}
	if value, _, err := childEntry.Objective(alloc.State{}, false); err != nil || value != 9 {
		t.Fatal("closing parent changed the child callback", value, err)
	}
	child.Close()
}

func TestParityPhaseCopiesAndNormalizesEvidence(t *testing.T) {
	base := "program:" + strings.Repeat("a", 64)
	family := base + ":" + strings.Repeat("b", 64)
	other := "context:" + strings.Repeat("c", 64)
	first, second := parityProbePackages("first"), parityProbePackages("second")
	b := newBranch(nil, alloc.State{})
	b.pool[family] = candidate{packages: first, value: 7, family: family}
	b.pool[other] = candidate{packages: second, value: 9, family: other}
	b.bank = []candidate{b.pool[family], b.pool[other]}
	b.aliases[family] = map[string]Alias{"z": {}, "a": {}}
	b.visited["first"], b.visited["missing"] = family, ""
	b.refined[family] = 2
	b.unavailable["missing"] = Unavailable{Reasons: []string{"z-reason", "a-reason"}}
	b.work.Formula = 3
	session := &Session{active: b, archive: b}
	phase := session.ParityPhase()
	if len(phase.Pool) != 2 || phase.Pool[0].Value != 9 || phase.Pool[1].Family != base || phase.Bank[0].Value != 7 ||
		!reflect.DeepEqual(phase.Aliases[base], []string{"a", "z"}) || phase.Visited["first"] != base || phase.Visited["missing"] != "" || phase.Refined[base] != 2 || !reflect.DeepEqual(phase.Unavailable["missing"], []string{"a-reason", "z-reason"}) {
		t.Fatal("phase changed sorted pool/bank order or failed to normalize family evidence", phase)
	}
	phase.Pool[0].Packages[0].Sets[0].SetUID = "changed"
	phase.Bank[0].Packages[0].Sets[0].SetUID = "changed"
	phase.Pool[0].State.Mains[0][0] = "changed"
	phase.Aliases[base][0] = "changed"
	phase.Unavailable["missing"][0] = "changed"
	phase.Visited["first"], phase.Refined[base], phase.Work.Formula = "changed", 99, 99
	archive := session.ParityArchive()
	if b.pool[other].packages[0].Sets[0].SetUID != "second" || b.bank[0].packages[0].Sets[0].SetUID != "first" || b.pool[other].state.Mains[0][0] != "" ||
		!reflect.DeepEqual(archive.Aliases[base], []string{"a", "z"}) || archive.Visited["first"] != base || archive.Refined[base] != 2 || archive.Work.Formula != 3 || !reflect.DeepEqual(archive.Unavailable["missing"], []string{"a-reason", "z-reason"}) {
		t.Fatal("returned evidence mutated active/archive data")
	}
	var missing *Session
	if len(missing.ParityPhase().Pool) != 0 || len(missing.ParityArchive().Pool) != 0 || len(missing.ParityRoute()) != 0 || len(missing.ParityAnchors()) != 0 {
		t.Fatal("nil session evidence was not empty")
	}
}

func TestParityResolverGuardsDeadlineLimitsAndClosedCallbacks(t *testing.T) {
	inner := &parityProbeTestResolver{value: 7}
	resolver := NewParityResolver(inner, time.Time{})
	entry, _, err := resolver.Resolve(context.Background(), parityProbePackages("first"))
	if err != nil {
		t.Fatal(err)
	}
	resolver.guard.totals = ParityTotals{Formula: parityFormulaLimit - 1, Gradient: parityGradientLimit - 1}
	if _, _, err := entry.Objective(alloc.State{}, true); err != nil {
		t.Fatal("last permitted evaluator call was rejected", err)
	}
	if _, _, err := entry.Objective(alloc.State{}, false); err == nil || inner.objectiveCalls != 1 || resolver.Totals().Formula != parityFormulaLimit+1 {
		t.Fatal("formula limit reached the evaluator or lost attempted-work accounting")
	}
	resolver.guard.totals = ParityTotals{Gradient: parityGradientLimit}
	if _, _, err := entry.Objective(alloc.State{}, true); err == nil || inner.objectiveCalls != 1 || resolver.Totals().Gradient != parityGradientLimit+1 {
		t.Fatal("gradient limit reached the evaluator")
	}
	resolver.guard.totals = ParityTotals{}
	resolver.guard.deadline = time.Now().Add(-time.Second)
	if _, _, err := entry.Objective(alloc.State{}, false); !errors.Is(err, context.DeadlineExceeded) || inner.objectiveCalls != 1 {
		t.Fatal("expired objective deadline reached the evaluator", err)
	}
	if _, _, err := resolver.Resolve(context.Background(), parityProbePackages("second")); !errors.Is(err, context.DeadlineExceeded) || inner.resolveCalls != 1 {
		t.Fatal("expired resolution deadline reached the resolver", err)
	}
	resolver.Close()
	resolver.Close()
	if _, err := resolver.Fork(); err == nil {
		t.Fatal("closed resolver accepted a fork")
	}
	var missing *ParityResolver
	if _, _, err := missing.Resolve(context.Background(), firstParityProbeEmpty()); err == nil {
		t.Fatal("nil resolver accepted Resolve")
	}
	if _, err := missing.Fork(); err == nil || missing.Totals() != (ParityTotals{}) || len(missing.Route()) != 0 {
		t.Fatal("nil resolver stubs were not safe")
	}
	missing.Close()
	var zero ParityResolver
	if zero.Totals() != (ParityTotals{}) || len(zero.Anchors()) != 0 {
		t.Fatal("zero-value resolver evidence was not safe")
	}
}

func firstParityProbeEmpty() [4]domain.Package { return [4]domain.Package{} }
