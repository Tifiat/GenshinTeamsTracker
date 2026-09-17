package seteffects

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"testing"
)

func TestInputGuideRequiresExactGraphAndObservedValue(t *testing.T) {
	m := contracts.IRSeedMember{Seed: 1, DurationMS: 1000, TopologySHA256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", Nodes: []contracts.IRNode{
		{NodeID: 1, Operation: "constant", Value: "2", Inputs: []contracts.IRInput{}},
		{NodeID: 2, Operation: "constant", Value: "100", Inputs: []contracts.IRInput{}},
		{NodeID: 3, Operation: "multiply", Inputs: []contracts.IRInput{{NodeID: 1, Relation: "input/000000"}, {NodeID: 2, Relation: "input/000001"}}},
	}, Channels: []contracts.IRChannel{{ChannelID: "hit/000001", Kind: "reaction", ActorKey: "visible", AttackTag: "tag/7", DamageType: "dendro", RootNodeID: 3, HitCount: 1, BaselineDamage: "200", ResponseCoordinates: []string{}}}, OpaqueBoundaries: []contracts.IROpaqueBoundary{}}
	sha, _ := contracts.CanonicalSHA256(m)
	env := InputEnvelope{SchemaVersion: 1, MemberSHA256: sha, Inputs: []EffectInput{{EventID: "read", NodeID: 1, Kind: "reaction_bonus", Owner: "participant", AttackTag: "tag/4", Observed: "2"}}}
	p, e := NewInputProbe(m, []string{"participant", "visible"}, env)
	if e != nil {
		t.Fatal(e)
	}
	r := Recipe{Effect: Effect{ID: "source", Kind: "reaction_bonus"}, RecipientScope: "owner", Terms: []Term{{Constant: "1/2"}}}
	got, e := p.Feature(Description{}, r, 0, "participant", nil)
	if e != nil || got.MatchedReads != 1 || got.IncrementDPS == nil || *got.IncrementDPS != 50 {
		t.Fatal("lost actual contributor owner", got, e)
	}
	got, e = p.Feature(Description{}, r, 0, "visible", nil)
	if e != nil || got.IncrementDPS != nil {
		t.Fatal("displayed actor became owner", got, e)
	}
	r.RecipientScope = "team_iteration_member"
	got, e = p.Feature(Description{}, r, 0, "visible", nil)
	if e != nil || got.IncrementDPS == nil || *got.IncrementDPS != 50 {
		t.Fatal("team recipient lost contributor", got, e)
	}
	env.Inputs[0].Observed = "3"
	if _, e = NewInputProbe(m, []string{"participant", "visible"}, env); e == nil {
		t.Fatal("wrong observed input")
	}
	env.MemberSHA256 = "other"
	if _, e = NewInputProbe(m, []string{"participant", "visible"}, env); e == nil {
		t.Fatal("wrong graph binding")
	}
}
