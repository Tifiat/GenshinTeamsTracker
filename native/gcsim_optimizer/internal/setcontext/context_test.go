package setcontext

import (
	"context"
	"errors"
	"math"
	"reflect"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

// Deliberately synthetic set names/amounts: this proves routing and accounting,
// not a production certificate for any GCSIM set. Real captures are replayed
// separately by the bounded All Sets pilot with no broad reuse proofs.
func fixtureContext(t *testing.T) *Context {
	t.Helper()
	h := strings.Repeat("a", 64)
	binding := Binding{Engine: contracts.EngineBinding{ArtifactSHA256: h, BindingSHA256: h, SourceManifestSHA256: h, PatchManifestSHA256: h}, CatalogSHA256: h, ReferenceStatsSHA256: h, Seeds: []uint64{1, 2}}
	text := ""
	for _, actor := range []string{"actor_a", "actor_b", "actor_c", "actor_d"} {
		text += actor + " char lvl=90/90;\n" + actor + " add set=\"old\" count=2;\n" + actor + " add stats em=100;\n\n"
	}
	text += "options ignore_burst_energy=true;\ntarget lvl=100;\nactor_a skill;\n"
	c, err := New(binding, text)
	if err != nil {
		t.Fatal(err)
	}
	return c
}

func replaced(t *testing.T, c *Context, sets []Set) *Context {
	t.Helper()
	next, err := c.Replace(map[string][]Set{"actor_a": sets})
	if err != nil {
		t.Fatal(err)
	}
	return next
}

func TestContextReplacementPreservesFrameAndRestores(t *testing.T) {
	base := fixtureContext(t)
	next := replaced(t, base, []Set{{UID: "new", Count: 2}, {UID: "another", Count: 3}})
	if next.key == base.key || next.frameKey != base.frameKey || !reflect.DeepEqual(next.actors, base.actors) {
		t.Fatal("context identity/frame/order lost")
	}
	if strings.Contains(next.text, "actor_a add set=\"old\"") || strings.Count(next.text, "actor_a add stats em=100;") != 1 {
		t.Fatal("ghost effect or modified artifact row")
	}
	if got := replaced(t, next, base.Sets("actor_a")); got.text != base.text || got.key != base.key {
		t.Fatal("restore mismatch")
	}
	crlf, err := New(base.binding, strings.ReplaceAll(base.text, "\n", "\r\n"))
	if err != nil {
		t.Fatal(err)
	}
	if got := replaced(t, replaced(t, crlf, next.Sets("actor_a")), base.Sets("actor_a")); got.text != crlf.text {
		t.Fatal("CRLF restoration changed unrelated bytes")
	}
	copySets := next.Sets("actor_a")
	copySets[0].UID = "mutated"
	copySeeds := next.Seeds()
	copySeeds[0] = 90
	if next.Sets("actor_a")[0].UID != "new" || next.Seeds()[0] != 1 {
		t.Fatal("mutable context leaked")
	}
}

func TestContextIdentityCoversAllInputs(t *testing.T) {
	base := fixtureContext(t)
	cases := map[string]func(*Binding, *string){
		"binary":     func(b *Binding, _ *string) { b.Engine.ArtifactSHA256 = strings.Repeat("b", 64) },
		"source":     func(b *Binding, _ *string) { b.Engine.SourceManifestSHA256 = strings.Repeat("b", 64) },
		"patch":      func(b *Binding, _ *string) { b.Engine.PatchManifestSHA256 = strings.Repeat("b", 64) },
		"catalog":    func(b *Binding, _ *string) { b.CatalogSHA256 = strings.Repeat("b", 64) },
		"reference":  func(b *Binding, _ *string) { b.ReferenceStatsSHA256 = strings.Repeat("b", 64) },
		"seed_order": func(b *Binding, _ *string) { b.Seeds = []uint64{2, 1} },
		"energy":     func(_ *Binding, s *string) { *s = strings.ReplaceAll(*s, "energy=true", "energy=false") },
		"rotation":   func(_ *Binding, s *string) { *s = strings.ReplaceAll(*s, "actor_a skill;", "actor_a burst;") },
		"raw_stats":  func(_ *Binding, s *string) { *s = strings.ReplaceAll(*s, "em=100", "em=101") },
		"target":     func(_ *Binding, s *string) { *s = strings.ReplaceAll(*s, "target lvl=100", "target lvl=101") },
		"initialization": func(_ *Binding, s *string) {
			*s = strings.ReplaceAll(*s, "actor_a", "temporary")
			*s = strings.ReplaceAll(*s, "actor_b", "actor_a")
			*s = strings.ReplaceAll(*s, "temporary", "actor_b")
		},
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			b, text := base.binding, base.text
			mutate(&b, &text)
			changed, err := New(b, text)
			if err != nil {
				t.Fatal(err)
			}
			if changed.key == base.key || Decide(base, changed, "", nil, nil).Reason != "non_set_context_changed" {
				t.Fatal("unsafe identity reuse")
			}
		})
	}
	param := replaced(t, base, []Set{{UID: "old", Count: 2, Parameters: " +params=[pilot=1]"}})
	if param.key == base.key || Decide(base, param, "", nil, nil).Route != FreshCapture {
		t.Fatal("opaque parameters ignored")
	}
}

func TestContextRejectsAmbiguousPreparedRows(t *testing.T) {
	base := fixtureContext(t)
	for _, bad := range []string{
		strings.Replace(base.text, "actor_a add set=\"old\" count=2;", "actor_a add set=\"old\" count=2; actor_a skill;", 1),
		strings.Replace(base.text, "actor_a add stats em=100;", "actor_a add stats em=100;\nactor_a add set=\"other\" count=2;", 1),
		strings.Replace(base.text, "actor_a add stats em=100;", "actor_a add set=\"old\" count=2;", 1),
		strings.Replace(base.text, "actor_a char lvl=90/90;", "", 1),
	} {
		if _, err := New(base.binding, bad); err == nil {
			t.Fatal("ambiguous layout accepted")
		}
	}
	for _, sets := range [][]Set{nil, {{UID: "old", Count: 4}, {UID: "new", Count: 2}}, {{UID: "new", Count: 2, Parameters: "; actor_a skill;"}}, {{UID: "new", Count: 0}}} {
		if _, err := base.Replace(map[string][]Set{"actor_a": sets}); err == nil {
			t.Fatal("invalid replacement accepted")
		}
	}
	if _, err := base.Replace(map[string][]Set{"unknown": {{UID: "new", Count: 2}}}); err == nil {
		t.Fatal("unknown owner accepted")
	}
}

func syntheticCapture(c *Context, amount string) Capture {
	members := make([]contracts.IRSeedMember, 0, len(c.binding.Seeds))
	for _, seed := range c.binding.Seeds {
		members = append(members, contracts.IRSeedMember{Seed: seed, DurationMS: 1000, TopologySHA256: strings.Repeat("c", 64),
			Nodes: []contracts.IRNode{
				{NodeID: 1, Operation: "constant", Value: amount, Inputs: []contracts.IRInput{}},
				{NodeID: 2, Operation: "artifact_stat", Coordinate: "actor_a.em", Inputs: []contracts.IRInput{}},
				{NodeID: 3, Operation: "add", Inputs: []contracts.IRInput{{NodeID: 1, Relation: "base"}, {NodeID: 2, Relation: "delta"}}},
			}, Channels: []contracts.IRChannel{{ChannelID: "damage", Kind: "direct", ActorKey: "actor_b", AttackTag: "skill", DamageType: "synthetic", RootNodeID: 3, HitCount: 1, BaselineDamage: amount, ResponseCoordinates: []string{"actor_a.em"}}}, OpaqueBoundaries: []contracts.IROpaqueBoundary{},
		})
	}
	return Capture{ContextSHA256: c.key, ConfigSHA256: c.configSHA, EngineBindingSHA256: c.binding.Engine.BindingSHA256, Members: members}
}

func syntheticProof(base, target *Context, graph string) *StaticProof {
	return &StaticProof{FromContextSHA256: base.key, ToContextSHA256: target.key, GraphSHA256: graph, EvidenceSHA256: strings.Repeat("d", 64),
		LifecycleComplete: true, ReadBindingsComplete: true, ModifierInteractionsComplete: true, SchedulePreserved: true,
		Before: []Effect{{SetUID: "old", Wearer: "actor_a", Tier: 2, Scope: "owner", SourceSHA256: strings.Repeat("e", 64), ModifierKeys: []string{"old_key"}, StaticStats: map[string]float64{"actor_a.em": 80}}},
		After:  []Effect{{SetUID: "new", Wearer: "actor_a", Tier: 2, Scope: "owner", SourceSHA256: strings.Repeat("f", 64), ModifierKeys: []string{"new_key"}, StaticStats: map[string]float64{"actor_a.em": 30}}},
		Bounds: map[string]Interval{"actor_a.em": {-100, 100}},
	}
}

func TestProofRejectsPartialCoverageAndBadIdentity(t *testing.T) {
	base := fixtureContext(t)
	target := replaced(t, base, []Set{{UID: "new", Count: 2}})
	graph := strings.Repeat("b", 64)
	cases := map[string]func(*StaticProof){
		"old_context":           func(p *StaticProof) { p.FromContextSHA256 = target.key },
		"graph":                 func(p *StaticProof) { p.GraphSHA256 = "wrong" },
		"lifecycle":             func(p *StaticProof) { p.LifecycleComplete = false },
		"stat_reads":            func(p *StaticProof) { p.ReadBindingsComplete = false },
		"modifier_interactions": func(p *StaticProof) { p.ModifierInteractionsComplete = false },
		"schedule":              func(p *StaticProof) { p.SchedulePreserved = false },
		"missing_old":           func(p *StaticProof) { p.Before = nil },
		"condition":             func(p *StaticProof) { p.After[0].ConditionDependencies = []string{"reaction"} },
		"target_scope":          func(p *StaticProof) { p.After[0].Scope = "target" },
		"new_output":            func(p *StaticProof) { p.After[0].Scope = "new_output" },
		"unknown_scope":         func(p *StaticProof) { p.After[0].Scope = "unknown" },
		"wrong_owner": func(p *StaticProof) {
			p.After[0].StaticStats = map[string]float64{"actor_b.em": 30}
		},
		"modifier_collision": func(p *StaticProof) { p.After[0].ModifierKeys = []string{"same", "same"} },
		"missing_bounds":     func(p *StaticProof) { p.Bounds = nil },
		"nan":                func(p *StaticProof) { p.After[0].StaticStats["actor_a.em"] = math.NaN() },
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			p := syntheticProof(base, target, graph)
			mutate(p)
			if d := Decide(base, target, graph, []string{"actor_a.em"}, p); d.Route != FreshCapture {
				t.Fatalf("unsafe proof accepted: %+v", d)
			}
		})
	}
	four := replaced(t, base, []Set{{UID: "old", Count: 4}})
	p := syntheticProof(four, target, graph)
	if d := Decide(four, target, graph, []string{"actor_a.em"}, p); d.Route != FreshCapture {
		t.Fatal("removed 4p effect omitted")
	}
}

func TestSessionReuseBiasRestorationAndBudget(t *testing.T) {
	base := fixtureContext(t)
	target := replaced(t, base, []Set{{UID: "new", Count: 2}})
	calls := 0
	s, _ := NewSession(func(_ context.Context, c *Context) (Capture, error) { calls++; return syntheticCapture(c, "180"), nil }, 2)
	h, err := s.Resolve(context.Background(), base, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	p := syntheticProof(base, target, h.GraphSHA256())
	next, err := s.Resolve(context.Background(), target, h, p)
	if err != nil {
		t.Fatal(err)
	}
	if next.Route() != StaticReplacement || calls != 1 || s.attempted != 2 {
		t.Fatal("replacement spent capture budget")
	}
	raw := map[string]float64{"actor_a.em": 5}
	for i := 0; i < 2; i++ {
		score, err := next.EvaluateDPS(raw)
		if err != nil || score != 135 || raw["actor_a.em"] != 5 {
			t.Fatalf("bias double counted or raw mutated: %v, %v", score, err)
		}
	}
	if _, err := next.EvaluateDPS(map[string]float64{"actor_a.em": 101}); err == nil {
		t.Fatal("proof escaped bounds")
	}
	restored, err := s.Resolve(context.Background(), base, next, nil)
	if err != nil {
		t.Fatal(err)
	}
	if score, _ := restored.EvaluateDPS(raw); score != 185 || calls != 1 {
		t.Fatal("restoration retained new bonus")
	}
	third := replaced(t, base, []Set{{UID: "third", Count: 2}})
	if _, err := s.Resolve(context.Background(), third, next, p); err == nil || calls != 1 {
		t.Fatal("bad proof/budget caused hidden capture")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := s.Resolve(ctx, base, nil, nil); !errors.Is(err, context.Canceled) {
		t.Fatal("cancel ignored on cache hit")
	}
}

func TestSessionValidatesCapturedPanelAndChargesFailures(t *testing.T) {
	base := fixtureContext(t)
	for name, mutate := range map[string]func(*Capture){
		"context":  func(c *Capture) { c.ContextSHA256 = strings.Repeat("b", 64) },
		"config":   func(c *Capture) { c.ConfigSHA256 = strings.Repeat("b", 64) },
		"engine":   func(c *Capture) { c.EngineBindingSHA256 = strings.Repeat("b", 64) },
		"seed":     func(c *Capture) { c.Members[0].Seed = 20 },
		"panel":    func(c *Capture) { c.Members = c.Members[:1] },
		"baseline": func(c *Capture) { c.Members[0].Channels[0].BaselineDamage = "90" },
	} {
		t.Run(name, func(t *testing.T) {
			calls := 0
			s, _ := NewSession(func(_ context.Context, c *Context) (Capture, error) {
				calls++
				v := syntheticCapture(c, "100")
				mutate(&v)
				return v, nil
			}, 2)
			if _, err := s.Resolve(context.Background(), base, nil, nil); err == nil {
				t.Fatal("bad capture accepted")
			}
			if _, err := s.Resolve(context.Background(), base, nil, nil); err == nil || calls != 1 || s.attempted != 2 {
				t.Fatal("failed capture silently retried")
			}
		})
	}
}

func TestContextPanelKeepsPerSeedDurationAndPointBounds(t *testing.T) {
	base := fixtureContext(t)
	s, _ := NewSession(func(_ context.Context, c *Context) (Capture, error) {
		v := syntheticCapture(c, "180")
		v.Members[1].DurationMS = 2000
		return v, nil
	}, 2)
	h, err := s.Resolve(context.Background(), base, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	if dps, err := h.EvaluateDPS(nil); err != nil || dps != 135 {
		t.Fatalf("per-member DPS expectation changed: %v %v", dps, err)
	}
	target := replaced(t, base, []Set{{UID: "new", Count: 2}})
	p := syntheticProof(base, target, h.GraphSHA256())
	p.Bounds["actor_a.em"] = Interval{0, 0}
	next, err := s.Resolve(context.Background(), target, h, p)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := next.EvaluateDPS(nil); err != nil {
		t.Fatal(err)
	}
	if _, err := next.EvaluateDPS(map[string]float64{"actor_a.em": 0.001}); err == nil {
		t.Fatal("point evidence widened into arbitrary artifact coverage")
	}
}

func TestSameTopologyUsesFreshFormulaWithoutProof(t *testing.T) {
	base := fixtureContext(t)
	target := replaced(t, base, []Set{{UID: "new", Count: 2}})
	s, _ := NewSession(func(_ context.Context, c *Context) (Capture, error) {
		amount := "180"
		if c.key == target.key {
			amount = "130"
		}
		return syntheticCapture(c, amount), nil
	}, 4)
	a, err := s.Resolve(context.Background(), base, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	b, err := s.Resolve(context.Background(), target, a, nil)
	if err != nil {
		t.Fatal(err)
	}
	if b.Route() != FreshCapture || s.attempted != 4 {
		t.Fatal("topology authorized unsafe reuse")
	}
	if got, _ := b.EvaluateDPS(nil); got != 130 {
		t.Fatal("old buff retained")
	}
	again, err := s.Resolve(context.Background(), target, a, nil)
	if err != nil || again.Route() != IdentityReuse || s.attempted != 4 {
		t.Fatal("fresh context not reused")
	}
}
