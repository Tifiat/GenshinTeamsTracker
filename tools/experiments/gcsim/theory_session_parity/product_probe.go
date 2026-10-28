// Scratch-only owner: tools/experiments/gcsim/theory_session_parity. The managed
// parity runner copies this file into its disposable theorysearch package and
// removes that overlay with the job. Replace it with an explicitly reviewed
// diagnostic if reused; these methods make no production API commitment.
package theorysearch

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
	"genshinteamstracker/native/gcsim_optimizer/internal/theoryteams"
)

const parityFormulaLimit = 800000
const parityGradientLimit = 200000

type ParityCandidate struct {
	Packages [4]domain.Package `json:"packages"`
	State    alloc.State       `json:"state"`
	Value    float64           `json:"value"`
	Family   string            `json:"family"`
}

type ParityPhase struct {
	Pool        []ParityCandidate   `json:"pool"`
	Bank        []ParityCandidate   `json:"bank"`
	Aliases     map[string][]string `json:"aliases"`
	Visited     map[string]string   `json:"visited"`
	Refined     map[string]int      `json:"refined"`
	Unavailable map[string][]string `json:"unavailable"`
	Work        Work                `json:"work"`
}

type ParityAnchor struct {
	Pass  int    `json:"pass"`
	Actor int    `json:"actor"`
	Tuple string `json:"tuple"`
}

type ParityTotals struct {
	Formula  int `json:"formula"`
	Gradient int `json:"gradient"`
}

// Strip only the product's final frame suffix. A research program:<sha> or
// context:<sha> already denotes an arithmetic identity and remains intact.
func normalizeParityFamily(family string) string {
	colon := strings.LastIndexByte(family, ':')
	if colon <= 0 || len(family)-colon-1 != 64 {
		return family
	}
	if !strings.Contains(family[:colon], ":") {
		return family
	}
	for _, digit := range family[colon+1:] {
		if !(digit >= '0' && digit <= '9') && !(digit >= 'a' && digit <= 'f') && !(digit >= 'A' && digit <= 'F') {
			return family
		}
	}
	return family[:colon]
}

func parityCandidate(c candidate) ParityCandidate {
	return ParityCandidate{Packages: copyPackages(c.packages), State: c.state, Value: c.value, Family: normalizeParityFamily(c.family)}
}

func parityBranchPhase(b *branch) ParityPhase {
	out := ParityPhase{Pool: []ParityCandidate{}, Bank: []ParityCandidate{}, Aliases: map[string][]string{}, Visited: map[string]string{}, Refined: map[string]int{}, Unavailable: map[string][]string{}}
	if b == nil {
		return out
	}
	// Sort using the live core keys first. Normalization is evidence-only and
	// never changes search identities, ordering, values, or numerical feedback.
	for _, c := range sorted(b.pool) {
		out.Pool = append(out.Pool, parityCandidate(c))
	}
	for _, c := range b.bank {
		out.Bank = append(out.Bank, parityCandidate(c))
	}
	for family, aliases := range b.aliases {
		key := normalizeParityFamily(family)
		for tuple := range aliases {
			out.Aliases[key] = append(out.Aliases[key], tuple)
		}
	}
	for family, tuples := range out.Aliases {
		sort.Strings(tuples)
		unique := tuples[:0]
		for _, tuple := range tuples {
			if len(unique) == 0 || unique[len(unique)-1] != tuple {
				unique = append(unique, tuple)
			}
		}
		out.Aliases[family] = unique
	}
	for tuple, family := range b.visited {
		out.Visited[tuple] = normalizeParityFamily(family)
	}
	for family, level := range b.refined {
		key := normalizeParityFamily(family)
		if previous, exists := out.Refined[key]; !exists || level > previous {
			out.Refined[key] = level
		}
	}
	for tuple, unavailable := range b.unavailable {
		reasons := append([]string{}, unavailable.Reasons...)
		sort.Strings(reasons)
		out.Unavailable[tuple] = reasons
	}
	out.Work = b.work
	return out
}

// Read these value-only copies at a phase boundary on the session's owning
// goroutine. Retained branch evidence remains readable after Close.
func (s *Session) ParityPhase() ParityPhase {
	if s == nil {
		return parityBranchPhase(nil)
	}
	return parityBranchPhase(s.active)
}

func (s *Session) ParityArchive() ParityPhase {
	if s == nil {
		return parityBranchPhase(nil)
	}
	return parityBranchPhase(s.archive)
}

type parityGuard struct {
	mu       sync.Mutex
	deadline time.Time
	totals   ParityTotals
}

func (g *parityGuard) checkDeadline() error {
	g.mu.Lock()
	defer g.mu.Unlock()
	if !g.deadline.IsZero() && !time.Now().Before(g.deadline) {
		return fmt.Errorf("Theory parity deadline exceeded: %w", context.DeadlineExceeded)
	}
	return nil
}

func (g *parityGuard) beforeObjective(gradient bool) error {
	g.mu.Lock()
	defer g.mu.Unlock()
	// Count attempted objective work before delegation, including the one
	// attempt that crosses a limit. No over-limit call reaches the evaluator.
	g.totals.Formula++
	if gradient {
		g.totals.Gradient++
	}
	if g.totals.Formula > parityFormulaLimit {
		return fmt.Errorf("Theory parity formula work exceeded %d", parityFormulaLimit)
	}
	if g.totals.Gradient > parityGradientLimit {
		return fmt.Errorf("Theory parity gradient work exceeded %d", parityGradientLimit)
	}
	if !g.deadline.IsZero() && !time.Now().Before(g.deadline) {
		return fmt.Errorf("Theory parity deadline exceeded: %w", context.DeadlineExceeded)
	}
	return nil
}

// This wrapper has no engine/provider/IO path. It delegates only to the frozen
// Resolver supplied by the managed diagnostic and observes returned objectives.
type ParityResolver struct {
	mu      sync.Mutex
	inner   Resolver
	guard   *parityGuard
	route   []string
	anchors []ParityAnchor
	closed  bool
}

func NewParityResolver(inner Resolver, deadline time.Time) *ParityResolver {
	return &ParityResolver{inner: inner, guard: &parityGuard{deadline: deadline}, route: []string{}, anchors: []ParityAnchor{}}
}

func (r *ParityResolver) Resolve(ctx context.Context, packages [4]domain.Package) (*Entry, []string, error) {
	if r == nil {
		return nil, nil, fmt.Errorf("nil Theory parity resolver")
	}
	r.mu.Lock()
	if r.closed || r.inner == nil {
		r.mu.Unlock()
		return nil, nil, fmt.Errorf("Theory parity resolver closed or unavailable")
	}
	if ctx == nil {
		r.mu.Unlock()
		return nil, nil, fmt.Errorf("nil Theory parity context")
	}
	if err := ctx.Err(); err != nil {
		r.mu.Unlock()
		return nil, nil, err
	}
	if err := r.guard.checkDeadline(); err != nil {
		r.mu.Unlock()
		return nil, nil, err
	}
	r.route = append(r.route, theoryteams.Key(packages))
	inner := r.inner
	r.mu.Unlock()
	entry, codes, err := inner.Resolve(ctx, packages)
	if entry == nil {
		return nil, append([]string(nil), codes...), err
	}
	out := *entry
	out.Uncertainty = append([]string(nil), entry.Uncertainty...)
	objective := entry.Objective
	if objective != nil {
		out.Objective = func(state alloc.State, gradient bool) (float64, [4][10]float64, error) {
			r.mu.Lock()
			closed, guard := r.closed, r.guard
			r.mu.Unlock()
			if closed {
				return 0, [4][10]float64{}, fmt.Errorf("Theory parity resolver closed")
			}
			if err := guard.beforeObjective(gradient); err != nil {
				return 0, [4][10]float64{}, err
			}
			return objective(state, gradient)
		}
	}
	return &out, append([]string(nil), codes...), err
}

func (r *ParityResolver) Fork() (Resolver, error) {
	if r == nil {
		return nil, fmt.Errorf("nil Theory parity resolver")
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.closed || r.inner == nil {
		return nil, fmt.Errorf("Theory parity resolver closed or unavailable")
	}
	if err := r.guard.checkDeadline(); err != nil {
		return nil, err
	}
	inner, err := r.inner.Fork()
	if err != nil {
		return nil, err
	}
	if inner == nil {
		return nil, fmt.Errorf("Theory parity fork returned no resolver")
	}
	return &ParityResolver{inner: inner, guard: r.guard, route: append([]string{}, r.route...), anchors: append([]ParityAnchor{}, r.anchors...)}, nil
}

// The managed runner inserts this observer immediately before the options
// loop in pass. It copies only the actual anchor key and performs no scoring.
func ParityRecordAnchor(b *branch, pass, actor int, tuple [4]domain.Package) {
	if b == nil {
		return
	}
	if resolver, ok := b.world.(*ParityResolver); ok && resolver != nil {
		resolver.mu.Lock()
		defer resolver.mu.Unlock()
		if !resolver.closed {
			resolver.anchors = append(resolver.anchors, ParityAnchor{Pass: pass, Actor: actor, Tuple: theoryteams.Key(tuple)})
		}
	}
}

func (r *ParityResolver) Anchors() []ParityAnchor {
	if r == nil {
		return []ParityAnchor{}
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	return append([]ParityAnchor{}, r.anchors...)
}

func (r *ParityResolver) Route() []string {
	if r == nil {
		return []string{}
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	return append([]string{}, r.route...)
}

func (r *ParityResolver) Totals() ParityTotals {
	if r == nil || r.guard == nil {
		return ParityTotals{}
	}
	r.guard.mu.Lock()
	defer r.guard.mu.Unlock()
	return r.guard.totals
}

func (r *ParityResolver) Close() {
	if r == nil {
		return
	}
	r.mu.Lock()
	if r.closed {
		r.mu.Unlock()
		return
	}
	r.closed = true
	inner := r.inner
	r.inner = nil
	r.mu.Unlock()
	if inner != nil {
		inner.Close()
	}
}

func (s *Session) ParityRoute() []string {
	if s == nil || s.active == nil {
		return []string{}
	}
	if resolver, ok := s.active.world.(*ParityResolver); ok {
		return resolver.Route()
	}
	return []string{}
}

func (s *Session) ParityAnchors() []ParityAnchor {
	if s == nil || s.active == nil {
		return []ParityAnchor{}
	}
	if resolver, ok := s.active.world.(*ParityResolver); ok {
		return resolver.Anchors()
	}
	return []ParityAnchor{}
}
