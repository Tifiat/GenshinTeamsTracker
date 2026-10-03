package formula

// Synthetic arithmetic/ownership cases, not gameplay recipes. Real active-engine
// changed-input evidence is a separate gate; these tests prove the compiler
// preserves the supplied model, not that all set mechanics have been supplied.
import (
	"math"
	"math/rand"
	"reflect"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func parametricMember(t *testing.T, duration int64) (contracts.IRSeedMember, *CompiledMember) {
	t.Helper()
	in := func(ids ...uint32) []contracts.IRInput {
		out := []contracts.IRInput{}
		for _, id := range ids {
			out = append(out, contracts.IRInput{NodeID: id, Relation: "operand"})
		}
		return out
	}
	m := contracts.IRSeedMember{Seed: 1, DurationMS: duration, TopologySHA256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", Nodes: []contracts.IRNode{
		{NodeID: 1, Operation: "constant", Value: "20", Inputs: in()},
		{NodeID: 2, Operation: "artifact_stat", Coordinate: "provider.em", Inputs: in()},
		{NodeID: 3, Operation: "add", Inputs: in(1, 2)},
		{NodeID: 4, Operation: "constant", Value: "20", Inputs: in()},
		{NodeID: 5, Operation: "artifact_stat", Coordinate: "recipient.atk", Inputs: in()},
		{NodeID: 6, Operation: "add", Inputs: in(4, 5)},
		{NodeID: 7, Operation: "multiply", Inputs: in(3, 6)},
		// This disconnected subtree must not survive preparation.
		{NodeID: 8, Operation: "multiply", Inputs: in(2, 5)},
	}, Channels: []contracts.IRChannel{{ChannelID: "hit/000001", Kind: "direct", ActorKey: "recipient", AttackTag: "tag/1", DamageType: "physical", RootNodeID: 7, HitCount: 1, BaselineDamage: "400", ResponseCoordinates: []string{"provider.em", "recipient.atk"}}}, OpaqueBoundaries: []contracts.IROpaqueBoundary{}}
	c, err := CompileSeedMember(m, []string{"provider", "recipient"}, []string{"provider.em", "recipient.atk"})
	if err != nil {
		t.Fatal(err)
	}
	return m, c
}

func TestParametricDistinctEqualPortsSurviveReduction(t *testing.T) {
	m, c := parametricMember(t, 1000)
	p, err := PrepareParametric([]*CompiledMember{c}, []EffectPort{{0, 1, "window_a", 20}, {0, 4, "window_b", 20}})
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(p.EffectKeys(), []string{"window_a", "window_b"}) {
		t.Fatal(p.EffectKeys())
	}
	oracle, err := CompileInterventions(m, c.actorKeys, c.coordinates, []uint32{1, 4})
	if err != nil {
		t.Fatal(err)
	}
	rng := rand.New(rand.NewSource(19))
	for trial := 0; trial < 100; trial++ {
		x := []float64{rng.Float64()*20 - 10, rng.Float64()*20 - 10}
		e := []float64{rng.Float64()*10 - 5, rng.Float64()*10 - 5}
		got, err := p.Evaluate(x, e)
		want, otherErr := oracle.Evaluate(x, map[uint32]float64{1: e[0], 4: e[1]})
		if err != nil || otherErr != nil || math.Abs(got-want.Damage) > 1e-10 {
			t.Fatal(got, want, err, otherErr)
		}
	}
	// Changing one equal-valued source must not modify the other source.
	got, _ := p.Evaluate([]float64{1, 5}, []float64{2, 0})
	if got != 23*25 {
		t.Fatal(got)
	}
	got, _ = p.Evaluate([]float64{1, 5}, []float64{0, 2})
	if got != 21*27 {
		t.Fatal(got)
	}
	got, _ = p.Evaluate([]float64{0, 0}, []float64{0, 0})
	if got != 400 {
		t.Fatal("stale parametric scratch", got)
	}
}

func TestParametricSharedGraphKeepsPrivateScratchAndProofStatus(t *testing.T) {
	_, c := parametricMember(t, 1000)
	p, err := PrepareParametric([]*CompiledMember{c}, nil)
	if err != nil {
		t.Fatal(err)
	}
	a, b := p.WithOwnScratch(), p.WithoutPruning()
	if &a.program.values[0] == &p.program.values[0] || &a.program.values[0] == &b.program.values[0] || &a.input[0] == &p.input[0] {
		t.Fatal("evaluation scratch shared")
	}
	if !b.program.unresolved || a.program.unresolved || p.program.unresolved {
		t.Fatal("proof status leaked")
	}
	if _, err = a.Evaluate([]float64{7, 9}, nil); err != nil {
		t.Fatal(err)
	}
	if p.input[0] != 0 || b.input[0] != 0 {
		t.Fatal("one candidate changed another")
	}
}

func TestParametricDurationAndRepeatedMultiActorSpecialization(t *testing.T) {
	_, a := parametricMember(t, 1000)
	_, b := parametricMember(t, 2000)
	p, err := PrepareParametric([]*CompiledMember{a, b}, nil)
	if err != nil {
		t.Fatal(err)
	}
	before := p.NodeCount()
	for _, anchor := range [][]float64{{0, 0}, {3, 7}, {-5, 2}} {
		got, err := p.Evaluate(anchor, nil)
		want := (20 + anchor[0]) * (20 + anchor[1]) * .75
		if err != nil || got != want {
			t.Fatal(got, want, err)
		}
		for _, actors := range [][]int{{0}, {1}, {0, 1}, {}} {
			q, err := p.Specialize(anchor, nil, actors...)
			if err != nil {
				t.Fatal(err)
			}
			x := []float64{}
			for _, key := range q.Coordinates() {
				if key == "provider.em" {
					x = append(x, anchor[0])
				} else {
					x = append(x, anchor[1])
				}
			}
			v, err := q.Evaluate(x)
			if err != nil || v != want {
				t.Fatal(v, want, err)
			}
		}
	}
	if p.NodeCount() != before {
		t.Fatal("specialization mutated source")
	}
	if _, err = p.Specialize([]float64{0, 0}, nil, 0, 0); err == nil {
		t.Fatal("duplicate actor accepted")
	}
}

func TestParametricPortControlsBranchAfterReduction(t *testing.T) {
	_, c := parametricMember(t, 1000)
	// Reuse the validated scalar nodes with a pure conditional numeric root.
	c.nodes = append(c.nodes, compiledNode{op: opConstant, value: 21, coordinate: -1})
	c.nodes = append(c.nodes, compiledNode{op: opSelectLT, coordinate: -1, inputs: []uint32{1, 9, 3, 6}})
	c.channels[0].root = 10
	if err := c.buildEvaluationPlan(); err != nil {
		t.Fatal(err)
	}
	p, err := PrepareParametric([]*CompiledMember{c}, []EffectPort{{0, 1, "condition", 20}})
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct{ offset, want float64 }{{0, 23}, {2, 27}, {0, 23}} {
		got, err := p.Evaluate([]float64{3, 7}, []float64{test.offset})
		if err != nil || got != test.want {
			t.Fatal(got, test.want, err)
		}
	}
}

func TestParametricRejectsMismatchedPortsAndNonfiniteInput(t *testing.T) {
	_, c := parametricMember(t, 1000)
	for _, ports := range [][]EffectPort{
		{{0, 1, "a", 21}}, {{0, 1, "a", 20}, {0, 1, "b", 20}}, {{1, 1, "a", 20}}, {{0, 99, "a", 20}}, {{0, 1, "", 20}}, {{0, 1, "a", math.NaN()}},
	} {
		if _, err := PrepareParametric([]*CompiledMember{c}, ports); err == nil {
			t.Fatal("invalid port accepted", ports)
		}
	}
	p, err := PrepareParametric([]*CompiledMember{c}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = p.Evaluate([]float64{math.NaN(), 0}, nil); err == nil {
		t.Fatal("nonfinite input accepted")
	}
	if _, err = p.Evaluate([]float64{0, 0}, []float64{1}); err == nil {
		t.Fatal("wrong input layout accepted")
	}
}

func TestUnknownDependenciesPreventFinitePruningBound(t *testing.T) {
	_, c := parametricMember(t, 1000)
	c.hasOpaque = true
	p, err := PrepareParametric([]*CompiledMember{c}, nil)
	if err != nil {
		t.Fatal(err)
	}
	q, err := p.Specialize([]float64{0, 0}, nil, 0)
	if err != nil {
		t.Fatal(err)
	}
	u, _ := q.Upper([][][]float64{{{0}, {10}}}, []float64{0})
	if !math.IsInf(u, 1) || !q.HasUnresolvedDependencies() {
		t.Fatal("unknown model certified dominance", u)
	}
	if v, err := q.Evaluate([]float64{10}); err != nil || v != 600 {
		t.Fatal("unknown disabled known arithmetic", v, err)
	}
}

func TestPreparedGradientMatchesJointResponse(t *testing.T) {
	_, c := parametricMember(t, 1000)
	p, err := PrepareParametric([]*CompiledMember{c}, nil)
	if err != nil {
		t.Fatal(err)
	}
	q, err := p.Specialize([]float64{0, 0}, nil, 0, 1)
	if err != nil {
		t.Fatal(err)
	}
	for _, x := range [][]float64{{3, 7}, {-20, 7}, {-20, -20}} {
		v, g, smooth, err := q.ValueGradient(x)
		if err != nil || !smooth || v != (20+x[0])*(20+x[1]) || g[0] != 20+x[1] || g[1] != 20+x[0] {
			t.Fatal(v, g, smooth, err)
		}
	}
	q, n := testProgram(2)
	x := n(opArtifactStat, 0, 0)
	y := n(opArtifactStat, 0, 1)
	cap := n(opConstant, 1, -1)
	r := n(opMin, 0, -1, x, cap)
	n(opMultiply, 0, -1, r, y)
	_, g, smooth, err := q.ValueGradient([]float64{1.2, 2})
	if err != nil || !smooth || g[0] != 0 || g[1] != 1 {
		t.Fatal(g, smooth, err)
	}
	_, _, smooth, err = q.ValueGradient([]float64{1, 2})
	if err != nil || smooth {
		t.Fatal("cap boundary claimed smooth", err)
	}
}
