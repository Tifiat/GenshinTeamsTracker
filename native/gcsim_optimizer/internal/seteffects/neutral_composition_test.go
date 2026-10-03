package seteffects

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"reflect"
	"testing"
)

func TestNeutralSymbolicReadWriteConflictUsesJointGroup(t *testing.T) {
	a, bb := RuleChoice{0, "reader", 4}, RuleChoice{1, "writer", 4}
	read, write := ruleFootprint{statDependent: true}, ruleFootprint{}
	read.readStat(1, "er", "non_extra_stat")
	write.writeStat(1, "er", false)
	leaf := &formula.InputExpression{Operation: "read", Key: "owner1.er"}
	joint := &formula.InputExpression{Operation: "add", Inputs: []*formula.InputExpression{leaf, {Operation: "constant", Value: .5}}}
	b := &NeutralBinding{catalog: &SourceCatalog{}, keys: []string{"damage"}, members: []neutralBoundMember{{neutral: ruleTestNeutral(), ports: []neutralBoundPort{{dimension: 0}}}},
		components: map[RuleChoice]neutralComponent{a: {usable: true, raw: []float64{0}, expressions: map[int]*formula.InputExpression{0: leaf}, footprint: read}, bb: {usable: true, raw: []float64{0}, footprint: write}},
		groups:     map[string]neutralComponent{ruleChoicesKey([]RuleChoice{a, bb}): {usable: true, raw: []float64{0}, expressions: map[int]*formula.InputExpression{0: joint}, footprint: read}}}
	got := b.CompilePackagesCompact([]RuleChoice{a, bb})
	if !got.Complete() || got.Effects["damage"] != joint || b.stats.GroupHits != 1 || b.stats.Merges != 1 {
		t.Fatal("dependent increment bypassed joint replay", got, b.stats)
	}
	if b.components[a].expressions[0] != leaf {
		t.Fatal("cached expression mutated")
	}
	if n, ok := componentExpressionSize(map[int]*formula.InputExpression{0: joint, 1: joint}, 3); !ok || n != 3 {
		t.Fatal("DAG size", n, ok)
	}
	if _, ok := componentExpressionSize(map[int]*formula.InputExpression{0: joint}, 2); ok {
		t.Fatal("expression node cap ignored")
	}
}

func TestNeutralComponentFootprintRejectsSharedWritesReadsAndStats(t *testing.T) {
	a, b := ruleFootprint{}, ruleFootprint{}
	a.write("shared")
	b.read("other")
	if !a.independent(b) {
		t.Fatal("independent effects rejected")
	}
	b.read("shared")
	if a.independent(b) {
		t.Fatal("cross-effect condition lost")
	}
	b = ruleFootprint{}
	b.write("shared")
	if a.independent(b) {
		t.Fatal("shared-key replacement became addition")
	}
	b = ruleFootprint{statDependent: true}
	if a.independent(b) {
		t.Fatal("stat expression became additive constant")
	}
}

func TestNeutralStatFootprintsKeepOwnerStatExtraAndUnknownWriters(t *testing.T) {
	read := ruleFootprint{statDependent: true}
	read.readStat(1, "er", "non_extra_stat")
	for _, test := range []struct {
		owner              int
		stat               string
		extra, independent bool
	}{
		{0, "er", false, true}, {1, "atk%", false, true},
		{1, "er", true, true}, {1, "er", false, false},
		{1, "", false, false}, {0, "", false, true},
	} {
		write := ruleFootprint{}
		write.writeStat(test.owner, test.stat, test.extra)
		if read.independent(write) != test.independent || write.independent(read) != test.independent {
			t.Fatalf("stat dependency mismatch: %+v", test)
		}
	}
	ordinary := ruleFootprint{statDependent: true}
	ordinary.readStat(1, "er", "stat")
	extra := ruleFootprint{}
	extra.writeStat(1, "er", true)
	if ordinary.independent(extra) {
		t.Fatal("ordinary Stat ignored Extra")
	}
	merged := ruleFootprint{}
	merged.merge(read)
	merged.readStat(2, "hp", "stat")
	if len(read.statReads) != 1 {
		t.Fatal("merged footprint mutated its cache source")
	}
}

func TestNeutralStatWriterUsesAffectedFilterAndConservativeWildcard(t *testing.T) {
	for _, test := range []struct {
		affected any
		extra    bool
		stat     string
	}{
		{2.0, false, "er"}, {2.0, true, "er"}, {0.0, false, ""}, {nil, false, ""}, {99.0, false, ""},
	} {
		h := &ruleReplayHost{statIndices: map[string]int{"n/a": 0, "er": 2}, touched: map[ruleModifierIdentity]bool{}}
		h.replaceMod(replayMod{kind: "stat", owner: 1, target: -1, key: "test", affected: test.affected, extra: test.extra})
		if !h.footprint.statWrites[ruleStatDependency{1, test.stat, "stat"}] {
			t.Fatal("missing stat writer", test, h.footprint)
		}
		if h.footprint.statWrites[ruleStatDependency{1, test.stat, "non_extra_stat"}] == test.extra {
			t.Fatal("Extra exclusion lost", test, h.footprint)
		}
	}
}

func TestRuleSourceComponentCompositionMatchesJointReplay(t *testing.T) {
	c := activeRuleCatalog(t)
	n := ruleTestNeutral()
	enemyDamage := int(ruleTestConstant(t, c, "pkg/core/event", "OnEnemyDamage"))
	lunarEvent := int(ruleTestConstant(t, c, "pkg/core/event", "OnLunarCharged"))
	skill := ruleTestConstant(t, c, "pkg/core/attacks", "AttackTagElementalArt")
	hydro := ruleTestConstant(t, c, "pkg/core/attributes", "Hydro")
	first := ruleTestEvent(enemyDamage, 2, skill, hydro, 1)
	second := ruleTestEvent(lunarEvent, 2, skill, hydro, 1)
	second.Order = 12
	second.EndOrder = 13
	third := ruleTestEvent(enemyDamage, 0, skill, hydro, 1)
	third.Order = 14
	third.EndOrder = 15
	n.Ledger.Events = []contracts.CombatEvent{first, second, third}
	for i, stat := range []string{"em", "cr", "atk%"} {
		n.Stats = append(n.Stats, contracts.NeutralStatInput{NodeID: uint32(i + 1), Owner: "beta", Kind: "stat", Stat: stat, Point: contracts.NeutralInputPoint{Mode: "snapshot", Order: 20, Frame: 11}})
	}
	b, err := NewNeutralBinding(c, []contracts.EffectInputsOutput{{SourceManifestBodySHA256: c.SourceManifestSHA256, Neutral: n}})
	if err != nil {
		t.Fatal(err)
	}
	cases := [][]RuleChoice{
		{{1, "nightoftheskysunveiling", 4}, {2, "silkenmoonsserenade", 4}},
		{{0, "silkenmoonsserenade", 4}, {2, "silkenmoonsserenade", 4}},
		{{0, "tenacityofthemillelith", 4}, {1, "nightoftheskysunveiling", 2}, {1, "emblemofseveredfate", 2}},
		{{0, "noblesseoblige", 4}, {2, "noblesseoblige", 4}, {1, "nightoftheskysunveiling", 4}},
	}
	for _, choices := range cases {
		for repeat := 0; repeat < 2; repeat++ {
			got, want := b.CompilePackages(choices), b.compilePackagesJoint(choices)
			if !got.Complete() || !want.Complete() || !reflect.DeepEqual(got.Effects, want.Effects) || !reflect.DeepEqual(got.Uncertainty, want.Uncertainty) {
				t.Fatalf("%v got=%+v want=%+v", choices, got, want)
			}
		}
	}
	if len(b.components) == 0 {
		t.Fatal("no source components retained")
	}
	if b.PreparationStats().GroupHits == 0 {
		t.Fatal("shared groups were not reused", b.PreparationStats())
	}
	for _, choices := range [][]RuleChoice{{{1, "nightoftheskysunveiling", 4}, {1, "gildeddreams", 2}}, {{1, "gildeddreams", 2}, {1, "gildeddreams", 2}}} {
		if b.CompilePackages(choices).Complete() {
			t.Fatal("composed illegal package", choices)
		}
	}
}

func TestNeutralConflictGroupsMergeNewDependenciesWithoutMutatingCache(t *testing.T) {
	n := ruleTestNeutral()
	a, bb, c := RuleChoice{0, "a", 4}, RuleChoice{1, "b", 4}, RuleChoice{2, "c", 4}
	fa, fb, fc, fab := ruleFootprint{}, ruleFootprint{}, ruleFootprint{}, ruleFootprint{}
	fa.write("x")
	fb.read("x")
	fc.read("y")
	fab.write("y")
	component := func(v float64, f ruleFootprint) neutralComponent {
		return neutralComponent{raw: []float64{v}, footprint: f, usable: true}
	}
	abkey, abckey := ruleChoicesKey([]RuleChoice{a, bb}), ruleChoicesKey([]RuleChoice{a, bb, c})
	b := &NeutralBinding{catalog: &SourceCatalog{}, keys: []string{"port"}, members: []neutralBoundMember{{neutral: n, ports: []neutralBoundPort{{dimension: 0}}}},
		components: map[RuleChoice]neutralComponent{a: component(.1, fa), bb: component(.2, fb), c: component(.3, fc)},
		groups:     map[string]neutralComponent{abkey: component(.4, fab), abckey: component(.9, ruleFootprint{})}}
	for _, choices := range [][]RuleChoice{{a, bb, c}, {c, bb, a}} {
		x := b.CompilePackages(choices)
		if !x.Complete() || x.Effects["port"].Value != .9 {
			t.Fatal("missed newly exposed conflict", x)
		}
	}
	if b.stats.GroupHits != 4 || b.stats.Replays != 0 || b.groups[abkey].footprint.reads["x"] || b.groups[abckey].footprint.writes["y"] {
		t.Fatal("cache mutated or not reused", b.stats, b.groups)
	}
	zero := b.CompilePackages(nil)
	if !zero.Complete() || zero.Effects["port"].Value != 0 || b.stats.Replays != 0 {
		t.Fatal("empty package replayed", zero, b.stats)
	}
}
