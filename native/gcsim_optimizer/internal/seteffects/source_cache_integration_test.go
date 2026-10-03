package seteffects

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

// Actual active-engine rule source; synthetic event tapes, zero simulations.
// Shared syntax must never share mutable activation or team state.
func TestRuleCacheCatalogWarmColdAndSeparateTeamEvents(t *testing.T) {
	name := os.Getenv("GTT_RULE_SOURCE_BUNDLE")
	if name == "" {
		t.Skip("managed active-source envelope not supplied")
	}
	data, err := os.ReadFile(name)
	if err != nil {
		t.Fatal(err)
	}
	var b SourceBundle
	if err := json.Unmarshal(data, &b); err != nil {
		t.Fatal(err)
	}
	e := contracts.EngineBinding{ArtifactSHA256: b.EngineSHA256, SourceManifestSHA256: b.SourceManifestSHA256}
	dir := t.TempDir()
	compile := func(cache *RuleParseCache, items []contracts.Artifact, filter bool) *SourceCatalog {
		t.Helper()
		c, err := CompileSourceBundleCached(b, e, b.CatalogSHA256, items, filter, cache)
		if err != nil {
			t.Fatal(err)
		}
		return c
	}
	cold := compile(NewRuleParseCache("", dir), nil, false)
	if cold.ParseCache.Writes == 0 || cold.ParseCache.Errors != 0 {
		t.Fatal(cold.ParseCache)
	}
	files, err := filepath.Glob(filepath.Join(dir, "*.gttast"))
	if err != nil {
		t.Fatal(err)
	}
	warm := compile(NewRuleParseCache(dir, t.TempDir()), nil, false)
	if warm.ParseCache.BundledHits == 0 || warm.ParseCache.Misses != 0 || warm.ParseCache.Errors != 0 {
		t.Fatal(warm.ParseCache)
	}
	items := []contracts.Artifact{{SetUID: "tenacityofthemillelith", Slot: "flower"}, {SetUID: "tenacityofthemillelith", Slot: "plume"}}
	neutralOnly := compile(NewRuleParseCache(dir, t.TempDir()), items, true)
	if neutralOnly.LegacyPrepared || !warm.LegacyPrepared || !neutralOnly.HasNeutralRules() {
		t.Fatal("neutral inventory must not prepare legacy recipes; audits must retain them")
	}
	for _, row := range neutralOnly.Sets {
		if len(row.Recipes) != 0 || len(row.Description.Functions) != 0 {
			t.Fatal("unused legacy discovery ran on neutral inventory", row.Key)
		}
	}
	for _, c := range []*SourceCatalog{cold, warm, neutralOnly} {
		for _, active := range []bool{true, false, true, false} {
			n := ruleTestNeutral()
			if active {
				n.Ledger.Events = []contracts.CombatEvent{ruleTestEvent(
					int(ruleTestConstant(t, c, "pkg/core/event", "OnEnemyDamage")), 0,
					ruleTestConstant(t, c, "pkg/core/attacks", "AttackTagElementalArt"),
					ruleTestConstant(t, c, "pkg/core/attributes", "Hydro"), 1)}
			}
			q := RuleQuery{Order: 20, Frame: 11, Active: 1, Owner: 1, Kind: "stat", Mode: "stat", Stat: "atk%"}
			r := c.ReplayNeutralRules(n, []RuleChoice{{0, "tenacityofthemillelith", 4}}, []RuleQuery{q})
			want := 0.0
			if active {
				want = .2
			}
			if r.Boundary != "" || len(r.Values) != 1 || !r.Values[0].Known || r.Values[0].Value != want {
				t.Fatal(active, r)
			}
		}
	}
	// A different account cannot evict all catalog entries just because it has
	// only one assemblable set. Skipped artifacts remain eligible as off-pieces.
	compile(NewRuleParseCache("", dir), []contracts.Artifact{{SetUID: "tenacityofthemillelith", Slot: "flower"}, {SetUID: "tenacityofthemillelith", Slot: "plume"}}, true)
	legacyBundle := b
	legacyBundle.RuleLibraries = nil
	legacy, err := CompileSourceBundleCached(legacyBundle, e, b.CatalogSHA256, nil, false, NewRuleParseCache("", dir))
	if err != nil || !legacy.LegacyPrepared || legacy.ParseCache.Writes != 0 {
		t.Fatal("legacy-only mode must not populate or remove the neutral rule cache", err)
	}
	for _, file := range files {
		if _, err := os.Stat(file); err != nil {
			t.Fatal("another account evicted live source", file, err)
		}
	}
}
