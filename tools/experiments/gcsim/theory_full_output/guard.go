// Scratch-only diagnostic wrapper. Production numerical bodies are unchanged.
package theorysearch

import (
	"context"
	"fmt"
	"sync"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
)

type Stage15Totals struct {
	Formula    int     `json:"formula_attempts"`
	Gradient   int     `json:"gradient_attempts"`
	Resolve    int     `json:"cumulative_resolve_attempts"`
	Forks      int     `json:"forks"`
	ContextMS  float64 `json:"context_resolve_ms"`
	FormulaMS  float64 `json:"plain_formula_ms"`
	GradientMS float64 `json:"gradient_formula_ms"`
}
type stage15Guard struct {
	mu       sync.Mutex
	deadline time.Time
	totals   Stage15Totals
}
type Stage15Resolver struct {
	inner        Resolver
	guard        *stage15Guard
	resolveLimit int
	resolveCalls int
	closed       bool
}

func NewStage15Resolver(inner Resolver, deadline time.Time, catalog int) (*Stage15Resolver, error) {
	if inner == nil || deadline.IsZero() || catalog < 1 {
		return nil, fmt.Errorf("missing Stage15 resolver/diagnostic guard")
	}
	return &Stage15Resolver{inner: inner, guard: &stage15Guard{deadline: deadline}, resolveLimit: 9 + 16*catalog + 64}, nil
}
func (g *stage15Guard) alive() error {
	if !time.Now().Before(g.deadline) {
		return fmt.Errorf("Stage15 offline hard guard: %w", context.DeadlineExceeded)
	}
	return nil
}
func (r *Stage15Resolver) Resolve(ctx context.Context, packages [4]domain.Package) (*Entry, []string, error) {
	if r == nil || r.closed || r.inner == nil || ctx == nil {
		return nil, nil, fmt.Errorf("Stage15 resolver closed or unbound")
	}
	if err := ctx.Err(); err != nil {
		return nil, nil, err
	}
	r.guard.mu.Lock()
	err := r.guard.alive()
	if err == nil {
		r.resolveCalls++
		r.guard.totals.Resolve++
		if r.resolveCalls > r.resolveLimit {
			err = fmt.Errorf("Stage15 branch resolve hard guard exceeded %d", r.resolveLimit)
		}
	}
	r.guard.mu.Unlock()
	if err != nil {
		return nil, nil, err
	}
	started := time.Now()
	entry, codes, err := r.inner.Resolve(ctx, packages)
	r.guard.mu.Lock()
	r.guard.totals.ContextMS += float64(time.Since(started).Nanoseconds()) / 1e6
	r.guard.mu.Unlock()
	if entry == nil {
		return nil, append([]string(nil), codes...), err
	}
	out := *entry
	out.Uncertainty = append([]string(nil), entry.Uncertainty...)
	objective := entry.Objective
	if objective != nil {
		out.Objective = func(state alloc.State, gradient bool) (float64, [4][10]float64, error) {
			if r.closed {
				return 0, [4][10]float64{}, fmt.Errorf("Stage15 closed objective")
			}
			r.guard.mu.Lock()
			r.guard.totals.Formula++
			if gradient {
				r.guard.totals.Gradient++
			}
			err := r.guard.alive()
			if err == nil && r.guard.totals.Formula > 800000 {
				err = fmt.Errorf("Stage15 cumulative formula hard guard exceeded 800000")
			}
			if err == nil && r.guard.totals.Gradient > 200000 {
				err = fmt.Errorf("Stage15 cumulative gradient hard guard exceeded 200000")
			}
			r.guard.mu.Unlock()
			if err != nil {
				return 0, [4][10]float64{}, err
			}
			started := time.Now()
			value, derivative, err := objective(state, gradient)
			r.guard.mu.Lock()
			elapsed := float64(time.Since(started).Nanoseconds()) / 1e6
			if gradient {
				r.guard.totals.GradientMS += elapsed
			} else {
				r.guard.totals.FormulaMS += elapsed
			}
			r.guard.mu.Unlock()
			return value, derivative, err
		}
	}
	return &out, append([]string(nil), codes...), err
}
func (r *Stage15Resolver) Fork() (Resolver, error) {
	if r == nil || r.closed || r.inner == nil {
		return nil, fmt.Errorf("Stage15 cannot fork a closed resolver")
	}
	r.guard.mu.Lock()
	err := r.guard.alive()
	r.guard.mu.Unlock()
	if err != nil {
		return nil, err
	}
	inner, err := r.inner.Fork()
	if err != nil {
		return nil, err
	}
	if inner == nil {
		return nil, fmt.Errorf("Stage15 underlying fork returned nil")
	}
	r.guard.mu.Lock()
	r.guard.totals.Forks++
	r.guard.mu.Unlock()
	return &Stage15Resolver{inner: inner, guard: r.guard, resolveLimit: r.resolveLimit, resolveCalls: r.resolveCalls}, nil
}
func (r *Stage15Resolver) Totals() Stage15Totals {
	r.guard.mu.Lock()
	defer r.guard.mu.Unlock()
	return r.guard.totals
}
func (r *Stage15Resolver) Close() {
	if r == nil || r.closed {
		return
	}
	r.closed = true
	inner := r.inner
	r.inner = nil
	if inner != nil {
		inner.Close()
	}
}
