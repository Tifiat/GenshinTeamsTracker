package setcontext

import (
	"context"
	"errors"
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/engineclient"
	"genshinteamstracker/native/gcsim_optimizer/internal/projectionmetrics"
	"path/filepath"
	"strconv"
	"sync"
)

type r3CaptureSlot struct {
	result    engineclient.CompactResult
	err       error
	attempted bool
}

// All children are joined before results, receipts, or identity checks escape.
// Each worker writes disjoint slots; seed order is independent of completion.
func r3CaptureSeeds(ctx context.Context, seeds []uint64,
	capture func(context.Context, int, uint64) (engineclient.CompactResult, error),
	verify func() error) (slots []r3CaptureSlot, err error) {
	if err = ctx.Err(); err != nil {
		return nil, err
	}
	if err = verify(); err != nil {
		return nil, err
	}
	finish := projectionmetrics.Begin("r3.capture_batch_wall")
	defer finish()
	childCtx, cancel := context.WithCancel(ctx)
	defer cancel()
	slots = make([]r3CaptureSlot, len(seeds))
	workers := min(2, len(seeds))
	projectionmetrics.Count("r3.capture_batch_workers", uint64(workers))
	var wg sync.WaitGroup
	for worker := 0; worker < workers; worker++ {
		wg.Add(1)
		go func(first int) {
			defer wg.Done()
			for i := first; i < len(seeds); i += workers {
				if childCtx.Err() != nil {
					return
				}
				slots[i].attempted = true
				slots[i].result, slots[i].err = capture(childCtx, i, seeds[i])
				if slots[i].err != nil {
					cancel()
					return
				}
			}
		}(worker)
	}
	wg.Wait()
	if ctx.Err() != nil {
		err = ctx.Err()
	}
	if err == nil {
		for _, slot := range slots {
			if slot.err != nil && !errors.Is(slot.err, context.Canceled) {
				err = slot.err
				break
			}
		}
	}
	if err == nil {
		for _, slot := range slots {
			if slot.err != nil {
				err = slot.err
				break
			}
			if !slot.attempted {
				err = context.Canceled
				break
			}
		}
	}
	err = errors.Join(err, verify())
	return slots, err
}

func (p *EngineProvider) r3Capture(ctx context.Context, c *Context, dir string, out Capture) (Capture, error) {
	capture := p.bound.RunCompact
	if p.includeEffects {
		capture = p.bound.RunCompactWithEffects
	}
	slots, err := r3CaptureSeeds(ctx, c.binding.Seeds, func(child context.Context, _ int, seed uint64) (engineclient.CompactResult, error) {
		result, e := capture(child, c.text, filepath.Join(dir, "seed-"+strconv.FormatUint(seed, 10)), seed, true)
		if e == nil && result.ConfigSHA256 != c.configSHA {
			e = fmt.Errorf("captured config mismatch")
		}
		if e == nil && p.includeEffects && result.Effects == nil {
			e = fmt.Errorf("capture effects missing")
		}
		return result, e
	}, p.bound.VerifyUnchanged)
	for i, slot := range slots {
		if slot.attempted {
			r := slot.result
			p.timings = append(p.timings, CaptureTiming{c.key, c.binding.Seeds[i], r.ProcessMS, r.DecodeMS, r.ResultSHA256})
		}
	}
	if err != nil {
		return Capture{}, err
	}
	for _, slot := range slots {
		out.Members = append(out.Members, slot.result.Member)
		if p.includeEffects {
			out.Effects = append(out.Effects, *slot.result.Effects)
		}
	}
	return out, nil
}
