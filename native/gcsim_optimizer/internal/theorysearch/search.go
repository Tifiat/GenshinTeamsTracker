// Package theorysearch owns the resumable H-light / common-H catalog policy.
// It publishes feasible lower witnesses, never a Cartesian optimum claim.
package theorysearch

import (
	"context"
	"crypto/sha256"
	"fmt"
	"math"
	"sort"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
	"genshinteamstracker/native/gcsim_optimizer/internal/theorypackages"
)

const PolicyID = "theory_h_light_common_h_20261010_v1"

type Entry struct {
	Family        string
	ContextSHA256 string
	Uncertainty   []string
	Objective     alloc.Objective
}

// Fork must retain exact arithmetic identity and copy all mutable evaluator,
// route/cache, FIFO and counter state. No resolver may capture another engine
// universe while resolving, forking, or continuing a session.
type Resolver interface {
	Resolve(context.Context, [4]domain.Package) (*Entry, []string, error)
	Fork() (Resolver, error)
	Close()
}

type Config struct {
	Binding       string
	RequestSHA256 string
	SessionID     string
	Wearers       [4]string
	Initial       alloc.State
	Original      [4]domain.Package
	Domains       [4][]domain.Package
}

type candidate struct {
	packages [4]domain.Package
	state    alloc.State
	value    float64
	family   string
}

type Work struct {
	Formula            int `json:"formula_evaluations"`
	Gradient           int `json:"gradient_evaluations"`
	AllocationAttempts int `json:"allocation_attempts"`
	AliasHits          int `json:"tuple_alias_hits"`
	CompletedPasses    int `json:"completed_catalog_passes"`
	DeepBundles        int `json:"completed_deep_bundles"`
	CompletedSweeps    int `json:"completed_catalog_sweeps"`
	IndependentStarts  int `json:"independent_starts"`
	TransferredStarts  int `json:"transferred_starts"`
}

type branch struct {
	world       Resolver
	initial     alloc.State
	pool        map[string]candidate
	aliases     map[string]map[string]Alias
	unavailable map[string]Unavailable
	screened    map[string]bool
	visited     map[string]string
	refined     map[string]int
	bank        []candidate
	starts      []candidate
	work        Work
}

func newBranch(w Resolver, initial alloc.State) *branch {
	return &branch{world: w, initial: initial, pool: map[string]candidate{},
		aliases: map[string]map[string]Alias{}, unavailable: map[string]Unavailable{},
		screened: map[string]bool{}, visited: map[string]string{}, refined: map[string]int{}}
}
func copyMap[K comparable, V any](m map[K]V) map[K]V {
	n := make(map[K]V, len(m))
	for k, v := range m {
		n[k] = v
	}
	return n
}
func copyPackages(p [4]domain.Package) [4]domain.Package {
	for a := range p {
		p[a].Sets = append(p[a].Sets[:0:0], p[a].Sets...)
	}
	return p
}
func copyCandidate(c candidate) candidate { c.packages = copyPackages(c.packages); return c }
func (b *branch) fork() (*branch, error) {
	w, err := b.world.Fork()
	if err != nil {
		return nil, err
	}
	n := *b
	n.world = w
	n.pool = copyMap(b.pool)
	for k, v := range n.pool {
		n.pool[k] = copyCandidate(v)
	}
	n.aliases = copyMap(b.aliases)
	for f, rows := range n.aliases {
		n.aliases[f] = copyMap(rows)
		for k, v := range rows {
			n.aliases[f][k] = cloneAlias(v)
		}
	}
	n.unavailable = copyMap(b.unavailable)
	for k, v := range n.unavailable {
		n.unavailable[k] = cloneUnavailable(v)
	}
	n.screened = copyMap(b.screened)
	n.visited = copyMap(b.visited)
	n.refined = copyMap(b.refined)
	n.bank = append([]candidate(nil), b.bank...)
	for i := range n.bank {
		n.bank[i] = copyCandidate(n.bank[i])
	}
	n.starts = append([]candidate(nil), b.starts...)
	for i := range n.starts {
		n.starts[i] = copyCandidate(n.starts[i])
	}
	return &n, nil
}
func (b *branch) close() {
	if b != nil && b.world != nil {
		b.world.Close()
		b.world = nil
	}
}
func finite(v float64) bool { return !math.IsNaN(v) && !math.IsInf(v, 0) }
func sorted(pool map[string]candidate) []candidate {
	rows := make([]candidate, 0, len(pool))
	for _, c := range pool {
		rows = append(rows, c)
	}
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].value != rows[j].value {
			return rows[i].value > rows[j].value
		}
		return theorypackages.Key(rows[i].packages) < theorypackages.Key(rows[j].packages)
	})
	return rows
}
func (b *branch) offer(c candidate) {
	if !finite(c.value) || alloc.ValidateFull45(c.state) != nil {
		return
	}
	if old, ok := b.pool[c.family]; ok && old.value >= c.value {
		return
	}
	c = copyCandidate(c)
	b.pool[c.family] = c
	bank := []candidate{c}
	for _, old := range b.bank {
		if old.family != c.family && old.state != c.state {
			bank = append(bank, old)
		}
	}
	sort.Slice(bank, func(i, j int) bool {
		if bank[i].value != bank[j].value {
			return bank[i].value > bank[j].value
		}
		return bank[i].family < bank[j].family
	})
	b.bank = bank[:min(6, len(bank))]
}
func (b *branch) objective(ctx context.Context, e *Entry, p [4]domain.Package) alloc.Objective {
	return func(s alloc.State, want bool) (float64, [4][10]float64, error) {
		if err := ctx.Err(); err != nil {
			return 0, [4][10]float64{}, err
		}
		b.work.Formula++
		if want {
			b.work.Gradient++
		}
		v, g, err := e.Objective(s, want)
		if err == nil {
			if !finite(v) {
				return 0, g, fmt.Errorf("nonfinite Theory formula")
			}
			if want {
				for _, row := range g {
					for _, x := range row {
						if !finite(x) {
							return 0, g, fmt.Errorf("nonfinite Theory gradient")
						}
					}
				}
			}
			b.offer(candidate{p, s, v, e.Family})
		}
		return v, g, err
	}
}
func (b *branch) resolve(ctx context.Context, p [4]domain.Package, wearers [4]string) (*Entry, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	e, codes, err := b.world.Resolve(ctx, p)
	if err != nil {
		return nil, err
	}
	key := theorypackages.Key(p)
	if e == nil {
		if len(codes) == 0 {
			codes = []string{"source_resolution_unavailable"}
		}
		b.unavailable[key] = Unavailable{TupleKey: key, Packages: packageRows(p, wearers), Reasons: append([]string(nil), codes...)}
	} else {
		if e.Family == "" || e.Objective == nil {
			return nil, fmt.Errorf("incomplete Theory model entry")
		}
		if b.aliases[e.Family] == nil {
			b.aliases[e.Family] = map[string]Alias{}
		}
		b.aliases[e.Family][key] = Alias{TupleKey: key, Packages: packageRows(p, wearers), ContextSHA256: e.ContextSHA256, Uncertainty: append([]string(nil), e.Uncertainty...)}
	}
	return e, nil
}
func fresh(initial alloc.State, g [4][10]float64) []alloc.State {
	mains := initial.Mains
	choices, keys, values, mainValues := alloc.MainChoices(), alloc.StatKeys(), alloc.StatValues(), alloc.MainValues()
	for a := range mains {
		for slot := 2; slot < 5; slot++ {
			value := math.Inf(-1)
			choice := mains[a][slot]
			for _, main := range choices[slot] {
				for j, key := range keys {
					if main == key {
						v := g[a][j] * mainValues[main] / values[j]
						if v > value {
							value, choice = v, main
						}
					}
				}
			}
			mains[a][slot] = choice
		}
	}
	if alloc.ValidateFull45(initial) != nil {
		initial = alloc.Seed(initial.Mains, [4][10]float64{}, 0, 45)
	}
	return []alloc.State{initial, alloc.Seed(initial.Mains, g, 0, 45), alloc.Seed(mains, g, 0, 45)}
}
func seedPlan(fresh, bank []alloc.State) ([]alloc.State, int) {
	out := []alloc.State{fresh[2]}
	transferred := 0
	for _, s := range bank {
		if alloc.ValidateFull45(s) != nil {
			continue
		}
		duplicate := false
		for _, old := range out {
			if old == s {
				duplicate = true
			}
		}
		if !duplicate {
			out = append(out, s)
			transferred++
		}
		if len(out) == 3 {
			return out, transferred
		}
	}
	for _, s := range fresh {
		if len(out) == 3 {
			break
		}
		out = append(out, s)
	}
	return out, transferred
}
func (b *branch) seeds(ctx context.Context, e *Entry, p [4]domain.Package) ([]alloc.State, error) {
	obj := b.objective(ctx, e, p)
	bank := append([]candidate(nil), b.bank...)
	_, g, err := obj(b.initial, true)
	if err != nil {
		return nil, err
	}
	ranked := []candidate{}
	for _, old := range bank {
		if old.family == e.Family {
			continue
		}
		v, _, err := obj(old.state, false)
		if err != nil {
			return nil, err
		}
		old.value = v
		ranked = append(ranked, old)
	}
	sort.SliceStable(ranked, func(i, j int) bool { return ranked[i].value > ranked[j].value })
	states := []alloc.State{}
	for _, c := range ranked {
		states = append(states, c.state)
	}
	selected, transferred := seedPlan(fresh(b.initial, g), states)
	b.work.TransferredStarts += transferred
	b.work.IndependentStarts += len(selected) - transferred
	return selected, nil
}
func basicConfig(iterations int) alloc.Config {
	return alloc.Config{Budget: 45, Method: "spg", MaxIterations: iterations, LineSearch: true}
}
func (b *branch) visit(ctx context.Context, p [4]domain.Package, wearers [4]string) (string, error) {
	if err := ctx.Err(); err != nil {
		return "", err
	}
	key := theorypackages.Key(p)
	if family, known := b.visited[key]; known && (family == "" || b.screened[family]) {
		b.work.AliasHits++
		return family, nil
	}
	e, err := b.resolve(ctx, p, wearers)
	if err != nil {
		return "", err
	}
	if e == nil {
		b.visited[key] = ""
		return "", nil
	}
	b.visited[key] = e.Family
	if b.screened[e.Family] {
		return e.Family, nil
	}
	seeds, err := b.seeds(ctx, e, p)
	if err != nil {
		return e.Family, err
	}
	for _, s := range seeds {
		if err := alloc.ValidateFull45(s); err != nil {
			return e.Family, fmt.Errorf("illegal Theory search seed: %w", err)
		}
		b.work.AllocationAttempts++
		if _, err = alloc.Optimize(b.objective(ctx, e, p), s, basicConfig(4)); err != nil {
			return e.Family, err
		}
	}
	b.screened[e.Family] = true
	return e.Family, nil
}
func (b *branch) refine(ctx context.Context, c candidate, deep bool, wearers [4]string) error {
	e, err := b.resolve(ctx, c.packages, wearers)
	if err != nil || e == nil {
		return err
	}
	level := 1
	if deep {
		level = 2
	}
	if b.refined[c.family] >= level {
		return nil
	}
	obj := b.objective(ctx, e, c.packages)
	if _, err = alloc.FastWhole(obj, b.pool[c.family].state, basicConfig(40), alloc.FastConfig{Passes: 1, InnerIterations: 4}); err != nil {
		return err
	}
	if deep {
		if _, err = alloc.SlotLines(obj, b.pool[c.family].state, basicConfig(40), alloc.SlotLineConfig{Passes: 1, InnerIterations: 4}); err != nil {
			return err
		}
		if _, err = alloc.FastWhole(obj, b.pool[c.family].state, basicConfig(60), alloc.FastConfig{Passes: 1, InnerIterations: 6, MainPairs: true}); err != nil {
			return err
		}
	}
	b.refined[c.family] = level
	return nil
}
func packageKey(p domain.Package) string { return theorypackages.Key([4]domain.Package{p}) }
func distance(a, b [4]domain.Package) int {
	n := 0
	for i := range a {
		if packageKey(a[i]) != packageKey(b[i]) {
			n++
		}
	}
	return n
}
func beam(pool map[string]candidate) []candidate {
	rows := sorted(pool)
	if len(rows) < 2 {
		return rows
	}
	chosen := 1
	for i := 2; i < min(8, len(rows)); i++ {
		if distance(rows[i].packages, rows[0].packages) > distance(rows[chosen].packages, rows[0].packages) {
			chosen = i
		}
	}
	return []candidate{rows[0], rows[chosen]}
}
func initialTuples(original [4]domain.Package, domains [4][]domain.Package) [][4]domain.Package {
	ordered := domains
	for a, rows := range domains {
		ordered[a] = append([]domain.Package(nil), rows...)
		sort.Slice(ordered[a], func(i, j int) bool {
			x := sha256.Sum256([]byte(packageKey(ordered[a][i])))
			y := sha256.Sum256([]byte(packageKey(ordered[a][j])))
			return string(x[:]) < string(y[:])
		})
	}
	out := [][4]domain.Package{original}
	for k := 0; k < 8; k++ {
		p := original
		for a := range p {
			p[a] = ordered[a][(17+97*a+131*k)%len(ordered[a])]
		}
		out = append(out, p)
	}
	return out
}
func (b *branch) start(ctx context.Context, cfg Config) error {
	families := map[string]bool{}
	for _, p := range initialTuples(cfg.Original, cfg.Domains) {
		f, err := b.visit(ctx, p, cfg.Wearers)
		if err != nil {
			return err
		}
		if f != "" && !families[f] {
			families[f] = true
			if err = b.refine(ctx, b.pool[f], false, cfg.Wearers); err != nil {
				return err
			}
			b.starts = append(b.starts, b.pool[f])
		}
		if len(b.starts) == 2 {
			break
		}
	}
	if len(b.starts) == 0 {
		return ErrNoResult
	}
	return nil
}
func (b *branch) pass(ctx context.Context, cfg Config, pass int) error {
	for a := 0; a < 4; a++ {
		anchors := beam(b.pool)
		if pass == 0 && a == 0 {
			anchors = b.starts
		}
		for _, anchor := range anchors {
			touched := map[string]bool{}
			for _, option := range cfg.Domains[a] {
				p := anchor.packages
				p[a] = option
				f, err := b.visit(ctx, p, cfg.Wearers)
				if err != nil {
					return err
				}
				if f != "" {
					touched[f] = true
				}
			}
			b.work.CompletedSweeps++
			local := map[string]candidate{}
			for f := range touched {
				if c, ok := b.pool[f]; ok {
					local[f] = c
				}
			}
			rows := sorted(local)
			if len(rows) > 0 {
				if err := b.refine(ctx, rows[0], false, cfg.Wearers); err != nil {
					return err
				}
			}
		}
	}
	b.work.CompletedPasses = pass + 1
	return nil
}
func (b *branch) deep(ctx context.Context, cfg Config) error {
	rows := sorted(b.pool)
	picks := append([]candidate(nil), rows[:min(2, len(rows))]...)
	for i := 4; i < len(rows); i++ {
		if b.refined[rows[i].family] < 2 {
			picks = append(picks, rows[i])
			break
		}
	}
	for _, c := range picks {
		if err := b.refine(ctx, c, true, cfg.Wearers); err != nil {
			return err
		}
	}
	b.work.DeepBundles++
	return nil
}
