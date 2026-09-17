package seteffects

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"math"
	"strings"
	"testing"
)

func TestResistanceSourcePortAndElement(t *testing.T) {
	curves, e := ExtractScalarSlices([]byte(scalarWitness), "Resistance", "ResMod")
	if e != nil {
		t.Fatal(e)
	}
	m := contracts.IRSeedMember{Seed: 1, DurationMS: 1000, TopologySHA256: strings.Repeat("a", 64), Nodes: []contracts.IRNode{
		{NodeID: 1, Operation: "constant", Value: "0.9", Inputs: []contracts.IRInput{}},
		{NodeID: 2, Operation: "constant", Value: "100", Inputs: []contracts.IRInput{}},
		{NodeID: 3, Operation: "multiply", Inputs: []contracts.IRInput{{NodeID: 1, Relation: "input/000000"}, {NodeID: 2, Relation: "input/000001"}}},
	}, Channels: []contracts.IRChannel{{ChannelID: "hit/000001", Kind: "direct", ActorKey: "any", AttackTag: "tag/1", DamageType: "new-element", RootNodeID: 3, HitCount: 1, BaselineDamage: "90", ResponseCoordinates: []string{}}}, OpaqueBoundaries: []contracts.IROpaqueBoundary{}}
	sha, _ := contracts.CanonicalSHA256(m)
	env := ResistanceEnvelope{1, sha, []ResistanceInput{{NodeID: 1, HitID: 1, TargetKey: 7, Element: "new-element", Resistance: "0.1", Observed: "0.9"}}}
	p, e := NewResistanceProbe(m, []string{"any"}, env, curves)
	if e != nil {
		t.Fatal(e)
	}
	got, n, e := p.Increment("new-element", -.3)
	if e != nil || n != 1 || math.Abs(got-20) > 1e-10 {
		t.Fatal(got, n, e)
	}
	got, n, e = p.Increment("other", -.3)
	if e != nil || n != 0 || got != 0 {
		t.Fatal("wrong element", got, n, e)
	}
	got, _, e = p.Increment("new-element", 0)
	if e != nil || got != 0 {
		t.Fatal("offset leaked across probes", got, e)
	}
	env.Inputs[0].NodeID = 2
	if _, e = NewResistanceProbe(m, []string{"any"}, env, curves); e == nil {
		t.Fatal("wrong graph port")
	}
	env.Inputs[0].NodeID = 1
	env.Inputs[0].Resistance = ".5"
	if _, e = NewResistanceProbe(m, []string{"any"}, env, curves); e == nil {
		t.Fatal("wrong source curve input")
	}
	env.MemberSHA256 = "other"
	if _, e = NewResistanceProbe(m, []string{"any"}, env, curves); e == nil {
		t.Fatal("wrong graph")
	}
}

func TestElementVocabularyUsesSourceNames(t *testing.T) {
	source := []byte(`package attributes;type Element int;const(Other Element=iota;Next;End);var ElementString=[...]string{"renamed","future"}`)
	v, e := ElementVocabulary(source)
	if e != nil || v["github.com/genshinsim/gcsim/pkg/core/attributes.Next"] != "future" {
		t.Fatal(v, e)
	}
	if _, e = ElementVocabulary([]byte(strings.Replace(string(source), "Next;", "Next=7;", 1))); e == nil {
		t.Fatal("shifted enum accepted")
	}
}
