package seteffects

import (
	"strings"
	"testing"
)

func TestEngineVocabularyAndUnknownCoordinate(t *testing.T) {
	source := []byte(`package attributes;type Stat int;const(NoStat Stat=iota;EM;CR;EndStatType);var StatTypeString=[...]string{"n/a","em","cr"}`)
	v, e := StatVocabulary(source)
	if e != nil {
		t.Fatal(e)
	}
	if key, ok := OwnerStatKey(v["github.com/genshinsim/gcsim/pkg/core/attributes.EM"]); !ok || key != "em" {
		t.Fatal(v)
	}
	if _, ok := OwnerStatKey("dmg%"); ok {
		t.Fatal("invented all-damage equivalence")
	}
	if _, e = StatVocabulary([]byte(strings.Replace(string(source), ";CR;", ";CR=10;", 1))); e == nil {
		t.Fatal("changed enum accepted with shifted indices")
	}
	d, e := Discover(map[string][]byte{"test.go": []byte(sourceFixture)})
	if e != nil {
		t.Fatal(e)
	}
	signals, e := d.OwnerStatSignals(2, v)
	if e != nil {
		t.Fatal(e)
	}
	if len(signals.Signals) != 1 || signals.Signals[0].Amount != 75 || len(signals.ExcludedEffects) != 1 {
		t.Fatal(signals)
	}
}
