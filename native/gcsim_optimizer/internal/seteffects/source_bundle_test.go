package seteffects

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"reflect"
	"strings"
	"testing"
)

func TestSourceBundleUnknownSyntaxIsLocalButBindingMismatchIsNot(t *testing.T) {
	text := func(s string) contracts.SourceText {
		return contracts.SourceText{Text: s, SHA256: contracts.TextSHA256(s)}
	}
	engine := contracts.EngineBinding{ArtifactSHA256: strings.Repeat("a", 64), SourceManifestSHA256: strings.Repeat("b", 64)}
	unknown := text("package newengine\n")
	b := SourceBundle{SchemaVersion: 1, EngineSHA256: engine.ArtifactSHA256, SourceManifestSHA256: engine.SourceManifestSHA256, CatalogSHA256: strings.Repeat("c", 64),
		StatSource: unknown, AttackSource: unknown, ElementSource: unknown, ContextSource: unknown,
		Items: []SourceItem{{Key: "new_set", Sources: map[string]contracts.SourceText{"set.go": text("package unfinished\nfunc ()")}}}}
	c, e := CompileSourceBundle(b, engine, b.CatalogSHA256)
	if e != nil || len(c.Sets) != 1 || c.Sets[0].Unresolved == "" || len(c.Boundaries) == 0 {
		t.Fatal(c, e)
	}
	b.StatSource.Text += "changed"
	if _, e = CompileSourceBundle(b, engine, b.CatalogSHA256); e == nil {
		t.Fatal("unverified source bytes accepted")
	}
	b.StatSource = unknown
	b.SourceManifestSHA256 = strings.Repeat("d", 64)
	if _, e = CompileSourceBundle(b, engine, b.CatalogSHA256); e == nil {
		t.Fatal("another engine manifest accepted")
	}
}

func TestInventorySourceGateCountsSlotTypesAndStillChecksBytes(t *testing.T) {
	text := func(s string) contracts.SourceText {
		return contracts.SourceText{Text: s, SHA256: contracts.TextSHA256(s)}
	}
	e := contracts.EngineBinding{ArtifactSHA256: strings.Repeat("a", 64), SourceManifestSHA256: strings.Repeat("b", 64)}
	s := text("package unknown\n")
	b := SourceBundle{SchemaVersion: 1, EngineSHA256: e.ArtifactSHA256, SourceManifestSHA256: e.SourceManifestSHA256, CatalogSHA256: strings.Repeat("c", 64), StatSource: s, AttackSource: s, ElementSource: s, ContextSource: s, Items: []SourceItem{{Key: "one_slot", Sources: map[string]contracts.SourceText{"set.go": text("package unfinished\nfunc ()")}}, {Key: "two_slots", Sources: map[string]contracts.SourceText{"set.go": text("package unfinished\nfunc ()")}}}}
	items := []contracts.Artifact{{SetUID: "one_slot", Slot: "flower"}, {SetUID: "one_slot", Slot: "flower"}, {SetUID: "two_slots", Slot: "flower"}, {SetUID: "two_slots", Slot: "plume"}}
	c, err := CompileSourceBundleForInventory(b, e, b.CatalogSHA256, items)
	if err != nil || len(c.Sets) != 2 {
		t.Fatal(c, err)
	}
	if c.Sets[0].RuleUnresolved != "inventory_bonus_unassemblable" || c.Sets[1].Unresolved == "inventory_bonus_unassemblable" || c.Sets[1].Unresolved == "" {
		t.Fatal(c.Sets)
	}
	if len(items) != 4 {
		t.Fatal("source gate changed inventory")
	}
	// Even skipped source is authenticated; the fast path is not a trust bypass.
	b.Items[0].Sources["set.go"] = contracts.SourceText{Text: "changed", SHA256: s.SHA256}
	if _, err = CompileSourceBundleForInventory(b, e, b.CatalogSHA256, items); err == nil {
		t.Fatal("skipped corrupted source accepted")
	}
}

func TestCacheWarmingCompilesEverySetWithoutLegacyDescriptions(t *testing.T) {
	text := func(s string) contracts.SourceText {
		return contracts.SourceText{Text: s, SHA256: contracts.TextSHA256(s)}
	}
	engine := contracts.EngineBinding{
		ArtifactSHA256: strings.Repeat("a", 64), SourceManifestSHA256: strings.Repeat("b", 64),
	}
	setSource := text(`package sample
type Set struct { count int }
type Core struct{}
func NewSet(a, b, count int) (*Set, error) {
	set := &Set{count: count}
	if count < 4 { return set, nil }
	var core *Core
	core.QueueAttack(1)
	return set, nil
}
func (set *Set) Init() error { return nil }
`)
	baseSource := text("package baseline\n")
	bundle := SourceBundle{
		SchemaVersion: 1, EngineSHA256: engine.ArtifactSHA256,
		SourceManifestSHA256: engine.SourceManifestSHA256, CatalogSHA256: strings.Repeat("c", 64),
		StatSource: baseSource, AttackSource: baseSource, ElementSource: baseSource, ContextSource: baseSource,
		RuleLibraries: map[string]contracts.SourceText{"pkg/helper.go": text("package helper\nconst Marker = 1\n")},
		Items: []SourceItem{
			{Key: "owned", Sources: map[string]contracts.SourceText{"internal/artifacts/owned/set.go": setSource}},
			{Key: "absent_from_inventory", Sources: map[string]contracts.SourceText{"internal/artifacts/absent/set.go": setSource}},
		},
	}
	warmed, err := CompileSourceBundleForCacheWarming(bundle, engine, bundle.CatalogSHA256, NewRuleParseCache("", t.TempDir()))
	if err != nil {
		t.Fatal(err)
	}
	full, err := CompileSourceBundleCached(bundle, engine, bundle.CatalogSHA256, nil, false, NewRuleParseCache("", t.TempDir()))
	if err != nil {
		t.Fatal(err)
	}
	if warmed.LegacyPrepared || !full.LegacyPrepared || !warmed.HasNeutralRules() || len(warmed.Sets) != 2 || warmed.ParseCache.Writes == 0 {
		t.Fatalf("cache warming omitted rules or prepared legacy discovery: warmed=%+v full=%+v", warmed, full)
	}
	if warmed.EngineSHA256 != full.EngineSHA256 || warmed.SourceManifestSHA256 != full.SourceManifestSHA256 || warmed.CatalogSHA256 != full.CatalogSHA256 {
		t.Fatal("cache warming changed source identity")
	}
	for index, set := range warmed.Sets {
		if set.Key != full.Sets[index].Key || set.rule == nil || set.RuleUnresolved != "" || len(set.Description.Functions) != 0 || len(set.Recipes) != 0 || len(full.Sets[index].Description.Functions) == 0 {
			t.Fatalf("set %q lost syntax or prepared legacy description: warmed=%+v full=%+v", set.Key, set, full.Sets[index])
		}
	}
	warmMetadata := warmed.ScheduleCaptureMetadata()
	fullMetadata := full.ScheduleCaptureMetadata()
	if !reflect.DeepEqual(warmMetadata, fullMetadata) || len(warmMetadata) != 2 {
		t.Fatalf("cache warming changed source schedule metadata: warm=%+v full=%+v", warmMetadata, fullMetadata)
	}
	for _, row := range warmMetadata {
		if len(row.Tiers) != 2 || !row.Tiers[0].AnalysisComplete || !row.Tiers[1].AnalysisComplete || !row.Tiers[1].Potential {
			t.Fatalf("source schedule metadata was not retained for %q: %+v", row.SetUID, row)
		}
	}
}
