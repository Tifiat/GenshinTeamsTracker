package formula

import (
	"math"
	"math/rand"
	"testing"
)

func testProgram(d int) (*ArtifactProgram, func(uint8, float64, int, ...uint32) uint32) {
	p := &ArtifactProgram{coordinates: make([]string, d)}
	add := func(op uint8, v float64, dim int, in ...uint32) uint32 {
		i := uint32(len(p.nodes))
		p.nodes = append(p.nodes, compiledNode{op: op, value: v, coordinate: dim, inputs: in})
		p.values = append(p.values, 0)
		p.root = i
		return i
	}
	return p, add
}

func TestApproximateModelHasPriorityButNoHardUpper(t *testing.T) {
	p, n := testProgram(1)
	a := n(opArtifactStat, 0, 0)
	b := n(opConstant, 100, -1)
	n(opAdd, 0, -1, a, b)
	p.unresolved = true
	items := [][][]float64{{{1}, {10}}}
	u, _ := p.Upper(items, []float64{0})
	potential := p.Potential(items, []float64{0})
	if !math.IsInf(u, 1) || potential < 110 || potential > 110.001 {
		t.Fatal(u, potential)
	}
}

func checkRegion(t *testing.T, p *ArtifactProgram, pools [][][]float64, ref []float64) float64 {
	t.Helper()
	u, _ := p.Upper(pools, ref)
	best := math.Inf(-1)
	var walk func(int, []float64)
	walk = func(slot int, sum []float64) {
		if slot == len(pools) {
			x := append([]float64(nil), sum...)
			for j := range x {
				x[j] -= ref[j]
			}
			v, e := p.Evaluate(x)
			if e != nil {
				t.Fatal(e)
			}
			if v > u+1e-9 {
				t.Fatalf("unsafe bound: point=%g upper=%g", v, u)
			}
			best = math.Max(best, v)
			return
		}
		for _, item := range pools[slot] {
			next := append([]float64(nil), sum...)
			for j, v := range item {
				next[j] += v
			}
			walk(slot+1, next)
		}
	}
	walk(0, make([]float64, len(ref)))
	return best
}

func TestRealJointCritVectorsAndCap(t *testing.T) {
	for _, base := range []float64{.5, 1} {
		p, n := testProgram(2)
		cr := n(opArtifactStat, 0, 0)
		cd := n(opArtifactStat, 0, 1)
		one := n(opConstant, 1, -1)
		c := n(opConstant, base, -1)
		r := n(opAdd, 0, -1, c, cr)
		r = n(opMin, 0, -1, one, r)
		d := n(opAdd, 0, -1, one, cd)
		r = n(opMultiply, 0, -1, r, d)
		n(opAdd, 0, -1, one, r)
		items := [][]float64{{0, .23}, {.117, 0}, {.10, .22}}
		best := checkRegion(t, p, [][][]float64{items}, []float64{0, 0})
		want := 2
		if base == 1 {
			want = 0
		}
		v, _ := p.Evaluate(items[want])
		if math.Abs(best-v) > 1e-12 {
			t.Fatalf("balanced/capped witness lost %g %g", best, v)
		}
		u, _ := p.Upper([][][]float64{items}, []float64{0, 0})
		fake, _ := p.Evaluate([]float64{.117, .23})
		if base == 1 && u > fake+1e-7 {
			t.Fatal("constant crit cap should not invent a larger item")
		}
	}
}
func TestBoundFlatPercentOutlierBranchesAndSaturation(t *testing.T) {
	p, n := testProgram(2)
	pct := n(opArtifactStat, 0, 0)
	flat := n(opArtifactStat, 0, 1)
	base := n(opConstant, 900, -1)
	a := n(opMultiply, 0, -1, base, pct)
	n(opAdd, 0, -1, a, flat)
	if best := checkRegion(t, p, [][][]float64{{{.10, 20}, {.12, 0}}}, []float64{0, 0}); math.Abs(best-110) > 1e-9 {
		t.Fatal(best)
	}
	random := rand.New(rand.NewSource(731))
	for trial := 0; trial < 100; trial++ {
		p, n = testProgram(2)
		x := n(opArtifactStat, 0, 0)
		y := n(opArtifactStat, 0, 1)
		two := n(opConstant, 2, -1)
		neg := n(opConstant, -1, -1)
		den := n(opAdd, 0, -1, two, x)
		recip := n(opPower, 0, -1, den, neg)
		fraction := n(opMultiply, 0, -1, x, recip)
		x2 := n(opMultiply, 0, -1, x, x)
		branch := n(opSelectLT, 0, -1, x, y, x2, y)
		cap := n(opMax, 0, -1, x, y)
		n(opAdd, 0, -1, fraction, branch, cap)
		pools := make([][][]float64, 3)
		for s := range pools {
			for k := 0; k < 4; k++ {
				pools[s] = append(pools[s], []float64{random.Float64() * 4, random.Float64() * 4})
			}
		}
		pools[0][3] = []float64{20, 20}
		checkRegion(t, p, pools, []float64{0, 0})
	}
}
func TestUnknownPowerIsUnprunable(t *testing.T) {
	p, n := testProgram(1)
	x := n(opArtifactStat, 0, 0)
	power := n(opConstant, -1, -1)
	n(opPower, 0, -1, x, power)
	u, _ := p.Upper([][][]float64{{{-1}, {1}}}, []float64{0})
	if !math.IsInf(u, 1) {
		t.Fatal("singularity was prunable", u)
	}
}

func TestHybridEnclosureKeepsClampDomainAndLongProductRange(t *testing.T) {
	// A clamp proves nonnegativity even though a guarded affine support can
	// slightly cross zero. sqrt(max(0,x)) is bounded at zero; its derivative is
	// not. This must not assign infinite priority to an otherwise weak region.
	p, n := testProgram(1)
	x := n(opArtifactStat, 0, 0)
	zero := n(opConstant, 0, -1)
	half := n(opConstant, .5, -1)
	y := n(opMax, 0, -1, zero, x)
	n(opPower, 0, -1, y, half)
	items := [][][]float64{{{-1}, {0}, {.25}, {1}, {4}}}
	checkRegion(t, p, items, []float64{0})
	u, _ := p.Upper(items, []float64{0})
	if u < 2 || u > 2.000001 {
		t.Fatal("clamped root lost its finite enclosure", u)
	}
	// Independent interval products control nonlinear affine remainder growth.
	p, n = testProgram(1)
	x = n(opArtifactStat, 0, 0)
	y = x
	for i := 0; i < 7; i++ {
		y = n(opMultiply, 0, -1, y, x)
	}
	items = [][][]float64{{{1}, {1.2}, {1.7}, {2}}}
	checkRegion(t, p, items, []float64{0})
	u, _ = p.Upper(items, []float64{0})
	if u < 256 || u > 256.000001 {
		t.Fatal("nonlinear remainder escaped the natural interval", u)
	}
}

func TestHybridEnclosureMixedSignsAndFractionalBranches(t *testing.T) {
	random := rand.New(rand.NewSource(72951))
	for trial := 0; trial < 100; trial++ {
		p, n := testProgram(2)
		x := n(opArtifactStat, 0, 0)
		y := n(opArtifactStat, 0, 1)
		zero := n(opConstant, 0, -1)
		half := n(opConstant, .5, -1)
		one := n(opConstant, 1, -1)
		neg := n(opConstant, -1, -1)
		clamp := n(opMax, 0, -1, zero, x)
		sqrt := n(opPower, 0, -1, clamp, half)
		product := n(opMultiply, 0, -1, x, y)
		den := n(opAdd, 0, -1, one, clamp)
		recip := n(opPower, 0, -1, den, neg)
		branch := n(opSelectLT, 0, -1, x, y, sqrt, product)
		n(opAdd, 0, -1, branch, recip)
		pools := make([][][]float64, 3)
		for s := range pools {
			for k := 0; k < 4; k++ {
				pools[s] = append(pools[s], []float64{random.Float64()*4 - 2, random.Float64()*4 - 2})
			}
		}
		checkRegion(t, p, pools, []float64{0, 0})
	}
}

func TestUnionPotentialRetainsWholePatternAndJointItems(t *testing.T) {
	p, n := testProgram(1)
	n(opArtifactStat, 0, 0)
	groups := [][][]float64{{{50}}, {{1}}, {{2}}, {{60}}}
	patterns := [][]int{{0, 2}, {1, 3}}
	u := p.PotentialUnion(groups, patterns, []float64{0})
	if u < 61 || u > 61.000001 {
		t.Fatal("illegal cross-pattern maxima", u)
	}
	// Shared-pool union bounds enclose every legal nonlinear combination, even
	// with a branch/cap. Centering is only an affine numerical device: neither
	// average nor independently maximized fictitious items are ranked as builds.
	p, n = testProgram(2)
	x := n(opArtifactStat, 0, 0)
	y := n(opArtifactStat, 0, 1)
	one := n(opConstant, 1, -1)
	half := n(opConstant, .5, -1)
	cr := n(opMin, 0, -1, one, n(opAdd, 0, -1, half, x))
	cd := n(opAdd, 0, -1, one, y)
	n(opMultiply, 0, -1, cr, cd)
	groups = [][][]float64{{{0, .23}, {.10, .22}}, {{.117, 0}}, {{.2, .1}, {.1, 1.0}}, {{.05, .6}}}
	patterns = [][]int{{0, 2}, {1, 3}, {0, 3}}
	ref := []float64{.04, .1}
	u = p.PotentialUnion(groups, patterns, ref)
	for _, pattern := range patterns {
		for _, a := range groups[pattern[0]] {
			for _, b := range groups[pattern[1]] {
				value, err := p.Evaluate([]float64{a[0] + b[0] - ref[0], a[1] + b[1] - ref[1]})
				if err != nil || value > u+1e-10 {
					t.Fatal("unsafe union potential", value, u, err)
				}
			}
		}
	}
	p.unresolved = true
	if unknown := p.PotentialUnion(groups, patterns, ref); unknown != u {
		t.Fatal("model potential changed with proof status", unknown, u)
	}
	for _, bad := range [][][]int{nil, {{-1}}, {{4}}, {nil}} {
		if !math.IsInf(p.PotentialUnion(groups, bad, ref), 1) {
			t.Fatal("invalid union acquired finite bound", bad)
		}
	}
}
