package allsets

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/searchcontrol"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

func TestLegacyEarlyFinishDoesNotStartCapture(t *testing.T) {
	index, base, sources, provider, cfg := coordinatorFixture(t)
	cfg.SearchTime = 0
	cfg.ResultGroups, cfg.ResultAlternatives = 3, 2
	path := filepath.Join(t.TempDir(), "finish")
	if err := os.WriteFile(path, nil, 0600); err != nil {
		t.Fatal(err)
	}
	outer := searchcontrol.WithFile(context.Background(), path)
	ctx, closeSearch := searchcontrol.Begin(outer)
	defer closeSearch()
	calls := 0
	out, err := Run(ctx, index, base, sources, func(ctx context.Context, c *setcontext.Context) (setcontext.Capture, error) {
		calls++
		if ctx.Err() != nil {
			t.Fatal("mandatory capture interrupted by soft finish")
		}
		return provider(ctx, c)
	}, cfg)
	if !errors.Is(err, context.Canceled) || !searchcontrol.Requested(ctx) {
		t.Fatal("finish missing", err)
	}
	if calls != 0 || len(out.Finalists) != 0 {
		t.Fatal("early finish started capture or invented candidate", calls, len(out.Finalists))
	}
	if outer.Err() != nil {
		t.Fatal("finish cancelled final simulator context")
	}
}
