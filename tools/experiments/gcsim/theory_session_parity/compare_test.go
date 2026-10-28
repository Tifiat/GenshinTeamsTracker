package main

// Scratch-only Stage12 comparison helpers. The managed overlay supplies the
// pinned research harness and prototype package; this file captures no engine.
import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"math"
	"sort"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
	proto "genshinteamstracker/native/gcsim_optimizer/internal/theoryprototype"
	"genshinteamstracker/native/gcsim_optimizer/internal/theorysearch"
	"genshinteamstracker/native/gcsim_optimizer/internal/theoryteams"
)

func referencePhase(h *hybridRun) theorysearch.ParityPhase {
	out := theorysearch.ParityPhase{Aliases: map[string][]string{}, Unavailable: map[string][]string{}, Visited: map[string]string{}, Refined: map[string]int{}}
	convert := func(c feasibleCandidate) theorysearch.ParityCandidate {
		return theorysearch.ParityCandidate{Packages: stage12CopyPackages(c.packages),
			State: alloc.State{Mains: c.state.Mains, Lines: c.state.Lines, Upgrades: c.state.Upgrades},
			Value: c.value, Family: c.family}
	}
	for _, c := range r2Sorted(h.pool) {
		out.Pool = append(out.Pool, convert(c))
	}
	for _, c := range h.bank {
		out.Bank = append(out.Bank, convert(c))
	}
	for family, rows := range h.aliases {
		keys := make([]string, 0, len(rows))
		for key := range rows {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		out.Aliases[family] = keys
	}
	for key, family := range h.visited {
		out.Visited[key] = family
		if family == "" {
			out.Unavailable[key] = append([]string(nil), h.w.metadata[key]...)
			sort.Strings(out.Unavailable[key])
		}
	}
	for family, level := range h.refined {
		out.Refined[family] = level
	}
	out.Work = theorysearch.Work{Formula: h.w.work.Formula, Gradient: h.w.work.Gradient,
		AllocationAttempts: h.w.work.AllocationAttempts, AliasHits: h.aliasHits,
		CompletedSweeps: h.fullSweeps, CompletedPasses: h.completedPasses,
		IndependentStarts: h.independent, TransferredStarts: h.transferred, DeepBundles: h.refinedPasses}
	return out
}

// Existing six-argument callers compare all numerical counters. Optional true
// ignores only DeepBundles when the reference observer precedes that boundary.
func stage12ComparePhases(t *testing.T, name string, actual, expected theorysearch.ParityPhase,
	routeA, routeB []string, ignoreDeepBundles ...bool) {
	t.Helper()
	if len(ignoreDeepBundles) > 1 {
		t.Fatal("Stage12 comparison accepts at most one DeepBundles override")
	}
	ignore := len(ignoreDeepBundles) == 1 && ignoreDeepBundles[0]
	if difference := stage12PhaseDifference(actual, expected, routeA, routeB, ignore); difference != "" {
		t.Fatalf("Stage12 %s parity: %s", stage12Short(name), difference)
	}
	normal, difference := stage12NormalizeActual(actual)
	if difference != "" {
		t.Fatal(difference)
	}
	reference := stage12CopyPhase(expected)
	actualHashPhase, referenceHashPhase := stage12CopyPhase(normal), stage12CopyPhase(reference)
	if ignore {
		actualHashPhase.Work.DeepBundles = 0
		referenceHashPhase.Work.DeepBundles = 0
	}
	routesCompared := routeA != nil && routeB != nil
	receipt := map[string]any{
		"kind": "numeric_phase_parity", "name": name, "status": "pass", "exact_float_bits": true,
		"all_witnesses_full45": true, "pool_count": len(normal.Pool), "bank_count": len(normal.Bank),
		"alias_families": len(normal.Aliases), "alias_tuples": stage12AliasCount(normal.Aliases),
		"visited_count": len(normal.Visited), "refined_count": len(normal.Refined),
		"unavailable_count": len(normal.Unavailable), "fingerprint_scope": "compared_numeric_fields",
		"actual_sha256": stage12Fingerprint(t, actualHashPhase), "reference_sha256": stage12Fingerprint(t, referenceHashPhase),
		"actual_work": normal.Work, "reference_work": expected.Work, "ignore_deep_bundles": ignore,
		"route_sequence_compared": routesCompared,
	}
	if routesCompared {
		receipt["route_count"] = len(routeA)
		receipt["route_sha256"] = stage12Fingerprint(t, routeA)
	} else {
		receipt["route_check"] = "not_compared_here_reference_hash_checked_by_caller"
	}
	raw, err := json.Marshal(receipt)
	if err != nil {
		t.Fatal(err)
	}
	fmt.Println("STAGE12_RECEIPT " + string(raw))
}

func stage12CopyPackages(p [4]domain.Package) [4]domain.Package {
	for a := range p {
		p[a].Sets = append([]contracts.SetRequirement(nil), p[a].Sets...)
	}
	return p
}

func stage12CopyPhase(p theorysearch.ParityPhase) theorysearch.ParityPhase {
	out := theorysearch.ParityPhase{Pool: make([]theorysearch.ParityCandidate, len(p.Pool)),
		Bank: make([]theorysearch.ParityCandidate, len(p.Bank)), Aliases: map[string][]string{}, Unavailable: map[string][]string{},
		Visited: map[string]string{}, Refined: map[string]int{}, Work: p.Work}
	for i, row := range p.Pool {
		out.Pool[i] = row
		out.Pool[i].Packages = stage12CopyPackages(row.Packages)
	}
	for i, row := range p.Bank {
		out.Bank[i] = row
		out.Bank[i].Packages = stage12CopyPackages(row.Packages)
	}
	for key, rows := range p.Aliases {
		out.Aliases[key] = append([]string(nil), rows...)
		sort.Strings(out.Aliases[key])
	}
	for key, rows := range p.Unavailable {
		out.Unavailable[key] = append([]string(nil), rows...)
		sort.Strings(out.Unavailable[key])
	}
	for key, value := range p.Visited {
		out.Visited[key] = value
	}
	for key, value := range p.Refined {
		out.Refined[key] = value
	}
	return out
}

// Strip a frame digest only after an existing program/context identity. In
// particular program:<digest> and context:<key> themselves are never stripped.
func stage12NormalizedFamily(family string) string {
	if !strings.HasPrefix(family, "program:") && !strings.HasPrefix(family, "context:") {
		return family
	}
	at := strings.LastIndexByte(family, ':')
	if at < 0 || family[:at] == "program" || family[:at] == "context" || len(family[at+1:]) != 64 {
		return family
	}
	for _, c := range family[at+1:] {
		if !(c >= '0' && c <= '9') && !(c >= 'a' && c <= 'f') {
			return family
		}
	}
	return family[:at]
}

func stage12NormalizeActual(p theorysearch.ParityPhase) (theorysearch.ParityPhase, string) {
	out := stage12CopyPhase(p)
	for i := range out.Pool {
		out.Pool[i].Family = stage12NormalizedFamily(out.Pool[i].Family)
	}
	for i := range out.Bank {
		out.Bank[i].Family = stage12NormalizedFamily(out.Bank[i].Family)
	}
	out.Aliases = map[string][]string{}
	for _, raw := range stage12Keys(p.Aliases) {
		key := stage12NormalizedFamily(raw)
		if _, exists := out.Aliases[key]; exists {
			return out, "aliases: ambiguous normalized family " + stage12Short(key)
		}
		out.Aliases[key] = append([]string(nil), p.Aliases[raw]...)
		sort.Strings(out.Aliases[key])
	}
	out.Refined = map[string]int{}
	for _, raw := range stage12Keys(p.Refined) {
		key := stage12NormalizedFamily(raw)
		if _, exists := out.Refined[key]; exists {
			return out, "refined: ambiguous normalized family " + stage12Short(key)
		}
		out.Refined[key] = p.Refined[raw]
	}
	for key, family := range out.Visited {
		out.Visited[key] = stage12NormalizedFamily(family)
	}
	return out, ""
}

func stage12PhaseDifference(actual, expected theorysearch.ParityPhase, routeA, routeB []string, ignoreDeepBundles bool) string {
	a, difference := stage12NormalizeActual(actual)
	if difference != "" {
		return difference
	}
	b := stage12CopyPhase(expected)
	for _, rows := range []struct {
		name             string
		actual, expected []theorysearch.ParityCandidate
	}{
		{"pool", a.Pool, b.Pool}, {"bank", a.Bank, b.Bank},
	} {
		if len(rows.actual) != len(rows.expected) {
			return fmt.Sprintf("%s count: actual=%d reference=%d", rows.name, len(rows.actual), len(rows.expected))
		}
		for i := range rows.actual {
			if difference := stage12CandidateDifference(rows.actual[i], rows.expected[i]); difference != "" {
				return fmt.Sprintf("%s[%d] %s", rows.name, i, difference)
			}
		}
	}
	for _, key := range stage12UnionKeys(a.Aliases, b.Aliases) {
		ar, aok := a.Aliases[key]
		br, bok := b.Aliases[key]
		if aok != bok {
			return "aliases family presence: " + stage12Short(key)
		}
		if len(ar) != len(br) {
			return fmt.Sprintf("aliases[%s] count: actual=%d reference=%d", stage12Short(key), len(ar), len(br))
		}
		for i := range ar {
			if ar[i] != br[i] {
				return fmt.Sprintf("aliases[%s][%d]: actual=%s reference=%s", stage12Short(key), i, stage12Short(ar[i]), stage12Short(br[i]))
			}
		}
	}
	for _, key := range stage12UnionKeys(a.Visited, b.Visited) {
		av, aok := a.Visited[key]
		bv, bok := b.Visited[key]
		if aok != bok || av != bv {
			return fmt.Sprintf("visited[%s]: actual=%s (%t) reference=%s (%t)", stage12Short(key), stage12Short(av), aok, stage12Short(bv), bok)
		}
	}
	for _, key := range stage12UnionKeys(a.Unavailable, b.Unavailable) {
		ar, aok := a.Unavailable[key]
		br, bok := b.Unavailable[key]
		if aok != bok {
			return "unavailable tuple presence: " + stage12Short(key)
		}
		if len(ar) != len(br) {
			return fmt.Sprintf("unavailable[%s] reason count: actual=%d reference=%d", stage12Short(key), len(ar), len(br))
		}
		for i := range ar {
			if ar[i] != br[i] {
				return fmt.Sprintf("unavailable[%s][%d]: actual=%s reference=%s", stage12Short(key), i, stage12Short(ar[i]), stage12Short(br[i]))
			}
		}
	}
	for _, key := range stage12UnionKeys(a.Refined, b.Refined) {
		av, aok := a.Refined[key]
		bv, bok := b.Refined[key]
		if aok != bok || av != bv {
			return fmt.Sprintf("refined[%s]: actual=%d (%t) reference=%d (%t)", stage12Short(key), av, aok, bv, bok)
		}
	}
	for _, count := range []struct {
		name             string
		actual, expected int
	}{
		{"Formula", a.Work.Formula, b.Work.Formula}, {"Gradient", a.Work.Gradient, b.Work.Gradient},
		{"AllocationAttempts", a.Work.AllocationAttempts, b.Work.AllocationAttempts}, {"AliasHits", a.Work.AliasHits, b.Work.AliasHits},
		{"CompletedSweeps", a.Work.CompletedSweeps, b.Work.CompletedSweeps}, {"IndependentStarts", a.Work.IndependentStarts, b.Work.IndependentStarts},
		{"TransferredStarts", a.Work.TransferredStarts, b.Work.TransferredStarts}, {"CompletedPasses", a.Work.CompletedPasses, b.Work.CompletedPasses},
	} {
		if count.actual != count.expected {
			return fmt.Sprintf("work.%s: actual=%d reference=%d", count.name, count.actual, count.expected)
		}
	}
	if !ignoreDeepBundles && a.Work.DeepBundles != b.Work.DeepBundles {
		return fmt.Sprintf("work.DeepBundles: actual=%d reference=%d", a.Work.DeepBundles, b.Work.DeepBundles)
	}
	if routeA != nil && routeB != nil {
		if len(routeA) != len(routeB) {
			return fmt.Sprintf("route count: actual=%d reference=%d", len(routeA), len(routeB))
		}
		for i := range routeA {
			if routeA[i] != routeB[i] {
				return fmt.Sprintf("route[%d]: actual=%s reference=%s", i, stage12Short(routeA[i]), stage12Short(routeB[i]))
			}
		}
	}
	return ""
}

func stage12CandidateDifference(a, b theorysearch.ParityCandidate) string {
	if err := alloc.ValidateFull45(a.State); err != nil {
		return "actual witness is not legal full45: " + stage12Short(err.Error())
	}
	if err := alloc.ValidateFull45(b.State); err != nil {
		return "reference witness is not legal full45: " + stage12Short(err.Error())
	}
	if keyA, keyB := theoryteams.Key(a.Packages), theoryteams.Key(b.Packages); keyA != keyB {
		return "tuple: actual=" + stage12Short(keyA) + " reference=" + stage12Short(keyB)
	}
	if a.Family != b.Family {
		return "family: actual=" + stage12Short(a.Family) + " reference=" + stage12Short(b.Family)
	}
	if math.IsNaN(a.Value) || math.IsInf(a.Value, 0) || math.IsNaN(b.Value) || math.IsInf(b.Value, 0) {
		return "nonfinite score"
	}
	if math.Float64bits(a.Value) != math.Float64bits(b.Value) {
		return fmt.Sprintf("score bits: actual=%016x reference=%016x", math.Float64bits(a.Value), math.Float64bits(b.Value))
	}
	for actor := range a.State.Mains {
		for slot := range a.State.Mains[actor] {
			if a.State.Mains[actor][slot] != b.State.Mains[actor][slot] {
				return fmt.Sprintf("main[%d][%d]: actual=%s reference=%s", actor, slot, stage12Short(a.State.Mains[actor][slot]), stage12Short(b.State.Mains[actor][slot]))
			}
			for line := range a.State.Lines[actor][slot] {
				if a.State.Lines[actor][slot][line] != b.State.Lines[actor][slot][line] {
					return fmt.Sprintf("line[%d][%d][%d]: actual=%d reference=%d", actor, slot, line, a.State.Lines[actor][slot][line], b.State.Lines[actor][slot][line])
				}
				av, bv := a.State.Upgrades[actor][slot][line], b.State.Upgrades[actor][slot][line]
				if math.Float64bits(av) != math.Float64bits(bv) {
					return fmt.Sprintf("upgrade[%d][%d][%d] bits: actual=%016x reference=%016x", actor, slot, line, math.Float64bits(av), math.Float64bits(bv))
				}
			}
		}
	}
	return ""
}

func stage12Keys[V any](m map[string]V) []string {
	keys := make([]string, 0, len(m))
	for key := range m {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func stage12UnionKeys[V any](a, b map[string]V) []string {
	keys := map[string]bool{}
	for key := range a {
		keys[key] = true
	}
	for key := range b {
		keys[key] = true
	}
	return stage12Keys(keys)
}

func stage12Short(value string) string {
	const limit = 120
	if len(value) > limit {
		return value[:limit] + "…"
	}
	return value
}

func stage12AliasCount(aliases map[string][]string) int {
	n := 0
	for _, rows := range aliases {
		n += len(rows)
	}
	return n
}

func stage12Fingerprint(t *testing.T, value any) string {
	t.Helper()
	raw, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(raw)
	return fmt.Sprintf("%x", sum)
}

func stage12ComparisonFixture() theorysearch.ParityPhase {
	mains := [4][5]string{}
	var packages [4]domain.Package
	for a := range mains {
		mains[a] = [5]string{"hp", "atk", "em", "em", "em"}
		packages[a] = domain.Package{Sets: []contracts.SetRequirement{{SetUID: fmt.Sprintf("fixture-%d", a), Count: 4}}}
	}
	state := alloc.Seed(mains, [4][10]float64{}, 0, 45)
	first := theorysearch.ParityCandidate{Packages: packages, State: state, Value: 100, Family: "program:" + strings.Repeat("a", 64)}
	second := first
	second.Packages = stage12CopyPackages(packages)
	second.Packages[0].Sets[0].SetUID = "other-fixture"
	second.Value = 98
	second.Family = "context:" + strings.Repeat("b", 64)
	return theorysearch.ParityPhase{Pool: []theorysearch.ParityCandidate{first, second}, Bank: []theorysearch.ParityCandidate{second, first},
		Aliases:     map[string][]string{first.Family: {"choice-b", "choice-a"}, second.Family: {"choice-c"}},
		Unavailable: map[string][]string{"choice-unavailable": {"missing_fixture_rule"}},
		Visited:     map[string]string{"choice-a": first.Family, "choice-b": first.Family, "choice-c": second.Family, "choice-unavailable": ""},
		Refined:     map[string]int{first.Family: 2, second.Family: 1},
		Work: theorysearch.Work{Formula: 17, Gradient: 11, AllocationAttempts: 6, AliasHits: 2, CompletedSweeps: 8,
			IndependentStarts: 5, TransferredStarts: 1, CompletedPasses: 1, DeepBundles: 1}}
}

func TestStage12ReferencePhaseOwnsCandidatePackagesAndMaps(t *testing.T) {
	p := stage12ComparisonFixture()
	c := p.Pool[0]
	ref := feasibleCandidate{packages: c.Packages, state: proto.State{Mains: c.State.Mains, Lines: c.State.Lines, Upgrades: c.State.Upgrades}, value: c.Value, family: c.Family}
	h := &hybridRun{w: &r2World{feasibleWorld: &feasibleWorld{work: feasibleWork{Formula: 17, Gradient: 11, AllocationAttempts: 6}}},
		pool: map[string]feasibleCandidate{c.Family: ref}, bank: []feasibleCandidate{ref}, aliases: map[string]map[string]bool{c.Family: {"choice-b": true, "choice-a": true}},
		visited: map[string]string{"choice-a": c.Family, "choice-unavailable": ""}, refined: map[string]int{c.Family: 2}, aliasHits: 2, fullSweeps: 8,
		independent: 5, transferred: 1, completedPasses: 1, refinedPasses: 1}
	h.w.metadata = map[string][]string{"choice-unavailable": {"rule-z", "rule-a"}}
	phase := referencePhase(h)
	before := stage12Fingerprint(t, phase)
	h.bank[0].packages[0].Sets[0].SetUID = "mutated-input"
	h.aliases[c.Family]["added-choice"] = true
	h.visited["choice-a"] = "mutated-family"
	h.refined[c.Family] = 0
	h.w.work.Formula++
	h.w.metadata["choice-unavailable"][0] = "mutated-rule"
	if stage12Fingerprint(t, phase) != before {
		t.Fatal("reference adapter retained mutable input packages/maps")
	}
	phase.Pool[0].Packages[0].Sets[0].SetUID = "mutated-output"
	if h.bank[0].packages[0].Sets[0].SetUID != "mutated-input" {
		t.Fatal("reference output package mutation reached the research harness")
	}
}

func TestStage12ComparisonRejectsNumericalStateMapBankAndCounterMutations(t *testing.T) {
	expected := stage12ComparisonFixture()
	if difference := stage12PhaseDifference(stage12CopyPhase(expected), expected, nil, nil, false); difference != "" {
		t.Fatal(difference)
	}
	mutations := []struct {
		name   string
		change func(*theorysearch.ParityPhase)
	}{
		{"score-bit", func(p *theorysearch.ParityPhase) { p.Pool[0].Value = math.Nextafter(p.Pool[0].Value, math.Inf(1)) }},
		{"legal-slot-state", func(p *theorysearch.ParityPhase) {
			p.Pool[0].State.Upgrades[0][0][0] += .25
			p.Pool[0].State.Upgrades[0][0][1] -= .25
		}},
		{"illegal-45", func(p *theorysearch.ParityPhase) { p.Pool[0].State.Upgrades[0][0][0] -= .25 }},
		{"tuple", func(p *theorysearch.ParityPhase) { p.Pool[0].Packages[0].Sets[0].SetUID = "different-tuple" }},
		{"family", func(p *theorysearch.ParityPhase) { p.Pool[0].Family = "different-family" }},
		{"bank-order", func(p *theorysearch.ParityPhase) { p.Bank[0], p.Bank[1] = p.Bank[1], p.Bank[0] }},
		{"aliases", func(p *theorysearch.ParityPhase) {
			p.Aliases[p.Pool[0].Family] = append(p.Aliases[p.Pool[0].Family], "unseen-alias")
		}},
		{"visited", func(p *theorysearch.ParityPhase) { p.Visited["choice-a"] = "different-family" }},
		{"unavailable-reasons", func(p *theorysearch.ParityPhase) { p.Unavailable["choice-unavailable"][0] = "different-rule" }},
		{"refined", func(p *theorysearch.ParityPhase) { p.Refined[p.Pool[0].Family]++ }},
		{"formula", func(p *theorysearch.ParityPhase) { p.Work.Formula++ }},
		{"gradient", func(p *theorysearch.ParityPhase) { p.Work.Gradient++ }},
		{"allocations", func(p *theorysearch.ParityPhase) { p.Work.AllocationAttempts++ }},
		{"alias-hits", func(p *theorysearch.ParityPhase) { p.Work.AliasHits++ }},
		{"sweeps", func(p *theorysearch.ParityPhase) { p.Work.CompletedSweeps++ }},
		{"independent", func(p *theorysearch.ParityPhase) { p.Work.IndependentStarts++ }},
		{"transferred", func(p *theorysearch.ParityPhase) { p.Work.TransferredStarts++ }},
		{"passes", func(p *theorysearch.ParityPhase) { p.Work.CompletedPasses++ }},
	}
	for _, mutation := range mutations {
		t.Run(mutation.name, func(t *testing.T) {
			actual := stage12CopyPhase(expected)
			mutation.change(&actual)
			if difference := stage12PhaseDifference(actual, expected, nil, nil, true); difference == "" {
				t.Fatal("numerical mutation accepted")
			}
		})
	}
	actual := stage12CopyPhase(expected)
	actual.Work.DeepBundles++
	if stage12PhaseDifference(actual, expected, nil, nil, false) == "" || stage12PhaseDifference(actual, expected, nil, nil, true) != "" {
		t.Fatal("DeepBundles boundary override widened or failed its single-counter scope")
	}
	if stage12PhaseDifference(expected, expected, []string{"first", "second"}, []string{"first", "changed"}, false) == "" {
		t.Fatal("changed ordered route accepted")
	}
}

func TestStage12FamilyFrameNormalizationRetainsOriginalIdentities(t *testing.T) {
	program := "program:" + strings.Repeat("a", 64)
	context := "context:" + strings.Repeat("b", 64)
	frame := strings.Repeat("c", 64)
	for _, identity := range []string{program, context, "context:source-key"} {
		if stage12NormalizedFamily(identity) != identity || stage12NormalizedFamily(identity+":"+frame) != identity {
			t.Fatalf("frame normalization changed original identity: %s", identity)
		}
	}
	for _, value := range []string{program + ":" + strings.Repeat("C", 64), program + ":short", "other:" + frame} {
		if stage12NormalizedFamily(value) != value {
			t.Fatal("normalization stripped a non-frame suffix")
		}
	}
	expected := stage12ComparisonFixture()
	actual := stage12CopyPhase(expected)
	for i := range actual.Pool {
		actual.Pool[i].Family += ":" + frame
	}
	for i := range actual.Bank {
		actual.Bank[i].Family += ":" + frame
	}
	actual.Aliases = map[string][]string{}
	for family, rows := range expected.Aliases {
		actual.Aliases[family+":"+frame] = append([]string(nil), rows...)
	}
	actual.Refined = map[string]int{}
	for family, level := range expected.Refined {
		actual.Refined[family+":"+frame] = level
	}
	for key, family := range actual.Visited {
		if family != "" {
			actual.Visited[key] = family + ":" + frame
		}
	}
	if difference := stage12PhaseDifference(actual, expected, nil, nil, false); difference != "" {
		t.Fatal(difference)
	}
}
