package seteffects

// Active-source controls use a tiny synthetic event tape, NOT a simulated team
// or production search. Only the managed, engine-bound source gate supplies this
// opt-in envelope. Coefficients below are test expectations from the current
// source, never a production mechanic table.
import (
	"encoding/json"
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
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
)

// One real neutral schedule plus a same-seed changed-set control pins response
// for this fixture only. It is not ordinary-DPS/search/UI acceptance.
func TestRuleNeutralCapturedFixture(t *testing.T) {
	job := os.Getenv("GTT_NEUTRAL_CAPTURE_DIR")
	if job == "" {
		t.Skip("managed candidate capture only")
	}
	c := activeRuleCatalog(t)
	read := func(name string, value any) {
		t.Helper()
		b, err := os.ReadFile(filepath.Join(job, name))
		if err != nil {
			t.Fatal(err)
		}
		if err = json.Unmarshal(b, value); err != nil {
			t.Fatal(err)
		}
	}
	var member contracts.IRSeedMember
	var sidecar contracts.EffectInputsOutput
	read("neutral-member.json", &member)
	read("neutral-member.json.effects.json", &sidecar)
	owners := append([]string(nil), sidecar.CharacterKeys...)
	sort.Strings(owners)
	panel, err := evaluator.CompileMembers(owners, []uint64{member.Seed}, []contracts.IRSeedMember{member})
	if err != nil {
		t.Fatal(err)
	}
	b, err := NewNeutralBinding(c, []contracts.EffectInputsOutput{sidecar})
	if err != nil {
		t.Fatal(err)
	}
	started := time.Now()
	program, err := panel.PrepareEffectInputsWithReads(b.Ports(), b.Reads())
	if err != nil {
		t.Fatal(err)
	}
	t.Logf("one aggregate preparation %.3fs, ports=%d nodes=%d", time.Since(started).Seconds(), len(b.Ports()), program.NodeCount())
	owner := func(key string) int {
		for i, actor := range sidecar.CharacterKeys {
			if actor == key {
				return i
			}
		}
		t.Fatal("fixture actor missing", key)
		return -1
	}
	core := []RuleChoice{{owner("flins"), "nightoftheskysunveiling", 4}, {owner("ineffa"), "silkenmoonsserenade", 4}, {owner("columbina"), "tenacityofthemillelith", 4}, {owner("jahoda"), "viridescentvenerer", 4}}
	cases := [][]RuleChoice{nil, {{owner("flins"), "obsidiancodex", 4}, {owner("ineffa"), "obsidiancodex", 4}}}
	for _, choice := range core {
		cases = append(cases, []RuleChoice{choice})
	}
	cases = append(cases, core)
	base := 0.0
	var control contracts.IRSeedMember
	read("control-member.json", &control)
	controlPanel, err := evaluator.CompileMembers(owners, []uint64{control.Seed}, []contracts.IRSeedMember{control})
	if err != nil {
		t.Fatal(err)
	}
	controlScore, err := controlPanel.Evaluate(make([]float64, len(controlPanel.Coordinates())))
	if err != nil {
		t.Fatal(err)
	}
	for ci, choices := range cases {
		started = time.Now()
		v := b.EvaluatePackages(choices)
		if !v.Complete() {
			t.Errorf("choices=%v incomplete: %v (%.3fs)", choices, v.Boundaries, time.Since(started).Seconds())
			continue
		}
		dps, err := program.Evaluate(make([]float64, len(panel.Coordinates())), v.Values)
		if err != nil {
			t.Fatal(err)
		}
		if ci == 0 {
			base = dps
		}
		if ci == 1 && math.Abs(dps-base) > 1e-8 {
			t.Errorf("inactive Obsidian gained %g DPS", dps-base)
		}
		t.Logf("choices=%v dps=%.6f delta=%.6f effect_seconds=%.3f uncertainty=%v", choices, dps, dps-base, time.Since(started).Seconds(), v.Uncertainty)
		if ci == len(cases)-1 {
			t.Logf("FIXTURE_RESPONSE predicted=%.6f captured=%.6f residual=%.12g percent=%.12g neutral_ms=%d control_ms=%d topology_equal=%v; one observed schedule, not ordinary DPS or product acceptance", dps, controlScore.MeanDPS, dps-controlScore.MeanDPS, 100*(dps/controlScore.MeanDPS-1), member.DurationMS, control.DurationMS, member.TopologySHA256 == control.TopologySHA256)
			if member.TopologySHA256 != control.TopologySHA256 || member.DurationMS != control.DurationMS || math.Abs(dps-controlScore.MeanDPS) > 1e-8 {
				t.Error("saved changed-set response regressed")
			}
			// Diagnostic POINT specialization of the raw graph only: independently
			// attribute the aggregate residual without changing production scoring.
			point := member
			point.Nodes = append([]contracts.IRNode(nil), member.Nodes...)
			for i, port := range b.Ports() {
				point.Nodes[port.NodeID-1] = contracts.IRNode{NodeID: port.NodeID, Operation: "constant", Value: strconv.FormatFloat(port.Observed+v.Values[i], 'g', -1, 64), Inputs: []contracts.IRInput{}}
			}
			p, err := formula.CompileSeedMember(point, owners, panel.Coordinates())
			if err != nil {
				t.Fatal(err)
			}
			values, err := p.EvaluateChannelDamageDense(make([]float64, len(panel.Coordinates())))
			if err != nil {
				t.Fatal(err)
			}
			type residual struct {
				index                      int
				delta, predicted, observed float64
			}
			rows, byKind, sum := []residual{}, map[string]float64{}, 0.0
			if len(control.Channels) != len(point.Channels) {
				t.Fatal("response topology changed")
			}
			for i, ch := range point.Channels {
				other := control.Channels[i]
				if ch.ChannelID != other.ChannelID || ch.ActorKey != other.ActorKey || ch.Kind != other.Kind || ch.AttackTag != other.AttackTag {
					t.Fatal("response channels misaligned", i)
				}
				observed, err := strconv.ParseFloat(other.BaselineDamage, 64)
				if err != nil {
					t.Fatal(err)
				}
				scale := 1000 / float64(member.DurationMS)
				delta := (values[i] - observed) * scale
				if math.Abs(delta) > 1e-8 {
					t.Errorf("saved channel response regressed: %s delta=%g DPS", ch.ChannelID, delta)
				}
				rows = append(rows, residual{i, delta, values[i] * scale, observed * scale})
				byKind[ch.ActorKey+"/"+ch.Kind+"/"+ch.AttackTag] += delta
				sum += values[i] * scale
			}
			if math.Abs(sum-dps) > 1e-8 {
				t.Fatal("diagnostic graph differs from prepared aggregate", sum, dps)
			}
			sort.Slice(rows, func(i, j int) bool { return math.Abs(rows[i].delta) > math.Abs(rows[j].delta) })
			t.Logf("response residual by actor/kind/tag: %v", byKind)
			for _, r := range rows[:min(10, len(rows))] {
				ch, hit := point.Channels[r.index], sidecar.Neutral.Hits[r.index]
				t.Logf("response hit %s actor=%s frame=%d kind=%s tag=%s predicted=%.6f observed=%.6f delta=%.6f", ch.ChannelID, ch.ActorKey, hit.Point.HitFrame, ch.Kind, ch.AttackTag, r.predicted, r.observed, r.delta)
			}
		}
	}
	// New stat-dependent package on the SAME neutral graph: retained ER must
	// stay variable after binding. This is not an independent Emblem sim gate.
	expressions := b.CompilePackages([]RuleChoice{{owner("ineffa"), "emblemofseveredfate", 4}})
	if !expressions.Complete() {
		t.Fatalf("captured stat-dependent binding: %v", expressions.Boundaries)
	}
	bound, err := program.BindEffectExpressions(expressions.Effects)
	if err != nil {
		t.Fatal(err)
	}
	x := make([]float64, len(panel.Coordinates()))
	a, err := bound.Evaluate(x, nil)
	if err != nil {
		t.Fatal(err)
	}
	found := false
	for i, key := range panel.Coordinates() {
		if key == "ineffa.energy_recharge" {
			x[i] = 1
			found = true
		}
	}
	if !found {
		t.Fatal("latent ER coordinate was discarded")
	}
	z, err := bound.Evaluate(x, nil)
	if err != nil || z <= a {
		t.Fatal("bound ER did not affect damage", a, z, err)
	}
	t.Logf("captured Emblem expression: %.6f -> %.6f with +1 artifact ER; roots=%d bound_nodes=%d uncertainty=%v", a, z, len(b.Reads()), bound.NodeCount(), expressions.Uncertainty)
}

func activeRuleCatalog(t *testing.T) *SourceCatalog {
	t.Helper()
	name := os.Getenv("GTT_RULE_SOURCE_BUNDLE")
	if name == "" {
		t.Skip("managed active-source envelope not supplied")
	}
	data, err := os.ReadFile(name)
	if err != nil {
		t.Fatal(err)
	}
	var bundle SourceBundle
	if err = json.Unmarshal(data, &bundle); err != nil {
		t.Fatal(err)
	}
	c, err := CompileSourceBundle(bundle, contracts.EngineBinding{ArtifactSHA256: bundle.EngineSHA256, SourceManifestSHA256: bundle.SourceManifestSHA256}, bundle.CatalogSHA256)
	if err != nil {
		t.Fatal(err)
	}
	return c
}

// Diagnostic coverage, not a PASS certificate for unsupported packages. One
// captured schedule is reused by every source rule; this makes no engine calls.
func TestRuleNeutralCatalogCoverage(t *testing.T) {
	job := os.Getenv("GTT_NEUTRAL_CAPTURE_DIR")
	if job == "" || os.Getenv("GTT_RULE_COVERAGE") != "1" {
		t.Skip("explicit managed single-tape coverage audit only")
	}
	c := activeRuleCatalog(t)
	data, err := os.ReadFile(filepath.Join(job, "neutral-member.json.effects.json"))
	if err != nil {
		t.Fatal(err)
	}
	var sidecar contracts.EffectInputsOutput
	if err = json.Unmarshal(data, &sidecar); err != nil {
		t.Fatal(err)
	}
	b, err := NewNeutralBinding(c, []contracts.EffectInputsOutput{sidecar})
	if err != nil {
		t.Fatal(err)
	}
	started := time.Now()
	total, complete, approximate := 0, 0, 0
	for _, set := range c.Sets {
		failures := map[string][]string{}
		for _, pieces := range []int{2, 4} {
			if pieces == 4 && !set.FourPieceModeled {
				continue
			}
			for owner, actor := range sidecar.Neutral.Context.Characters {
				total++
				out := b.CompilePackages([]RuleChoice{{owner, set.Key, pieces}})
				if out.Complete() {
					complete++
					if len(out.Uncertainty) != 0 {
						approximate++
					}
				} else {
					code := strings.Join(out.Boundaries, " | ")
					failures[code] = append(failures[code], strconv.Itoa(pieces)+":"+actor.Key)
				}
			}
		}
		codes := make([]string, 0, len(failures))
		for code := range failures {
			codes = append(codes, code)
		}
		sort.Strings(codes)
		for _, code := range codes {
			t.Logf("COVERAGE %s %v: %s", set.Key, failures[code], code)
		}
	}
	t.Logf("COVERAGE_SUMMARY total=%d bound=%d approximate=%d unresolved=%d seconds=%.3f; one neutral tape, not response/search acceptance", total, complete, approximate, total-complete, time.Since(started).Seconds())
}

func TestRuleActiveSourcePortsRemainVariableAfterReduction(t *testing.T) {
	c := activeRuleCatalog(t)
	n := ruleTestNeutral()
	trigger := int(ruleTestConstant(t, c, "pkg/core/event", "OnLunarCharged"))
	n.Ledger.Events = []contracts.CombatEvent{ruleTestEvent(trigger, 2, 0, 0, 1)}
	n.Stats = []contracts.NeutralStatInput{
		{NodeID: 3, Kind: "stat", Owner: "beta", Stat: "em", Point: contracts.NeutralInputPoint{Mode: "snapshot", Order: 20, Frame: 11}},
		{NodeID: 7, Kind: "stat", Owner: "beta", Stat: "cr", Point: contracts.NeutralInputPoint{Mode: "snapshot", Order: 20, Frame: 11}},
	}
	b, err := NewNeutralBinding(c, []contracts.EffectInputsOutput{{SourceManifestBodySHA256: c.SourceManifestSHA256, Neutral: n}})
	if err != nil {
		t.Fatal(err)
	}
	in := func(ids ...uint32) []contracts.IRInput {
		out := []contracts.IRInput{}
		for _, id := range ids {
			out = append(out, contracts.IRInput{NodeID: id, Relation: "operand"})
		}
		return out
	}
	m := contracts.IRSeedMember{Seed: 1, DurationMS: 1000, TopologySHA256: strings.Repeat("a", 64), Nodes: []contracts.IRNode{
		{NodeID: 1, Operation: "constant", Value: "1000", Inputs: in()},
		{NodeID: 2, Operation: "artifact_stat", Coordinate: "beta.em", Inputs: in()},
		{NodeID: 3, Operation: "constant", Value: "0", Inputs: in()},
		{NodeID: 4, Operation: "add", Inputs: in(1, 2, 3)},
		{NodeID: 5, Operation: "constant", Value: "1", Inputs: in()},
		{NodeID: 6, Operation: "artifact_stat", Coordinate: "beta.crit_rate", Inputs: in()},
		{NodeID: 7, Operation: "constant", Value: "0", Inputs: in()},
		{NodeID: 8, Operation: "add", Inputs: in(5, 6, 7)},
		{NodeID: 9, Operation: "multiply", Inputs: in(4, 8)},
	}, Channels: []contracts.IRChannel{{ChannelID: "test", Kind: "direct", ActorKey: "beta", AttackTag: "tag/1", DamageType: "physical", RootNodeID: 9, HitCount: 1, BaselineDamage: "1000", ResponseCoordinates: []string{"beta.crit_rate", "beta.em"}}}, OpaqueBoundaries: []contracts.IROpaqueBoundary{}}
	member, err := formula.CompileSeedMember(m, []string{"alpha", "beta", "delta", "gamma"}, []string{"beta.crit_rate", "beta.em"})
	if err != nil {
		t.Fatal(err)
	}
	program, err := formula.PrepareParametric([]*formula.CompiledMember{member}, b.Ports())
	if err != nil {
		t.Fatal(err)
	}
	nodes := program.NodeCount()
	for _, pieces := range []int{0, 2, 4, 2, 0} {
		choices := []RuleChoice{}
		if pieces != 0 {
			choices = append(choices, RuleChoice{1, "nightoftheskysunveiling", pieces})
		}
		vector := b.EvaluatePackages(choices)
		if !vector.Complete() {
			t.Fatal(vector)
		}
		bonusEM, bonusCR := 0.0, 0.0
		if pieces >= 2 {
			bonusEM = 80
		}
		if pieces >= 4 {
			bonusCR = .3
		}
		got, err := program.Evaluate([]float64{.1, 120}, vector.Values)
		want := (1000 + 120 + bonusEM) * (1 + .1 + bonusCR)
		if err != nil || math.Abs(got-want) > 1e-9 || program.NodeCount() != nodes {
			t.Fatal(got, want, err)
		}
	}
}
func ruleTestConstant(t *testing.T, c *SourceCatalog, module, name string) float64 {
	t.Helper()
	for _, s := range c.Sets {
		if s.rule != nil {
			v := newRuleVM(s.rule, nil, 1000)
			m := s.rule.modules[gcsimImport+module]
			if m != nil {
				out, err := ruleTry(func() any { return v.lookup(m.envs[m.files[0]], name) })
				if err != nil {
					t.Fatal(err)
				}
				return ruleNumber(out)
			}
		}
	}
	t.Fatal("constant unavailable", module, name)
	return 0
}
func ruleTestNeutral() *contracts.NeutralInputs {
	n := &contracts.NeutralInputs{Context: contracts.NeutralContext{NoSets: true, Moonsign: 2, Active: 1, DurationFrames: 6000}, Ledger: contracts.CombatEventLedger{Events: []contracts.CombatEvent{}}, World: &contracts.NeutralWorldLedger{Complete: true, States: []contracts.NeutralWorldState{{Order: 1, Active: 1, Modifiers: []contracts.NeutralModifierIdentity{}}}}}
	for i, key := range []string{"alpha", "beta", "gamma", "delta"} {
		n.Context.Characters = append(n.Context.Characters, contracts.NeutralCharacter{Index: i, Key: key, Base: contracts.EventValue{Kind: "object", Fields: map[string]contracts.EventValue{}}})
	}
	return n
}
func ruleTestAttack(actor int, tag, element float64) contracts.EventValue {
	return contracts.EventValue{Kind: "object", Type: gcsimImport + "pkg/core/info.AttackInfo", Fields: map[string]contracts.EventValue{
		"ActorIndex": {Kind: "number", Number: float64(actor)}, "AttackTag": {Kind: "number", Number: tag}, "Element": {Kind: "number", Number: element}, "Amped": {Kind: "bool"}, "Catalyzed": {Kind: "bool"},
	}}
}
func ruleTestEvent(id int, actor int, tag, element float64, active int) contracts.CombatEvent {
	return contracts.CombatEvent{Order: 10, EndOrder: 11, Frame: 10, Active: active, Event: id, Arguments: []contracts.EventValue{
		{Kind: "target", Type: "*" + gcsimImport + "pkg/enemy.Enemy", Fields: map[string]contracts.EventValue{"Key": {Kind: "number", Number: 9}}},
		{Kind: "object", Type: "*" + gcsimImport + "pkg/core/info.AttackEvent", Fields: map[string]contracts.EventValue{"Info": ruleTestAttack(actor, tag, element)}},
	}}
}
func TestRuleActiveSourceNeutralControls(t *testing.T) {
	c := activeRuleCatalog(t)
	hydro := ruleTestConstant(t, c, "pkg/core/attributes", "Hydro")
	electro := ruleTestConstant(t, c, "pkg/core/attributes", "Electro")
	skill := ruleTestConstant(t, c, "pkg/core/attacks", "AttackTagElementalArt")
	swirl := ruleTestConstant(t, c, "pkg/core/attacks", "AttackTagSwirlElectro")
	lunar := ruleTestConstant(t, c, "pkg/core/attacks", "AttackTagDirectLunarCharged")
	enemyDamage := int(ruleTestConstant(t, c, "pkg/core/event", "OnEnemyDamage"))
	lunarEvent := int(ruleTestConstant(t, c, "pkg/core/event", "OnLunarCharged"))
	swirlEvent := int(ruleTestConstant(t, c, "pkg/core/event", "OnSwirlElectro"))
	type check struct {
		name    string
		choices []RuleChoice
		events  []contracts.CombatEvent
		q       RuleQuery
		want    float64
	}
	q := func(owner int, kind, stat string) RuleQuery {
		return RuleQuery{Order: 20, Frame: 11, Active: 1, Owner: owner, Target: 9, Kind: kind, Mode: "stat", Stat: stat, TargetStateComplete: true}
	}
	reaction := q(0, "reaction", "")
	reaction.Attack = ruleTestAttack(0, lunar, electro)
	vvReaction := q(3, "reaction", "")
	vvReaction.Attack = ruleTestAttack(3, swirl, electro)
	tests := []check{
		{"obsidian unavailable damage", []RuleChoice{{2, "obsidiancodex", 4}}, nil, q(2, "stat", "dmg%"), 0},
		{"obsidian unavailable crit", []RuleChoice{{2, "obsidiancodex", 4}}, nil, q(2, "stat", "cr"), 0},
		{"silken own 2p", []RuleChoice{{2, "silkenmoonsserenade", 2}}, nil, q(2, "stat", "er"), .2},
		{"silken ally em", []RuleChoice{{2, "silkenmoonsserenade", 4}}, []contracts.CombatEvent{ruleTestEvent(enemyDamage, 2, skill, hydro, 1)}, q(0, "stat", "em"), 120},
		{"silken team reaction", []RuleChoice{{2, "silkenmoonsserenade", 4}}, []contracts.CombatEvent{ruleTestEvent(enemyDamage, 2, skill, hydro, 1)}, reaction, .1},
		{"night cr", []RuleChoice{{1, "nightoftheskysunveiling", 4}}, []contracts.CombatEvent{ruleTestEvent(lunarEvent, 2, lunar, electro, 1)}, q(1, "stat", "cr"), .3},
		{"night team reaction", []RuleChoice{{1, "nightoftheskysunveiling", 4}}, []contracts.CombatEvent{ruleTestEvent(lunarEvent, 2, lunar, electro, 1)}, reaction, .1},
		{"vv electro resistance", []RuleChoice{{3, "viridescentvenerer", 4}}, []contracts.CombatEvent{ruleTestEvent(swirlEvent, 3, swirl, electro, 3)}, q(0, "resistance", "electro"), -.4},
		{"vv personal swirl", []RuleChoice{{3, "viridescentvenerer", 4}}, nil, vvReaction, .6},
		{"tenacity ally atk", []RuleChoice{{0, "tenacityofthemillelith", 4}}, []contracts.CombatEvent{ruleTestEvent(enemyDamage, 0, skill, hydro, 1)}, q(1, "stat", "atk%"), .2},
		{"shared silken em is not doubled", []RuleChoice{{0, "silkenmoonsserenade", 4}, {2, "silkenmoonsserenade", 4}}, []contracts.CombatEvent{ruleTestEvent(enemyDamage, 2, skill, hydro, 1)}, q(1, "stat", "em"), 120},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			n := ruleTestNeutral()
			n.Ledger.Events = test.events
			r := c.ReplayNeutralRules(n, test.choices, []RuleQuery{test.q})
			if r.Boundary != "" || len(r.Values) != 1 || !r.Values[0].Known || math.Abs(r.Values[0].Value-test.want) > 1e-12 {
				t.Fatalf("want %g: %+v", test.want, r)
			}
		})
	}
	t.Run("partial modifier evidence cannot prove inactive obsidian", func(t *testing.T) {
		n := ruleTestNeutral()
		n.World = nil
		r := c.ReplayNeutralRules(n, []RuleChoice{{2, "obsidiancodex", 4}}, []RuleQuery{q(2, "stat", "dmg%")})
		if r.Boundary == "" && r.Values[0].Known {
			t.Fatal("missing state became zero", r)
		}
	})
	t.Run("selected stat filter differs from full snapshot", func(t *testing.T) {
		query := q(0, "stat", "hp%")
		keys := []string{"em"}
		query.StatKeys = &keys
		r := c.ReplayNeutralRules(ruleTestNeutral(), []RuleChoice{{0, "tenacityofthemillelith", 2}}, []RuleQuery{query})
		if r.Boundary != "" || !r.Values[0].Known || r.Values[0].Value != 0 {
			t.Fatal(r)
		}
		query.StatKeys = nil
		r = c.ReplayNeutralRules(ruleTestNeutral(), []RuleChoice{{0, "tenacityofthemillelith", 2}}, []RuleQuery{query})
		if r.Boundary != "" || !r.Values[0].Known || r.Values[0].Value != .2 {
			t.Fatal(r)
		}
	})
}
