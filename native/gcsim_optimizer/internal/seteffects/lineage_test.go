package seteffects

import (
	"strings"
	"testing"
)

const recipientFixture = `package arbitrary
import (
 c "github.com/genshinsim/gcsim/pkg/core"
 ch "github.com/genshinsim/gcsim/pkg/core/player/character"
)
type Set struct{Core *c.Core;Char *ch.CharWrapper;Count int}
func NewSet(core *c.Core, owner *ch.CharWrapper,count int)*Set {
 s:=Set{Core:core,Char:owner,Count:count}
 return &s
}
func(s *Set)Init()error {
 if s.Count<4{return nil}
 for _,member:=range s.Core.Player.Chars(){
  copy:=member
  copy.AddStatMod(Mod{Amount:func()float64{return .2}})
 }
 s.Char.AddStatMod(Mod{Amount:func()float64{return 20}})
 return nil
}`

func TestSourceRecipientRolesAndMutableFields(t *testing.T) {
	d, e := Discover(map[string][]byte{"a.go": []byte(recipientFixture)})
	if e != nil {
		t.Fatal(e)
	}
	r := d.Recipes()
	if len(r) != 2 || r[0].RecipientScope != "team_iteration_member" || r[1].RecipientScope != "owner" {
		t.Fatal(r)
	}
	if d.TierApplicability(r[0].Effect, 2) != Excluded {
		t.Fatal("count field not tracked")
	}
	for _, mutation := range []string{"s.Count=5;", "s.Count++;", "alias:=s;alias.Count=5;", "unknown(s);", "unknown(&s.Count);"} {
		s := strings.Replace(recipientFixture, "if s.Count<4", mutation+"if s.Count<4", 1)
		d, e := Discover(map[string][]byte{"a.go": []byte(s)})
		if e != nil {
			t.Fatal(e)
		}
		if d.TierApplicability(d.Effects[0], 2) != Unknown {
			t.Fatal("mutated count used as constant")
		}
	}
	s := strings.Replace(recipientFixture, "copy:=member", "copy:=member;copy=other", 1)
	d, e = Discover(map[string][]byte{"a.go": []byte(s)})
	if e != nil {
		t.Fatal(e)
	}
	if d.Recipes()[0].RecipientScope != "unresolved" {
		t.Fatal("mutable team recipient retained")
	}
}
