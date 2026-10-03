package search

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/searchcontrol"
)

func TestFixedFinishBeforeSearchReportsNoCandidate(t *testing.T) {
	req, ir := searchFixtures(t)
	e, _ := fixedCandidateEngine(t, req, ir, DefaultConfig())
	path := filepath.Join(t.TempDir(), "finish")
	if err := os.WriteFile(path, nil, 0600); err != nil {
		t.Fatal(err)
	}
	outer := searchcontrol.WithFile(context.Background(), path)
	ctx, closeSearch := searchcontrol.Begin(outer)
	defer closeSearch()
	out, err := e.RunFixedCandidates(ctx, 160000, 6, 50)
	if !errors.Is(err, context.Canceled) || !searchcontrol.Requested(ctx) {
		t.Fatal("finish was not honored", err)
	}
	if len(out.Search.Finalists) != 0 || out.Evaluations != 0 {
		t.Fatal("early finish invented candidate or started work")
	}
	if outer.Err() != nil {
		t.Fatal("outer request cancelled")
	}
}

func TestFixedFinishDuringSearchRetainsAlreadyScoredImprovement(t *testing.T) {
	req, ir := searchFixtures(t)
	e, index := fixedCandidateEngine(t, req, ir, DefaultConfig())
	path := filepath.Join(t.TempDir(), "finish")
	outer := searchcontrol.WithFile(context.Background(), path)
	ctx, closeSearch := searchcontrol.Begin(outer)
	defer closeSearch()
	best := 0.0
	seen := 0
	e.ObserveCandidates(func(row ScoredAssignment) {
		seen++
		if row.DPS > best {
			best = row.DPS
		}
		if seen == 3 {
			if err := os.WriteFile(path, nil, 0600); err != nil {
				t.Fatal(err)
			}
			select {
			case <-ctx.Done():
			case <-time.After(time.Second):
				t.Fatal("finish marker was not observed during search")
			}
		}
	})
	out, err := e.RunFixedCandidates(ctx, 160000, 6, 50)
	if seen < 3 || !errors.Is(err, context.Canceled) || !searchcontrol.Requested(ctx) {
		t.Fatal("mid-search finish not exercised", seen, err)
	}
	if out.Search.Leader.DPS < best || len(out.Search.Finalists) == 0 {
		t.Fatal("completed candidate lost on finish")
	}
	for _, row := range out.Search.Finalists {
		if index.ValidateAssignment(row.Assignment) != nil {
			t.Fatal("partial candidate is not legal")
		}
	}
	if outer.Err() != nil {
		t.Fatal("verification cancelled")
	}
}
