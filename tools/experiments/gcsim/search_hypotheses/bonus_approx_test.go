package seteffects

import (
	"encoding/json"
	"math"
	"os"
	"sort"
	"testing"
)

const hypothesisLiteralFixture = `package arbitrary
import (
 a "github.com/genshinsim/gcsim/pkg/core/attributes"
 ch "github.com/genshinsim/gcsim/pkg/core/player/character"
 mod "github.com/genshinsim/gcsim/pkg/modifier"
)
func NewSet(c *Core, wearer *ch.CharWrapper, copies int) (*Set,error) {
 s:=Set{Count:copies}
 if copies >= 2 {
  vec:=make([]float64,a.EndStatType)
  vec[a.ER]=(.1+.05)*2
  wearer.AddStatMod(ch.StatMod{Base:mod.NewBase("arbitrary",-1),AffectedStat:a.ER,Amount:func()[]float64{return vec}})
 }
 if copies >= 4 { c.Events.Subscribe(5,func(){ s.stack++ },"arbitrary") }
 return &s,nil
}`

func TestHypothesisLiteral2PRestrictedSource(t *testing.T) {
	stats := map[string]string{"github.com/genshinsim/gcsim/pkg/core/attributes.ER": "er"}
	hint, ok := hypothesisExtractLiteral2P(map[string][]byte{"set.go": []byte(hypothesisLiteralFixture)}, stats)
	if !ok || math.Abs(hint["energy_recharge"]-.3) > 1e-12 || len(hint) != 1 {
		t.Fatalf("literal hint: %v %v", hint, ok)
	}
	c := &SourceCatalog{hypothesisLiteral2P: map[string]map[string]float64{"arbitrary": hint}}
	copy, ok := c.HypothesisLiteral2P("arbitrary")
	if !ok {
		t.Fatal("missing copy")
	}
	copy["energy_recharge"] = 50
	again, _ := c.HypothesisLiteral2P("arbitrary")
	if math.Abs(again["energy_recharge"]-.3) > 1e-12 {
		t.Fatal("caller mutated hint")
	}
	if _, ok := c.HypothesisLiteral2P("missing"); ok {
		t.Fatal("unknown must not become zero")
	}
}

func TestHypothesisLiteral2PRejectsDynamicAndExtraEffects(t *testing.T) {
	stats := map[string]string{"github.com/genshinsim/gcsim/pkg/core/attributes.ER": "er"}
	for _, source := range []string{
		// A value dependent on a current owner stat is not a literal.
		replaceHypothesisFixture("vec[a.ER]=(.1+.05)*2", "vec[a.ER]=wearer.NonExtraStat(a.ER)*.25"),
		// A second registration in the two-piece body is not a complete hint.
		replaceHypothesisFixture("wearer.AddStatMod(ch.StatMod{Base:mod.NewBase(\"arbitrary\",-1),AffectedStat:a.ER,Amount:func()[]float64{return vec}})", "wearer.AddAttackMod(ch.AttackMod{})"),
		// An unrelated count-two branch could change the owner.
		replaceHypothesisFixture("return &s,nil", "if copies >= 2 { c.SomeHelper() }; return &s,nil"),
		// Mutable captured vector after registration is not a stable literal.
		replaceHypothesisFixture("\n }\n if copies >= 4", "\n  vec[a.ER]=.9\n }\n if copies >= 4"),
	} {
		if hint, ok := hypothesisExtractLiteral2P(map[string][]byte{"set.go": []byte(source)}, stats); ok {
			t.Fatalf("unsupported shape classified: %v", hint)
		}
	}
}

func replaceHypothesisFixture(before, after string) string {
	return stringReplaceOnce(hypothesisLiteralFixture, before, after)
}

func stringReplaceOnce(source, before, after string) string {
	i := -1
	for at := 0; at+len(before) <= len(source); at++ {
		if source[at:at+len(before)] == before {
			i = at
			break
		}
	}
	if i < 0 {
		panic("fixture marker absent")
	}
	return source[:i] + after + source[i+len(before):]
}

// Opt-in coverage audit reads the active saved source envelope; it never
// invokes gcsim, a capture, or an optimizer run.
func TestHypothesisActiveSourceLiteralCoverage(t *testing.T) {
	path := os.Getenv("GTT_RULE_SOURCE_BUNDLE")
	if path == "" {
		t.Skip("active source bundle not selected")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var bundle SourceBundle
	if err := json.Unmarshal(data, &bundle); err != nil {
		t.Fatal(err)
	}
	stats, err := StatVocabulary([]byte(bundle.StatSource.Text))
	if err != nil {
		t.Fatal(err)
	}
	known := []string{}
	for _, item := range bundle.Items {
		sources := map[string][]byte{}
		for name, source := range item.Sources {
			sources[name] = []byte(source.Text)
		}
		if _, ok := hypothesisExtractLiteral2P(sources, stats); ok {
			known = append(known, item.Key)
		}
	}
	sort.Strings(known)
	t.Logf("restricted literal two-piece coverage: %d/%d source sets: %v", len(known), len(bundle.Items), known)
}
