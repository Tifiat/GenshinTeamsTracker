package seteffects

import (
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

const hypothesisFastFixture = `package arbitrary
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
}
func (s *Set) Init() error { return nil }
`

func TestHypothesisFastLiteralMetadataIsStrict(t *testing.T) {
	stats := map[string]string{"github.com/genshinsim/gcsim/pkg/core/attributes.ER": "er"}
	mods, ok := hypothesisExtractFastLiteral2P(map[string][]byte{"set.go": []byte(hypothesisFastFixture)}, stats)
	if !ok || len(mods) != 1 || mods[0].key != "arbitrary" || mods[0].stat != "er" || math.Abs(mods[0].value-.3) > 1e-12 {
		t.Fatalf("fast metadata: %v %v", mods, ok)
	}
	for _, source := range []string{
		strings.Replace(hypothesisFastFixture, "mod.NewBase(\"arbitrary\",-1)", "mod.NewBase(\"arbitrary\",300)", 1),
		strings.Replace(hypothesisFastFixture, "AffectedStat:a.ER,Amount:", "AffectedStat:a.ER,Extra:true,Amount:", 1),
		strings.Replace(hypothesisFastFixture, "AffectedStat:a.ER,Amount:", "AffectedStat:a.ER,Extra:false,Extra:false,Amount:", 1),
		strings.Replace(hypothesisFastFixture, "func (s *Set) Init() error { return nil }", "func (s *Set) Init() error { s.activate(); return nil }", 1),
		strings.Replace(hypothesisFastFixture, "wearer.AddStatMod(ch.StatMod", "c.AddStatMod(ch.StatMod", 1),
		strings.Replace(hypothesisFastFixture, "s:=Set{Count:copies}", "s:=Set{Count:copies}; wearer=other", 1),
		strings.Replace(hypothesisFastFixture, "s:=Set{Count:copies}", "s:=Set{Count:copies}; s.stack=2", 1),
	} {
		if got, ok := hypothesisExtractFastLiteral2P(map[string][]byte{"set.go": []byte(source)}, stats); ok {
			t.Fatalf("unsupported source got fast metadata: %v", got)
		}
	}
}

func TestHypothesisFastLiteralSavedPortsMatchReplay(t *testing.T) {
	run := os.Getenv("GTT_HYPOTHESIS_SAVED")
	if run == "" || os.Getenv("GTT_RULE_SOURCE_BUNDLE") == "" {
		t.Skip("managed saved neutral/source inputs required")
	}
	c := activeRuleCatalog(t)
	paths, err := filepath.Glob(filepath.Join(run, "verification", "contexts", "context-*", "seed-*", "member.json.effects.json"))
	if err != nil {
		t.Fatal(err)
	}
	var sidecars []contracts.EffectInputsOutput
	for _, path := range paths {
		data, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		var sidecar contracts.EffectInputsOutput
		if err := json.Unmarshal(data, &sidecar); err != nil {
			t.Fatal(err)
		}
		if sidecar.Neutral != nil && sidecar.Neutral.Context.NoSets {
			sidecars = append(sidecars, sidecar)
		}
	}
	if len(sidecars) == 0 {
		t.Fatal("saved neutral members absent")
	}
	b, err := NewNeutralBinding(c, sidecars)
	if err != nil {
		t.Fatal(err)
	}
	checks := 0
	for _, set := range c.Sets {
		if len(c.hypothesisFast2P[set.Key]) == 0 {
			continue
		}
		for owner := range sidecars[0].Neutral.Context.Characters {
			choice := RuleChoice{Owner: owner, Key: set.Key, Pieces: 2}
			got, fast := b.hypothesisFastLiteralChoice(choice)
			if !fast {
				continue
			}
			want := b.compilePackagesJoint([]RuleChoice{choice})
			if !reflect.DeepEqual(got.Boundaries, want.Boundaries) || !reflect.DeepEqual(got.Uncertainty, want.Uncertainty) || !reflect.DeepEqual(got.footprint, want.footprint) || len(got.Effects) != len(want.Effects) {
				t.Fatalf("%v metadata differs: got=%+v want=%+v", choice, got, want)
			}
			for key, actual := range got.Effects {
				expected := want.Effects[key]
				if expected == nil || actual.Operation != "constant" || expected.Operation != "constant" || math.Float64bits(actual.Value) != math.Float64bits(expected.Value) {
					t.Fatalf("%v %s port differs: %v / %v", choice, key, actual, expected)
				}
			}
			checks++
			if checks >= 8 {
				break
			}
		}
		if checks >= 8 {
			break
		}
	}
	if checks == 0 {
		t.Fatal("no saved fast-eligible literal 2p ports")
	}
	t.Logf("direct literal 2p vs ordinary replay: %d choices, every retained port bit-identical", checks)
}
