package main

import (
	"context"
	"encoding/json"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

func TestAllSetsNeutralRouteRequiresObserverRulesAndInfiniteEnergy(t *testing.T) {
	for _, tc := range []struct {
		name, options                  string
		observer, rules, want, wantErr bool
	}{
		{"neutral", "ignore_burst_energy=true", true, true, true, false},
		{"old active", "ignore_burst_energy=true", false, false, false, false},
		{"finite unchanged", "ignore_burst_energy=false", true, false, false, false},
		{"missing libraries", "ignore_burst_energy=true", true, false, false, true},
		{"missing energy", "iteration=1", true, true, false, true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var req contracts.OptimizerRequest
			req.Context.PreparedConfig.Text = "options " + tc.options + ";\n"
			if tc.observer {
				req.Engine.Capabilities = []string{contracts.NeutralInputsCapability}
			}
			got, err := useNeutralAllSets(req, tc.rules)
			if got != tc.want || (err != nil) != tc.wantErr {
				t.Fatal(got, err)
			}
		})
	}
}

// This pins the orchestration policy itself without paying for a product run:
// the All Sets entrypoint has exactly one ordinary measurement call, not a
// hidden screen plus another verifier. Numerical verifier tests live with it.
func TestAllSetsEntrypointHasOneCommonFidelityMeasurement(t *testing.T) {
	f, err := parser.ParseFile(token.NewFileSet(), "all_sets.go", nil, 0)
	if err != nil {
		t.Fatal(err)
	}
	calls := 0
	ast.Inspect(f, func(n ast.Node) bool {
		call, ok := n.(*ast.CallExpr)
		if !ok {
			return true
		}
		selector, ok := call.Fun.(*ast.SelectorExpr)
		if !ok {
			return true
		}
		owner, ok := selector.X.(*ast.Ident)
		if !ok || owner.Name != "finalists" || !strings.HasPrefix(selector.Sel.Name, "Verify") {
			return true
		}
		calls++
		if selector.Sel.Name != "VerifyDynamicWavesWithRenderer" || len(call.Args) != 8 {
			t.Fatal("unexpected extra/adaptive verification", selector.Sel.Name)
		}
		iterations, ok := call.Args[5].(*ast.BasicLit)
		if !ok || iterations.Value != "500" {
			t.Fatal("All Sets common fidelity changed")
		}
		return true
	})
	if calls != 1 {
		t.Fatal("All Sets must have one finalist measurement stage", calls)
	}
}

func TestSetSourceAuditSummarizesRecipesWithoutGameplayExecution(t *testing.T) {
	sources := &seteffects.SourceCatalog{Sets: []seteffects.DiscoveredSet{
		{
			Key:              "example",
			FourPieceModeled: true,
			Recipes: []seteffects.Recipe{
				{Effect: seteffects.Effect{Kind: "stat"}, Terms: []seteffects.Term{{}}, Unresolved: []string{"activation"}},
				{Effect: seteffects.Effect{Kind: "reaction_bonus"}, Terms: []seteffects.Term{{}, {}}},
			},
		},
	}}

	rows := summarizeSetSources(sources)

	if len(rows) != 1 || rows[0].Recipes != 2 || rows[0].Terms != 3 || rows[0].UnresolvedRecipes != 1 {
		t.Fatalf("unexpected source audit: %#v", rows)
	}
	if !reflect.DeepEqual(rows[0].EffectKinds, []string{"reaction_bonus", "stat"}) {
		t.Fatalf("effect kinds are not deterministic: %#v", rows[0].EffectKinds)
	}
}

func TestAllSetsCommandRejectsSourceEnvelopeBeforeEngine(t *testing.T) {
	root := filepath.Join("..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1")
	dir := t.TempDir()
	source := filepath.Join(dir, "source.json")
	if e := os.WriteFile(source, []byte(`{"schema_version":1,"untrusted_flag":true}`), 0600); e != nil {
		t.Fatal(e)
	}
	runRoot := filepath.Join(dir, "run")
	e := run(context.Background(), []string{"optimize-all-sets", filepath.Join(root, "request_v1.json"), source, runRoot})
	if e == nil || !strings.Contains(e.Error(), "unknown field") {
		t.Fatal(e)
	}
	if _, e = os.Stat(runRoot); !os.IsNotExist(e) {
		t.Fatal("engine/run mutation before source validation")
	}
}

func TestSourceCatalogCacheWarmingUsesSyntaxOnlyCompiler(t *testing.T) {
	request, _ := productFixtures(t)
	text := func(value string) contracts.SourceText {
		return contracts.SourceText{Text: value, SHA256: contracts.TextSHA256(value)}
	}
	base := text("package baseline\n")
	bundle := seteffects.SourceBundle{
		SchemaVersion: 1, EngineSHA256: request.Engine.ArtifactSHA256,
		SourceManifestSHA256: request.Engine.SourceManifestSHA256,
		CatalogSHA256:        strings.Repeat("c", 64),
		StatSource:           base, AttackSource: base, ElementSource: base, ContextSource: base,
		RuleLibraries: map[string]contracts.SourceText{"pkg/helper.go": text("package helper\nconst Marker = 1\n")},
		Items: []seteffects.SourceItem{
			{Key: "available", Sources: map[string]contracts.SourceText{"internal/artifacts/available/set.go": text("package sample\nfunc NewSet() {}\n")}},
			{Key: "not_owned", Sources: map[string]contracts.SourceText{"internal/artifacts/not_owned/set.go": text("package sample\nfunc NewSet() {}\n")}},
		},
	}
	payload, err := json.Marshal(bundle)
	if err != nil {
		t.Fatal(err)
	}
	sourcePath := filepath.Join(t.TempDir(), "sources.json")
	if err := os.WriteFile(sourcePath, payload, 0o600); err != nil {
		t.Fatal(err)
	}
	warmed, err := readSourceCatalogForCacheWarming(sourcePath, request.Engine, seteffects.NewRuleParseCache("", t.TempDir()))
	if err != nil {
		t.Fatal(err)
	}
	full, err := readSourceCatalogCached(sourcePath, request.Engine, seteffects.NewRuleParseCache("", t.TempDir()))
	if err != nil {
		t.Fatal(err)
	}
	if warmed.LegacyPrepared || !full.LegacyPrepared || len(warmed.Sets) != 2 || len(warmed.ScheduleCaptureMetadata()) != 2 || warmed.ParseCache.Writes == 0 {
		t.Fatalf("warm command failed to retain all source syntax without legacy discovery: warmed=%+v full=%+v", warmed, full)
	}
	if warmed.EngineSHA256 != request.Engine.ArtifactSHA256 || warmed.SourceManifestSHA256 != request.Engine.SourceManifestSHA256 || warmed.CatalogSHA256 != bundle.CatalogSHA256 {
		t.Fatal("warm command lost source identity")
	}
}
