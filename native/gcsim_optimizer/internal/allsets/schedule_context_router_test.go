package allsets

import (
	"context"
	"errors"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

type scheduleRouteProbe struct {
	boundary map[string]bool
	calls    []string
}

func (p *scheduleRouteProbe) Resolve(target *setcontext.Context) (*setcontext.Handle, []string, error) {
	p.calls = append(p.calls, target.Key())
	if p.boundary[target.Key()] {
		return nil, []string{"schedule_change: active attack-speed modifier"}, nil
	}
	return nil, nil, nil
}

func TestScheduleRouterCapturesOnlyActiveCompleteContextsAndCachesThem(t *testing.T) {
	_, base, sources, baseCapture, _ := coordinatorFixture(t)
	actors := base.Actors()
	changes := map[string][]setcontext.Set{}
	for _, actor := range actors {
		changes[actor] = nil
	}
	neutral, err := base.Replace(changes)
	if err != nil {
		t.Fatal(err)
	}
	targetFor := func(uid string) *setcontext.Context {
		t.Helper()
		target, replaceErr := neutral.Replace(map[string][]setcontext.Set{
			actors[0]: {{UID: uid, Count: 2}},
		})
		if replaceErr != nil {
			t.Fatal(replaceErr)
		}
		return target
	}
	targetA, targetB, targetC := targetFor("schedule_a"), targetFor("schedule_b"), targetFor("schedule_c")
	probe := &scheduleRouteProbe{boundary: map[string]bool{targetA.Key(): true, targetB.Key(): true, targetC.Key(): true}}
	keys := []string{}
	provider := func(ctx context.Context, target *setcontext.Context) (setcontext.Capture, error) {
		keys = append(keys, target.Key())
		return baseCapture(ctx, target)
	}
	maxMembers := 2 * len(base.Seeds())
	session, err := setcontext.NewSession(provider, maxMembers)
	if err != nil {
		t.Fatal(err)
	}
	var recorded []string
	router := &scheduleContextRouter{
		sources: sources, model: probe, captures: session, maxMembers: maxMembers,
		attempts:  map[string]scheduleCaptureOutcome{},
		onCapture: func(reason string) { recorded = append(recorded, reason) },
	}

	if handle, boundaries, err := router.Resolve(context.Background(), neutral); err != nil || handle != nil || len(boundaries) != 0 {
		t.Fatalf("unchanged neutral context unexpectedly routed: handle=%v boundaries=%v err=%v", handle, boundaries, err)
	}
	if len(keys) != 0 {
		t.Fatalf("neutral route made a capture: %v", keys)
	}

	first, boundaries, err := router.Resolve(context.Background(), targetA)
	if err != nil || first == nil || len(boundaries) != 0 {
		t.Fatalf("first schedule context was not captured: handle=%v boundaries=%v err=%v", first, boundaries, err)
	}
	if again, _, err := router.Resolve(context.Background(), targetA); err != nil || again == nil {
		t.Fatalf("repeated target did not reuse capture: handle=%v err=%v", again, err)
	}
	second, _, err := router.Resolve(context.Background(), targetB)
	if err != nil || second == nil {
		t.Fatalf("different schedule context was not independently captured: handle=%v err=%v", second, err)
	}
	if len(keys) != 2 || keys[0] != targetA.Key() || keys[1] != targetB.Key() || keys[0] == keys[1] {
		t.Fatalf("capture keys were not complete-context isolated: %v", keys)
	}
	if session.AttemptedCaptureMembers() != maxMembers {
		t.Fatalf("unexpected bounded capture count: got %d want %d", session.AttemptedCaptureMembers(), maxMembers)
	}
	third, boundaries, err := router.Resolve(context.Background(), targetC)
	if err != nil || third != nil || len(boundaries) == 0 || !containsBoundary(boundaries, "schedule_capture_context_budget_exhausted:") {
		t.Fatalf("capture limit did not remain an explicit boundary: handle=%v boundaries=%v err=%v", third, boundaries, err)
	}
	_, repeated, err := router.Resolve(context.Background(), targetC)
	if err != nil || !containsBoundary(repeated, "schedule_capture_context_budget_exhausted:") || len(keys) != 2 {
		t.Fatalf("budget boundary retried or disappeared: boundaries=%v captures=%v err=%v", repeated, keys, err)
	}
	if !containsBoundary(recorded, "schedule_capture_changed_item_timing_unverified:") {
		t.Fatalf("captured graph did not carry timing caveat: %v", recorded)
	}
}

func TestScheduleRouterCachesFailedExactContextAttempt(t *testing.T) {
	_, base, sources, _, _ := coordinatorFixture(t)
	actors := base.Actors()
	neutralChanges := map[string][]setcontext.Set{}
	for _, actor := range actors {
		neutralChanges[actor] = nil
	}
	neutral, err := base.Replace(neutralChanges)
	if err != nil {
		t.Fatal(err)
	}
	target, err := neutral.Replace(map[string][]setcontext.Set{actors[0]: {{UID: "schedule_failure", Count: 2}}})
	if err != nil {
		t.Fatal(err)
	}
	probe := &scheduleRouteProbe{boundary: map[string]bool{target.Key(): true}}
	providerCalls := 0
	provider := func(context.Context, *setcontext.Context) (setcontext.Capture, error) {
		providerCalls++
		return setcontext.Capture{}, errors.New("synthetic capture failure")
	}
	limit := len(base.Seeds())
	session, err := setcontext.NewSession(provider, limit)
	if err != nil {
		t.Fatal(err)
	}
	router := &scheduleContextRouter{
		sources: sources, model: probe, captures: session, maxMembers: limit,
		attempts: map[string]scheduleCaptureOutcome{},
	}
	for attempt := 0; attempt < 2; attempt++ {
		handle, boundaries, resolveErr := router.Resolve(context.Background(), target)
		if resolveErr != nil || handle != nil || !containsBoundary(boundaries, "schedule_capture_failed:") {
			t.Fatalf("failed capture was not retained as boundary: handle=%v boundaries=%v err=%v", handle, boundaries, resolveErr)
		}
	}
	if providerCalls != 1 || session.AttemptedCaptureMembers() != limit {
		t.Fatalf("failed target retried or escaped accounting: provider calls=%d attempted=%d", providerCalls, session.AttemptedCaptureMembers())
	}
}

func containsBoundary(boundaries []string, prefix string) bool {
	for _, boundary := range boundaries {
		if len(boundary) >= len(prefix) && boundary[:len(prefix)] == prefix {
			return true
		}
	}
	return false
}
