package main

import (
	"context"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

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
