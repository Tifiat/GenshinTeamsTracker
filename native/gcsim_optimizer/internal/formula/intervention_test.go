package formula

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"testing"
)

func TestInterventionRetainsOriginalDependencyAndResetsWithoutNewDamageMath(t *testing.T) {
	m := contracts.IRSeedMember{Seed: 1, DurationMS: 1000, TopologySHA256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", Nodes: []contracts.IRNode{
		{NodeID: 1, Operation: "constant", Value: "20", Inputs: []contracts.IRInput{}},
		{NodeID: 2, Operation: "artifact_stat", Coordinate: "provider.em", Inputs: []contracts.IRInput{}},
		{NodeID: 3, Operation: "add", Inputs: []contracts.IRInput{{NodeID: 1, Relation: "input/000000"}, {NodeID: 2, Relation: "input/000001"}}},
		{NodeID: 4, Operation: "multiply", Inputs: []contracts.IRInput{{NodeID: 1, Relation: "input/000000"}, {NodeID: 3, Relation: "input/000001"}}},
	}, Channels: []contracts.IRChannel{{ChannelID: "hit/000001", Kind: "reaction", ActorKey: "recipient", AttackTag: "tag/31", DamageType: "dendro", RootNodeID: 4, HitCount: 1, BaselineDamage: "400", ResponseCoordinates: []string{"provider.em"}}}, OpaqueBoundaries: []contracts.IROpaqueBoundary{}}
	p, e := CompileInterventions(m, []string{"provider", "recipient"}, []string{"provider.em"}, []uint32{3})
	if e != nil {
		t.Fatal(e)
	}
	for _, test := range []struct{ stat, offset, want float64 }{{0, 0, 400}, {10, 5, 700}, {0, 0, 400}, {-10, 5, 300}} {
		got, e := p.Evaluate([]float64{test.stat}, map[uint32]float64{3: test.offset})
		if e != nil || got.Damage != test.want || got.ByActor[1] != test.want {
			t.Fatal(got, e)
		}
	}
	if _, e = p.Evaluate([]float64{0}, map[uint32]float64{1: 1}); e == nil {
		t.Fatal("unbound intervention accepted")
	}
	if _, e = CompileInterventions(m, []string{"provider", "recipient"}, []string{"provider.em"}, []uint32{3, 3}); e == nil {
		t.Fatal("ambiguous input")
	}
}
