package setcontext

import (
	"context"
	"errors"
	"genshinteamstracker/native/gcsim_optimizer/internal/engineclient"
	"sync/atomic"
	"testing"
	"time"
)

func TestR3CaptureStableOrderAndBound(t *testing.T) {
	started := make(chan int, 2)
	release := []chan struct{}{make(chan struct{}), make(chan struct{})}
	var active, peak, checks atomic.Int32
	done := make(chan []r3CaptureSlot, 1)
	errs := make(chan error, 1)
	go func() {
		slots, err := r3CaptureSeeds(context.Background(), []uint64{10, 20}, func(ctx context.Context, i int, seed uint64) (engineclient.CompactResult, error) {
			current := active.Add(1)
			defer active.Add(-1)
			for previous := peak.Load(); current > previous && !peak.CompareAndSwap(previous, current); previous = peak.Load() {
			}
			started <- i
			select {
			case <-release[i]:
			case <-ctx.Done():
				return engineclient.CompactResult{}, ctx.Err()
			}
			r := engineclient.CompactResult{}
			r.Member.Seed = seed
			return r, nil
		}, func() error { checks.Add(1); return nil })
		done <- slots
		errs <- err
	}()
	for i := 0; i < 2; i++ {
		select {
		case <-started:
		case <-time.After(5 * time.Second):
			t.Fatal("capture children did not overlap")
		}
	}
	close(release[1])
	close(release[0])
	slots := <-done
	if err := <-errs; err != nil {
		t.Fatal(err)
	}
	if peak.Load() != 2 || active.Load() != 0 || checks.Load() != 2 || len(slots) != 2 || slots[0].result.Member.Seed != 10 || slots[1].result.Member.Seed != 20 {
		t.Fatal("capture order/ownership/bound differs")
	}
	active.Store(0)
	peak.Store(0)
	slots, err := r3CaptureSeeds(context.Background(), []uint64{1, 2, 3, 4, 5}, func(ctx context.Context, i int, seed uint64) (engineclient.CompactResult, error) {
		current := active.Add(1)
		defer active.Add(-1)
		for previous := peak.Load(); current > previous && !peak.CompareAndSwap(previous, current); previous = peak.Load() {
		}
		return engineclient.CompactResult{}, nil
	}, func() error { return nil })
	if err != nil || len(slots) != 5 || peak.Load() > 2 || active.Load() != 0 {
		t.Fatal("unbounded capture panel", err)
	}
}

func TestR3CaptureCancellationJoinAndIdentity(t *testing.T) {
	var joined atomic.Bool
	entered := make(chan struct{})
	injected := errors.New("capture integrity failure")
	checks := 0
	slots, err := r3CaptureSeeds(context.Background(), []uint64{1, 2}, func(ctx context.Context, i int, seed uint64) (engineclient.CompactResult, error) {
		if i == 0 {
			<-entered
			return engineclient.CompactResult{}, injected
		}
		close(entered)
		<-ctx.Done()
		joined.Store(true)
		return engineclient.CompactResult{}, ctx.Err()
	}, func() error { checks++; return nil })
	if !errors.Is(err, injected) || !joined.Load() || checks != 2 || len(slots) != 2 {
		t.Fatal("failed sibling escaped without cancel/join", err)
	}
	canceled, cancel := context.WithCancel(context.Background())
	cancel()
	called := false
	if _, err = r3CaptureSeeds(canceled, []uint64{1, 2}, func(context.Context, int, uint64) (engineclient.CompactResult, error) {
		called = true
		return engineclient.CompactResult{}, nil
	}, func() error { return nil }); !errors.Is(err, context.Canceled) || called {
		t.Fatal("pre-canceled batch ran")
	}
	checks = 0
	_, err = r3CaptureSeeds(context.Background(), []uint64{1}, func(context.Context, int, uint64) (engineclient.CompactResult, error) {
		return engineclient.CompactResult{}, nil
	}, func() error {
		checks++
		if checks == 2 {
			return injected
		}
		return nil
	})
	if !errors.Is(err, injected) || checks != 2 {
		t.Fatal("post-batch identity guard lost")
	}
	checks = 0
	called = false
	_, err = r3CaptureSeeds(context.Background(), []uint64{1}, func(context.Context, int, uint64) (engineclient.CompactResult, error) {
		called = true
		return engineclient.CompactResult{}, nil
	}, func() error { checks++; return injected })
	if !errors.Is(err, injected) || called || checks != 1 {
		t.Fatal("pre-batch identity guard lost")
	}
}
