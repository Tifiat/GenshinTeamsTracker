package seteffects

import (
	"strings"
	"testing"
)

// Synthetic engine-shaped code deliberately changes labels, coefficients and
// import aliases. Tests pin source discovery, not gameplay or static reuse.
const sourceFixture = `package arbitrary
import (
 a "github.com/genshinsim/gcsim/pkg/core/attributes"
 ch "github.com/genshinsim/gcsim/pkg/core/player/character"
 ev "github.com/genshinsim/gcsim/pkg/core/event"
 mod "github.com/genshinsim/gcsim/pkg/modifier"
)
type Set struct { index int }
func NewSet(c *Core, wearer *ch.CharWrapper, count int) *Set {
 if count >= 2 {
  m:=make([]float64,a.EndStatType)
  m[a.EM]=37.5*2
  wearer.AddStatMod(ch.StatMod{Base:mod.NewBase("arbitrary-2",-1),AffectedStat:a.EM,Amount:func()[]float64{return m}})
 }
 if count >= 4 {
  f:=func(args ...any){
   if c.Active()!=wearer.Index(){return}
   for _, recipient:=range c.Chars(){
    buff:=make([]float64,a.EndStatType)
    buff[a.ATKP]=.23
    recipient.AddStatMod(ch.StatMod{Amount:func()[]float64{return buff}})
   }
  }
  c.Events.Subscribe(ev.OnBurst,f,"source-key")
 }
 return &Set{}
}
func(s *Set)Init()error{return nil}
`

func TestSourceRecipesAliasesBranchesCallbacksAndRenaming(t *testing.T) {
	d, err := Discover(map[string][]byte{"fixture.go": []byte(sourceFixture)})
	if err != nil {
		t.Fatal(err)
	}
	if err = d.ValidateDiscovery(); err != nil {
		t.Fatal(err)
	}
	if len(d.Effects) != 2 {
		t.Fatalf("effects: %+v", d.Effects)
	}
	recipes := d.Recipes()
	if len(recipes[0].Terms) != 1 || recipes[0].Terms[0].Constant != "75" || !strings.HasSuffix(recipes[0].Terms[0].Coordinate, "/attributes.EM") {
		t.Fatalf("source amount missing: %+v", recipes)
	}
	if recipes[1].Terms[0].Constant != "23/100" {
		t.Fatal(recipes[1])
	}
	if !strings.Contains(strings.Join(d.Effects[1].Guards, " "), "!(c.Active() != wearer.Index())") {
		t.Fatal("lost early-return exclusion", d.Effects[1])
	}
	if len(d.Edges) != 1 || d.Edges[0].Kind != "event" || !strings.HasSuffix(d.Edges[0].Trigger.Symbol, "/event.OnBurst") {
		t.Fatal(d.Edges)
	}
	if strings.Join(d.Edges[0].Guards, "") != "count >= 4" {
		t.Fatal("lost callback registration condition")
	}
	paths := d.EffectPaths(d.Effects[1])
	if paths.Incomplete || len(paths.Paths) != 1 || !strings.Contains(strings.Join(paths.Paths[0].Guards, " "), "count >= 4") {
		t.Fatal("lost registration ancestry", paths)
	}
	changed := strings.ReplaceAll(sourceFixture, "arbitrary-2", "different-label")
	changed = strings.ReplaceAll(changed, "37.5*2", "42*3")
	other, err := Discover(map[string][]byte{"fixture.go": []byte(changed)})
	if err != nil {
		t.Fatal(err)
	}
	if other.Recipes()[0].Terms[0].Constant != "126" || other.SourceSHA256 == d.SourceSHA256 {
		t.Fatal("hardcoded amount or stale source binding")
	}
	if d.ReplacementCertified || other.ReplacementCertified {
		t.Fatal("discovery granted proof")
	}
	if d.TierApplicability(d.Effects[0], 1) != Excluded || d.TierApplicability(d.Effects[0], 2) != Possible || d.TierApplicability(d.Effects[1], 2) != Excluded || d.TierApplicability(d.Effects[1], 4) != Unknown {
		t.Fatal("incorrect piece-count specialization")
	}
	if d.Effects[0].Receiver.Symbol != "set_owner" {
		t.Fatal("constructor owner not resolved")
	}
}

func TestUnknownOperationsAndMutableCallbacksCannotDisappear(t *testing.T) {
	src := strings.Replace(sourceFixture, "c.Events.Subscribe(ev.OnBurst,f,\"source-key\")", "f=other; c.Events.Subscribe(ev.OnBurst,f,\"source-key\"); wearer.AddFutureBonus(42)", 1)
	d, err := Discover(map[string][]byte{"fixture.go": []byte(src)})
	if err != nil {
		t.Fatal(err)
	}
	unknown, callback := false, false
	for _, b := range d.Boundaries {
		unknown = unknown || b.Reason == "unclassified_operation"
		callback = callback || b.Reason == "callback_or_helper_unresolved"
	}
	if !unknown || !callback {
		t.Fatal(d.Boundaries)
	}
}

func TestShadowedVectorsDoNotMix(t *testing.T) {
	src := strings.Replace(sourceFixture, "m[a.EM]=37.5*2", "m[a.EM]=37.5*2; if flag {m:=make([]float64,a.EndStatType);m[a.EM]=999; use(m)}", 1)
	d, err := Discover(map[string][]byte{"fixture.go": []byte(src)})
	if err != nil {
		t.Fatal(err)
	}
	if terms := d.Recipes()[0].Terms; len(terms) != 1 || terms[0].Constant != "75" {
		t.Fatal(terms)
	}
}

func TestReturnedInstanceLinksInitAndHelpersButNotOtherInstance(t *testing.T) {
	source := `package example
import a "engine/attributes"
type Set struct{buff []float64}
func NewSet(c *Core,owner *Character,count int)*Set{
 s:=Set{};s.buff=make([]float64,10);s.buff[a.DmgP]=.25
 scratch:=Set{};scratch.buff=make([]float64,10);scratch.buff[a.DmgP]=99
 owner.AddAttackMod(Mod{Amount:func()[]float64{return s.buff}})
 return &s
}
func(other *Set)Init()error{other.gain();return nil}
func(v *Set)gain(){v.buff[a.DmgP]=.5}
`
	d, e := Discover(map[string][]byte{"a.go": []byte(source)})
	if e != nil {
		t.Fatal(e)
	}
	terms := d.Recipes()[0].Terms
	if len(terms) != 2 || terms[0].Constant != "1/4" || terms[1].Constant != "1/2" {
		t.Fatal(terms)
	}
	if len(d.Edges) != 1 || d.Edges[0].Kind != "call" {
		t.Fatal("helper edge missing", d.Edges)
	}
}

func TestIntegerDivisionAndSourceZeroAreNotInventedFloatAmounts(t *testing.T) {
	d, e := Discover(map[string][]byte{"a.go": []byte(strings.Replace(sourceFixture, "37.5*2", "1/2", 1))})
	if e != nil {
		t.Fatal(e)
	}
	if d.Recipes()[0].Terms[0].Constant != "0" {
		t.Fatal(d.Recipes()[0])
	}
}
