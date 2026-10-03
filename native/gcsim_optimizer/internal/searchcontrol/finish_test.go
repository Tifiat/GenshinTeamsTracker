package searchcontrol

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestEarlyFinishStopsPreparationAndNeverCancelsOuter(t *testing.T) {
	path := filepath.Join(t.TempDir(), "finish")
	if err := os.WriteFile(path, nil, 0600); err != nil {
		t.Fatal(err)
	}
	outer := WithFile(context.Background(), path)
	ctx, closeSearch := Begin(outer)
	defer closeSearch()
	if !Requested(ctx) || ctx.Err() != context.Canceled {
		t.Fatal("early finish was not immediate")
	}
	Ready(ctx)
	Ready(ctx)
	if !Requested(ctx) || ctx.Err() != context.Canceled {
		t.Fatal("queued request ignored")
	}
	if outer.Err() != nil {
		t.Fatal("verification context cancelled")
	}
	closeSearch()
	closeSearch()
}

func TestFinishDuringSearchAndCancelAreDistinct(t *testing.T) {
	path := filepath.Join(t.TempDir(), "finish")
	outer, cancel := context.WithCancel(WithFile(context.Background(), path))
	defer cancel()
	ctx, closeSearch := Begin(outer)
	defer closeSearch()
	Ready(ctx)
	if err := os.WriteFile(path, nil, 0600); err != nil {
		t.Fatal(err)
	}
	select {
	case <-ctx.Done():
	case <-time.After(time.Second):
		t.Fatal("finish marker not observed")
	}
	if !Requested(ctx) || outer.Err() != nil {
		t.Fatal("finish killed outer request")
	}
	cancel()
	if outer.Err() != context.Canceled {
		t.Fatal("Cancel must still work during verification")
	}
	plain, kill := context.WithCancel(context.Background())
	other, closeOther := Begin(plain)
	defer closeOther()
	kill()
	if other.Err() != context.Canceled || Requested(other) {
		t.Fatal("hard cancellation mislabeled as finish")
	}
}

func TestClosedSearchCannotConsumeLateFinish(t *testing.T) {
	path := filepath.Join(t.TempDir(), "finish")
	ctx, closeSearch := Begin(WithFile(context.Background(), path))
	Ready(ctx)
	closeSearch()
	if err := os.WriteFile(path, nil, 0600); err != nil {
		t.Fatal(err)
	}
	if Requested(ctx) {
		t.Fatal("late click changed completed search")
	}
}
