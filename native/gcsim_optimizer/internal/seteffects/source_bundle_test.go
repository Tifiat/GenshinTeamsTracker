package seteffects

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
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
