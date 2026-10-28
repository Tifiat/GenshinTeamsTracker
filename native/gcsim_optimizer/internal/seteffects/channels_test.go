package seteffects

import (
	"strings"
	"testing"
)

const filterFixture = `package invented
import (
 a "github.com/genshinsim/gcsim/pkg/core/attacks"
 i "github.com/genshinsim/gcsim/pkg/core/info"
)
func NewSet(c *Core, owner *Character,count int)*Set {
 owner.AddReactBonusMod(Mod{Amount:func(hit i.AttackInfo)float64{
  switch hit.AttackTag {
   case a.First:
   case a.Second:return .1
   default:return 0
  }
  return .4
 }})
 return &Set{}
}`

func TestFilterReadsEngineTagsAndPreservesEmptyCaseMeaning(t *testing.T) {
	v, err := AttackTagVocabulary([]byte(`package attacks;type AttackTag int;const(None AttackTag=iota;First;Second;UnseenFutureMechanic)`))
	if err != nil {
		t.Fatal(err)
	}
	d, err := Discover(map[string][]byte{"a.go": []byte(filterFixture)})
	if err != nil {
		t.Fatal(err)
	}
	terms := d.Recipes()[0].Terms
	if len(terms) != 3 {
		t.Fatal(terms)
	}
	for _, term := range terms {
		want := map[string]string{"1/10": "tag/2", "0": "tag/3", "2/5": "tag/1"}[term.Constant]
		if want == "" {
			t.Fatal(term)
		}
		for _, tag := range []string{"tag/1", "tag/2", "tag/3"} {
			got := d.TermChannelApplicability(term, tag, v)
			if (tag == want && got != Possible) || (tag != want && got != Excluded) {
				t.Fatal(term.Constant, tag, got)
			}
		}
	}
	if _, e := AttackTagVocabulary([]byte(`package attacks;type AttackTag int;const(None AttackTag=iota;First=42)`)); e == nil {
		t.Fatal("enum drift accepted")
	}
}

func TestMutatedInputsAndForeignTriggerCannotFilterARecipientHit(t *testing.T) {
	v := map[string]int{"github.com/genshinsim/gcsim/pkg/core/attacks.Second": 2}
	for _, change := range []string{"hit.AttackTag=a.Second;", "mutate(&hit);", "mutate(&hit.AttackTag);"} {
		s := strings.Replace(filterFixture, "switch hit.AttackTag", change+"switch hit.AttackTag", 1)
		d, e := Discover(map[string][]byte{"a.go": []byte(s)})
		if e != nil {
			t.Fatal(e)
		}
		if got := d.TermChannelApplicability(d.Recipes()[0].Terms[0], "tag/1", v); got != Unknown {
			t.Fatal(change, got)
		}
	}
	// Same selector spelling is insufficient: no modifier callback input role.
	d := Description{Conditions: map[string]Expression{"trigger": {Kind: "binary:==", Inputs: []Expression{{Kind: "selector", Symbol: "AttackTag", Inputs: []Expression{{Kind: "symbol", Symbol: "event_attack"}}}, {Kind: "qualified", Symbol: "github.com/genshinsim/gcsim/pkg/core/attacks.Second"}}}}}
	if got := d.TermChannelApplicability(Term{Guards: []string{"trigger"}}, "tag/1", v); got != Unknown {
		t.Fatal(got)
	}
}

func TestShadowedConditionAndMutableCountStayUnknown(t *testing.T) {
	for _, extra := range []string{"count=5;", "mutate(&count);"} {
		s := strings.Replace(sourceFixture, "if count >= 2", extra+"if count >= 2", 1)
		d, e := Discover(map[string][]byte{"a.go": []byte(s)})
		if e != nil {
			t.Fatal(e)
		}
		if got := d.TierApplicability(d.Effects[0], 1); got != Unknown {
			t.Fatal(extra, got)
		}
	}
	s := strings.Replace(sourceFixture, "return &Set{}", `if flag {count:=2;if count >= 2 {use(count)}};return &Set{}`, 1)
	d, e := Discover(map[string][]byte{"a.go": []byte(s)})
	if e != nil {
		t.Fatal(e)
	}
	if got := d.TierApplicability(d.Effects[0], 1); got != Unknown {
		t.Fatal("shadow collision narrowed", got)
	}
}
