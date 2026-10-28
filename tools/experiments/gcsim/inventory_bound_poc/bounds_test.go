package evaluator_test

// Research-only real-vector enclosure/search. Not imported by the product.
// The dated inventory-bound concept gate owns this temporary implementation.
// Arithmetic toy cases below are NOT gameplay formulas; real cases consume
// active-engine IR and use the production evaluator as an exhaustive oracle.
// Floating-point enclosures are guarded and exhaustively checked on these
// finite domains, not formally certified for arbitrary future engine graphs.
import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

const maxDims = 32

type vec [maxDims]float64
type item struct {
	ID    int64              `json:"id"`
	Stats map[string]float64 `json:"stats"`
	V     vec                `json:"-"`
}
type region [][]int
type problem struct {
	Pools [][]item
	Ref   vec
	D     int
	G     *graph
	Score func(vec) float64
}
type node struct {
	Op    string
	In    []int
	Value float64
	Dim   int
}
type graph struct {
	N    []node
	Root int
	memo map[string]int
}

func newGraph() *graph { return &graph{memo: map[string]int{}} }
func scalar(op string, x []float64) float64 {
	switch op {
	case "add":
		s := 0.0
		for _, v := range x {
			s += v
		}
		return s
	case "multiply":
		s := 1.0
		for _, v := range x {
			s *= v
		}
		return s
	case "min":
		s := x[0]
		for _, v := range x[1:] {
			s = math.Min(s, v)
		}
		return s
	case "max":
		s := x[0]
		for _, v := range x[1:] {
			s = math.Max(s, v)
		}
		return s
	case "power":
		return math.Pow(x[0], x[1])
	case "select_lt":
		if x[0] < x[1] {
			return x[2]
		}
		return x[3]
	}
	panic("unsupported IR operation: " + op)
}
func (g *graph) make(n node) int {
	if n.Op != "constant" && n.Op != "artifact_stat" {
		fixed := true
		v := make([]float64, len(n.In))
		for j, i := range n.In {
			fixed = fixed && g.N[i].Op == "constant"
			v[j] = g.N[i].Value
		}
		if n.Op == "select_lt" && g.N[n.In[0]].Op == "constant" && g.N[n.In[1]].Op == "constant" {
			if v[0] < v[1] {
				return n.In[2]
			}
			return n.In[3]
		}
		if fixed {
			n = node{Op: "constant", Value: scalar(n.Op, v)}
		}
	}
	key := fmt.Sprintf("%s/%v/%g/%d", n.Op, n.In, n.Value, n.Dim)
	if i, ok := g.memo[key]; ok {
		return i
	}
	i := len(g.N)
	g.N = append(g.N, n)
	g.memo[key] = i
	return i
}
func (g *graph) c(v float64) int             { return g.make(node{Op: "constant", Value: v}) }
func (g *graph) x(d int) int                 { return g.make(node{Op: "artifact_stat", Dim: d}) }
func (g *graph) op(op string, in ...int) int { return g.make(node{Op: op, In: in}) }
func (g *graph) point(x vec) float64 {
	values := make([]float64, len(g.N))
	for i, n := range g.N {
		switch n.Op {
		case "constant":
			values[i] = n.Value
		case "artifact_stat":
			values[i] = x[n.Dim]
		default:
			a := make([]float64, len(n.In))
			for j, k := range n.In {
				a[j] = values[k]
			}
			values[i] = scalar(n.Op, a)
		}
	}
	return values[g.Root]
}
func (g *graph) trim() {
	old := g.N
	remap := map[int]int{}
	fresh := newGraph()
	var visit func(int) int
	visit = func(i int) int {
		if v, ok := remap[i]; ok {
			return v
		}
		n := old[i]
		n.In = append([]int(nil), n.In...)
		for j, k := range n.In {
			n.In[j] = visit(k)
		}
		v := fresh.make(n)
		remap[i] = v
		return v
	}
	fresh.Root = visit(g.Root)
	*g = *fresh
}

// f(x) = C + W dot (x-centre) + [-R,R]. The support function is taken
// over REAL joint item vectors in each slot (or their convex hull), not
// independent maxima, a mean item, or a locally maximized NLP value.
type affine struct {
	C, R float64
	W    vec
}
type bounder struct {
	P                  *problem
	Domain             region
	Centre, MeanTotals vec
	Values             []affine
	Box                bool
}

func (b *bounder) support(w vec) (float64, float64) {
	lo, hi := 0.0, 0.0
	if b.Box { // Deliberately looser diagnostic comparator, never the main search.
		for j := 0; j < b.P.D; j++ {
			low, high := 0.0, 0.0
			for s, pool := range b.Domain {
				a, z := math.Inf(1), math.Inf(-1)
				for _, k := range pool {
					v := b.P.Pools[s][k].V[j]
					a = math.Min(a, v)
					z = math.Max(z, v)
				}
				low += a
				high += z
			}
			low -= b.MeanTotals[j]
			high -= b.MeanTotals[j]
			if w[j] < 0 {
				low, high = high, low
			}
			lo += w[j] * low
			hi += w[j] * high
		}
		return lo, hi
	}
	for s, pool := range b.Domain {
		a, z := math.Inf(1), math.Inf(-1)
		for _, k := range pool {
			v := 0.0
			for j := 0; j < b.P.D; j++ {
				v += w[j] * b.P.Pools[s][k].V[j]
			}
			a = math.Min(a, v)
			z = math.Max(z, v)
		}
		lo += a
		hi += z
	}
	offset := 0.0
	for j := 0; j < b.P.D; j++ {
		offset += w[j] * b.MeanTotals[j]
	}
	return lo - offset, hi - offset
}
func (b *bounder) span(a affine) (float64, float64) {
	lo, hi := b.support(a.W)
	guard := 2e-12 * (1 + math.Abs(a.C) + math.Abs(lo) + math.Abs(hi) + a.R)
	return a.C + lo - a.R - guard, a.C + hi + a.R + guard
}
func (b *bounder) deviation(a affine) float64 {
	lo, hi := b.support(a.W)
	return math.Max(math.Abs(lo), math.Abs(hi)) + a.R
}
func scale(a affine, v float64) affine {
	a.C *= v
	a.R *= math.Abs(v)
	for j := range a.W {
		a.W[j] *= v
	}
	return a
}
func plus(a, z affine) affine {
	a.C += z.C
	a.R += z.R
	for j := range a.W {
		a.W[j] += z.W[j]
	}
	return a
}
func (b *bounder) multiply(a, z affine) affine {
	if fixed(a) {
		return scale(z, a.C)
	}
	if fixed(z) {
		return scale(a, z.C)
	}
	r := affine{C: a.C * z.C, R: math.Abs(a.C)*z.R + math.Abs(z.C)*a.R + b.deviation(a)*b.deviation(z)}
	for j := 0; j < b.P.D; j++ {
		r.W[j] = a.C*z.W[j] + z.C*a.W[j]
	}
	return r
}
func interval(lo, hi float64) affine { return affine{C: (lo + hi) / 2, R: (hi - lo) / 2} }
func fixed(a affine) bool {
	if a.R != 0 {
		return false
	}
	for _, v := range a.W {
		if v != 0 {
			return false
		}
	}
	return true
}
func (b *bounder) power(a, z affine) affine {
	if !fixed(z) {
		return affine{R: math.Inf(1)}
	}
	p := z.C
	if p == 0 {
		return affine{C: 1}
	}
	if p == 1 {
		return a
	}
	lo, hi := b.span(a)
	if lo <= 0 && (p < 0 || p != math.Trunc(p)) {
		return affine{R: math.Inf(1)}
	}
	centre := (lo + hi) / 2
	slope := p * math.Pow(centre, p-1)
	// Supremum of |f''| on an interval for a real constant power. On a
	// positive interval it is monotone; an integer >=2 crossing zero is safe.
	curvature := math.Abs(p*(p-1)) * math.Max(math.Abs(math.Pow(lo, p-2)), math.Abs(math.Pow(hi, p-2)))
	r := scale(a, slope)
	r.C += math.Pow(centre, p) - slope*centre
	r.R += 0.5 * curvature * math.Pow((hi-lo)/2, 2)
	return r
}
func (p *problem) upper(dom region, box bool) (float64, vec) {
	b := bounder{P: p, Domain: dom, Values: make([]affine, len(p.G.N)), Box: box}
	for s, pool := range dom {
		for _, k := range pool {
			for j := 0; j < p.D; j++ {
				b.MeanTotals[j] += p.Pools[s][k].V[j] / float64(len(pool))
			}
		}
	}
	for j := 0; j < p.D; j++ {
		b.Centre[j] = b.MeanTotals[j] - p.Ref[j]
	}
	for i, n := range p.G.N {
		r := affine{}
		switch n.Op {
		case "constant":
			r.C = n.Value
		case "artifact_stat":
			r.C = b.Centre[n.Dim]
			r.W[n.Dim] = 1
		case "add":
			for _, k := range n.In {
				r = plus(r, b.Values[k])
			}
		case "multiply":
			r.C = 1
			for _, k := range n.In {
				r = b.multiply(r, b.Values[k])
			}
		case "power":
			r = b.power(b.Values[n.In[0]], b.Values[n.In[1]])
		case "min", "max":
			r = b.Values[n.In[0]]
			for _, k := range n.In[1:] {
				z := b.Values[k]
				dl, dh := b.span(plus(r, scale(z, -1)))
				if n.Op == "min" && dh <= 0 || n.Op == "max" && dl >= 0 {
					continue
				}
				if n.Op == "min" && dl >= 0 || n.Op == "max" && dh <= 0 {
					r = z
					continue
				}
				al, ah := b.span(r)
				zl, zh := b.span(z)
				if n.Op == "min" {
					r = interval(math.Min(al, zl), math.Min(ah, zh))
				} else {
					r = interval(math.Max(al, zl), math.Max(ah, zh))
				}
			}
		case "select_lt":
			dl, dh := b.span(plus(b.Values[n.In[0]], scale(b.Values[n.In[1]], -1)))
			if dh < 0 {
				r = b.Values[n.In[2]]
			} else if dl >= 0 {
				r = b.Values[n.In[3]]
			} else {
				al, ah := b.span(b.Values[n.In[2]])
				zl, zh := b.span(b.Values[n.In[3]])
				r = interval(math.Min(al, zl), math.Max(ah, zh))
			}
		default:
			panic(n.Op)
		}
		if math.IsNaN(r.C) || math.IsInf(r.C, 0) || math.IsNaN(r.R) || math.IsInf(r.R, 0) {
			return math.Inf(1), vec{}
		}
		// Small operation-scale outward cushion. Exhaustive bound validation
		// below is still required; this is not a directed-rounding library.
		if !fixed(r) {
			r.R += 2e-14 * (1 + math.Abs(r.C) + r.R)
		}
		b.Values[i] = r
	}
	r := b.Values[p.G.Root]
	_, hi := b.span(r)
	return hi, r.W
}
func (p *problem) whole() region {
	r := make(region, len(p.Pools))
	for s, pool := range p.Pools {
		for k := range pool {
			r[s] = append(r[s], k)
		}
	}
	return r
}
func copyRegion(r region) region {
	v := make(region, len(r))
	for s := range r {
		v[s] = append([]int(nil), r[s]...)
	}
	return v
}
func size(r region) int {
	n := 1
	for _, a := range r {
		n *= len(a)
	}
	return n
}
func (p *problem) delta(a []int) vec {
	v := scale(affine{W: p.Ref}, -1).W
	for s, k := range a {
		for j := 0; j < p.D; j++ {
			v[j] += p.Pools[s][k].V[j]
		}
	}
	return v
}
func (p *problem) ids(a []int) []int64 {
	r := []int64{}
	for s, k := range a {
		r = append(r, p.Pools[s][k].ID)
	}
	return r
}
func ms(t time.Time) float64 { return float64(time.Since(t)) / float64(time.Millisecond) }

type oracleRow struct {
	Assignment []int
	Score      float64
}
type checkedBound struct {
	Domain region
	Upper  float64
}

func exercise(t *testing.T, name string, p *problem, expectedID int64) map[string]any {
	t.Helper()
	started := time.Now()
	oracle := []oracleRow{}
	oracleBest := math.Inf(-1)
	var oracleIDs []int64
	maxParity := 0.0
	a := make([]int, len(p.Pools))
	var enumerate func(int)
	enumerate = func(s int) {
		if s == len(a) {
			x := p.delta(a)
			v := p.Score(x)
			oracle = append(oracle, oracleRow{append([]int(nil), a...), v})
			if v > oracleBest {
				oracleBest = v
				oracleIDs = p.ids(a)
			}
			return
		}
		for k := range p.Pools[s] {
			a[s] = k
			enumerate(s + 1)
		}
	}
	enumerate(0)
	oracleMS := ms(started)
	started = time.Now()
	for _, row := range oracle {
		maxParity = math.Max(maxParity, math.Abs(row.Score-p.G.point(p.delta(row.Assignment))))
	}
	parityMS := ms(started)
	if maxParity > 1e-6 {
		t.Fatalf("%s reduced graph parity drift %g", name, maxParity)
	}
	started = time.Now()
	bounds := []checkedBound{}
	evaluated := map[string]float64{}
	best := math.Inf(-1)
	var bestA []int
	pruned := 0
	score := func(a []int) float64 {
		key := fmt.Sprint(a)
		v, ok := evaluated[key]
		if !ok {
			v = p.Score(p.delta(a))
			evaluated[key] = v
		}
		if v > best {
			best = v
			bestA = append([]int(nil), a...)
		}
		return v
	}
	bound := func(r region) (float64, vec) {
		u, w := p.upper(r, false)
		bounds = append(bounds, checkedBound{copyRegion(r), u})
		return u, w
	}
	full := p.whole()
	rootU, weights := bound(full)
	// This linear score proposes real candidates only; it never deletes items.
	for s, pool := range p.Pools {
		sort.SliceStable(full[s], func(i, j int) bool {
			x, y := pool[full[s][i]].V, pool[full[s][j]].V
			v := 0.0
			for d := 0; d < p.D; d++ {
				v += weights[d] * (x[d] - y[d])
			}
			return v > 0
		})
		a[s] = full[s][0]
	}
	score(a)
	for pass := 0; pass < 2; pass++ {
		for s, pool := range p.Pools {
			a = append([]int(nil), bestA...)
			for k := range pool {
				a[s] = k
				score(a)
			}
		}
	}
	heuristicBest := best
	var visit func(region, float64)
	visit = func(r region, u float64) {
		if u < best-1e-7 {
			pruned += size(r)
			return
		}
		if size(r) == 1 {
			a := make([]int, len(r))
			for s := range r {
				a[s] = r[s][0]
			}
			score(a)
			return
		}
		s := 0
		for j := range r {
			if len(r[j]) > len(r[s]) {
				s = j
			}
		}
		left, right := copyRegion(r), copyRegion(r)
		mid := len(r[s]) / 2
		left[s] = left[s][:mid]
		right[s] = right[s][mid:]
		lu, _ := bound(left)
		ru, _ := bound(right)
		if lu >= ru {
			visit(left, lu)
			visit(right, ru)
		} else {
			visit(right, ru)
			visit(left, lu)
		}
	}
	visit(full, rootU)
	searchMS := ms(started)
	started = time.Now()
	worstViolation := 0.0
	// Audit EVERY enclosure used in search against every oracle leaf inside it.
	// The oracle never feeds a score or ordering decision into the search.
	for _, b := range bounds {
		for _, row := range oracle {
			inside := true
			for s, k := range row.Assignment {
				found := false
				for _, j := range b.Domain[s] {
					found = found || j == k
				}
				inside = inside && found
			}
			if inside {
				worstViolation = math.Max(worstViolation, row.Score-b.Upper)
			}
		}
	}
	if worstViolation > 1e-7 || math.Abs(best-oracleBest) > 1e-7 {
		t.Fatalf("%s invalid upper/prune: violation=%g search=%g oracle=%g", name, worstViolation, best, oracleBest)
	}
	if expectedID != 0 && p.ids(bestA)[0] != expectedID {
		t.Fatalf("%s expected first-slot witness %d, got %v", name, expectedID, p.ids(bestA))
	}
	validationMS := ms(started)
	boxU, _ := p.upper(p.whole(), true)
	result := map[string]any{"name": name, "combinations": len(oracle), "exact_scored_unique": len(evaluated), "search_best": best, "oracle_best": oracleBest, "best_ids": p.ids(bestA), "oracle_ids": oracleIDs, "bound_evaluations": len(bounds), "covered_by_pruned_regions": pruned, "worst_upper_bound_violation": worstViolation, "reduced_point_max_error": maxParity, "oracle_ms": oracleMS, "search_ms": searchMS, "validation_ms": validationMS, "parity_check_ms": parityMS, "reduced_nodes": len(p.G.N)}
	result["heuristic_best_before_branching"] = heuristicBest
	if !math.IsInf(rootU, 0) {
		result["root_upper"] = rootU
		result["root_gap_percent"] = 100 * (rootU/oracleBest - 1)
	} else {
		result["root_upper"] = "unbounded"
	}
	if !math.IsInf(boxU, 0) {
		result["independent_box_root_upper"] = boxU
	} else {
		result["independent_box_root_upper"] = "unbounded"
	}
	t.Logf("%s: %d/%d exact, %d bounds; score %.6f; oracle %.2fms search %.2fms; upper violations %.3g", name, len(evaluated), len(oracle), len(bounds), best, oracleMS, searchMS, worstViolation)
	return result
}

func toy(t *testing.T) []map[string]any {
	rows := []map[string]any{}
	for _, cap := range []bool{false, true} {
		g := newGraph()
		cr := g.op("add", g.c(0.5), g.x(0))
		expected := int64(3)
		name := "balanced_10cr_22cd"
		if cap {
			cr = g.op("add", g.c(1), g.x(0))
			expected = 1
			name = "crit_cap_not_crit_mass"
		}
		g.Root = g.op("add", g.c(1), g.op("multiply", g.op("min", g.c(1), cr), g.op("add", g.c(1), g.x(1))))
		p := &problem{D: 2, G: g, Pools: [][]item{{{ID: 1, V: vec{0, .23}}, {ID: 2, V: vec{.117, 0}}, {ID: 3, V: vec{.10, .22}}}}}
		p.Score = g.point
		rows = append(rows, exercise(t, name, p, expected))
	}
	g := newGraph()
	g.Root = g.op("add", g.op("multiply", g.c(900), g.x(0)), g.x(1))
	p := &problem{D: 2, G: g, Pools: [][]item{{{ID: 1, V: vec{.10, 20}}, {ID: 2, V: vec{.12, 0}}}}}
	p.Score = g.point
	rows = append(rows, exercise(t, "flat_plus_percent_attack", p, 1))
	g = newGraph()
	g.Root = g.op("multiply", g.op("add", g.c(1), g.x(0)), g.op("add", g.c(1), g.x(1)))
	p = &problem{D: 2, G: g, Pools: [][]item{{}, {}}}
	p.Score = g.point
	for s := range p.Pools {
		for i := 0; i < 32; i++ {
			p.Pools[s] = append(p.Pools[s], item{ID: int64(s*100 + i + 1), V: vec{float64(i%4) / 100, float64(i%5) / 100}})
		}
	}
	p.Pools[0][31].V = vec{.9, .9}
	p.Pools[1][31].V = vec{.8, .8}
	rows = append(rows, exercise(t, "one_great_among_many_weak", p, 32))
	// Generic nonlinear saturation / branch / cross-input toy; no game constants.
	g = newGraph()
	x, y := g.x(0), g.x(1)
	fraction := g.op("multiply", x, g.op("power", g.op("add", g.c(2), x), g.c(-1)))
	branch := g.op("select_lt", x, y, g.op("multiply", g.c(2), y), g.op("add", x, y))
	g.Root = g.op("add", fraction, branch, g.op("max", x, y))
	p = &problem{D: 2, G: g, Pools: [][]item{{{ID: 1, V: vec{0, 1}}, {ID: 2, V: vec{2, 0}}, {ID: 3, V: vec{1, 2}}}, {{ID: 11, V: vec{1, 0}}, {ID: 12, V: vec{0, 2}}, {ID: 13, V: vec{2, 1}}}}}
	p.Score = g.point
	rows = append(rows, exercise(t, "saturation_branch_and_cross_input", p, 0))
	return rows
}

func capturedGraph(members []contracts.IRSeedMember, coordinates []string) (*graph, int) {
	g := newGraph()
	dims := map[string]int{}
	for j, key := range coordinates {
		dims[key] = j
	}
	roots := []int{}
	original := 0
	for _, m := range members {
		original += len(m.Nodes)
		mapped := make([]int, len(m.Nodes)+1)
		for _, n := range m.Nodes {
			r := node{Op: n.Operation}
			for _, i := range n.Inputs {
				r.In = append(r.In, mapped[i.NodeID])
			}
			switch n.Operation {
			case "constant", "opaque_frozen":
				r.Op = "constant"
				var err error
				r.Value, err = strconv.ParseFloat(n.Value, 64)
				if err != nil {
					panic(err)
				}
			case "artifact_stat":
				var ok bool
				r.Dim, ok = dims[n.Coordinate]
				if !ok {
					r = node{Op: "constant"}
				}
			}
			mapped[n.NodeID] = g.make(r)
		}
		channelRoots := []int{}
		for _, c := range m.Channels {
			channelRoots = append(channelRoots, mapped[c.RootNodeID])
		}
		roots = append(roots, g.op("multiply", g.op("add", channelRoots...), g.c(1000/float64(m.DurationMS)/float64(len(members)))))
	}
	g.Root = g.op("add", roots...)
	g.trim()
	return g, original
}

func TestInventoryBoundConcept(t *testing.T) {
	output := map[string]any{"synthetic": toy(t)}
	path := os.Getenv("GTT_BOUND_INPUT")
	if path == "" {
		t.Fatal("explicit managed input required")
	}
	var input struct {
		Engine  contracts.EngineBinding `json:"engine"`
		Catalog string                  `json:"catalog_sha256"`
		Seeds   []uint64                `json:"seeds"`
		Cases   []struct {
			Name, Config, Actor string
			Pools               [][]item
		}
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(data, &input); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 300*time.Second)
	defer cancel()
	rows := []map[string]any{}
	for _, c := range input.Cases {
		tick := time.Now()
		var refs []string
		for _, line := range strings.Split(c.Config, "\n") {
			if strings.Contains(line, " add stats ") {
				refs = append(refs, line)
			}
		}
		if len(refs) != 4 {
			t.Fatal("four reference rows required")
		}
		binding := setcontext.Binding{Engine: input.Engine, CatalogSHA256: input.Catalog, ReferenceStatsSHA256: contracts.TextSHA256(strings.Join(refs, "\n")), Seeds: input.Seeds}
		source, err := setcontext.New(binding, c.Config)
		if err != nil {
			t.Fatal(err)
		}
		root := filepath.Join(filepath.Dir(path), c.Name, "capture")
		if err = os.Mkdir(root, 0755); err != nil {
			t.Fatal(err)
		}
		provider, err := setcontext.NewEffectEngineProvider(binding, root)
		if err != nil {
			t.Fatal(err)
		}
		capture, err := provider.Capture(ctx, source)
		closeErr := provider.Close()
		if err != nil {
			t.Fatal(err)
		}
		if closeErr != nil {
			t.Fatal(closeErr)
		}
		captureMS := ms(tick)
		tick = time.Now()
		panel, err := evaluator.CompileMembers([]string{"columbina", "flins", "ineffa", "jahoda"}, input.Seeds, capture.Members)
		if err != nil {
			t.Fatal(err)
		}
		selected := []string{}
		positions := []int{}
		for j, key := range panel.Coordinates() {
			if strings.HasPrefix(key, c.Actor+".") {
				selected = append(selected, key)
				positions = append(positions, j)
			}
		}
		if len(selected) == 0 || len(selected) > maxDims {
			t.Fatal("unsupported coordinate count")
		}
		g, original := capturedGraph(capture.Members, selected)
		p := &problem{D: len(selected), G: g, Pools: c.Pools}
		for s := range p.Pools {
			for k := range p.Pools[s] {
				for j, key := range selected {
					p.Pools[s][k].V[j] = p.Pools[s][k].Stats[strings.TrimPrefix(key, c.Actor+".")]
				}
			}
			for j := range selected {
				p.Ref[j] += p.Pools[s][0].V[j]
			}
		}
		p.Score = func(x vec) float64 {
			dense := make([]float64, len(panel.Coordinates()))
			for j, pos := range positions {
				dense[pos] = x[j]
			}
			v, e := panel.EvaluateDPS(dense)
			if e != nil {
				t.Fatal(e)
			}
			return v
		}
		compileMS := ms(tick)
		row := exercise(t, c.Name, p, 0)
		row["capture_ms"] = captureMS
		row["compile_ms"] = compileMS
		row["source_ir_nodes"] = original
		row["coordinates"] = selected
		row["config_sha256"] = source.ConfigSHA256()
		row["capture_context_sha256"] = capture.ContextSHA256
		opaque := map[string]int{}
		topologies := []string{}
		for _, m := range capture.Members {
			topologies = append(topologies, m.TopologySHA256)
			for _, b := range m.OpaqueBoundaries {
				opaque[b.ReasonCode]++
			}
		}
		row["opaque_boundary_counts"] = opaque
		row["topology_sha256"] = topologies
		rows = append(rows, row)
	}
	output["real_cases"] = rows
	output["engine_capture_calls"] = len(input.Cases) * len(input.Seeds)
	output["ordinary_simulator_calls"] = 0
	output["proof_scope"] = "All evaluated/pruned bounds checked against exhaustive fixed-formula scores; no proof of schedule invariance or complete opaque ancestry, no full-account set scheduler or twenty-slot search."
	data, err = json.MarshalIndent(output, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(os.Getenv("GTT_BOUND_OUTPUT"), data, 0644); err != nil {
		t.Fatal(err)
	}
}

func TestInventoryBoundSyntheticSafety(t *testing.T) {
	toy(t)
	// A local stat slope and single-slot exchanges cannot escape this toy trap.
	// It demonstrates why those priorities must not become permanent deletions.
	g := newGraph()
	x, y := g.x(0), g.x(1)
	g.Root = g.op("add", g.c(1), g.op("multiply", g.c(-1), x),
		g.op("multiply", g.c(-1), y), g.op("multiply", g.c(3), x, y))
	p := &problem{D: 2, G: g, Pools: [][]item{{}, {}}}
	for s := range p.Pools {
		for k, v := range []float64{0, .1, .2, 1} {
			iv := vec{}
			iv[s] = v
			p.Pools[s] = append(p.Pools[s], item{ID: int64(10*s + k + 1), V: iv})
		}
	}
	p.Score = g.point
	row := exercise(t, "greedy_trap_joint_upgrade", p, 4)
	if row["heuristic_best_before_branching"].(float64) >= row["search_best"].(float64) {
		t.Fatal("fixture no longer demonstrates escape from the local optimum")
	}
	// A singular relaxed interval is deliberately unprunable even though its
	// two real endpoints are valid. Never replace an unknown bound with zero.
	g = newGraph()
	g.Root = g.op("power", g.x(0), g.c(-1))
	p = &problem{D: 1, G: g, Pools: [][]item{{{ID: 1, V: vec{-1}}, {ID: 2, V: vec{1}}}}}
	p.Score = g.point
	u, _ := p.upper(p.whole(), false)
	if !math.IsInf(u, 1) {
		t.Fatal("singular interval must stay unprunable")
	}
	exercise(t, "singular_relaxation_is_not_pruned", p, 2)
}
