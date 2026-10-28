package formula

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"math"
	"strings"
	"testing"
)

// Source-independent capped support scalar. Cross-owner condition and both
// value arms must remain dependencies in dense and one-wearer evaluation.
func TestPureConditionalCrossOwnerCapResponse(t *testing.T) {
	member := contracts.IRSeedMember{Seed: 1, DurationMS: 1000, TopologySHA256: strings.Repeat("a", 64), OpaqueBoundaries: []contracts.IROpaqueBoundary{}}
	add := func(op, value, coordinate string, ids ...uint32) {
		in := []contracts.IRInput{}
		for _, id := range ids {
			in = append(in, contracts.IRInput{NodeID: id, Relation: "input"})
		}
		member.Nodes = append(member.Nodes, contracts.IRNode{NodeID: uint32(len(member.Nodes) + 1), Operation: op, Value: value, Coordinate: coordinate, Inputs: in})
	}
	add("constant", "1000", "")
	add("artifact_stat", "", "support.em")
	add("add", "", "", 1, 2)
	add("constant", "-200", "")
	add("add", "", "", 3, 4)
	add("constant", "0.001", "")
	add("multiply", "", "", 5, 6)
	add("constant", "0.8", "")
	add("select_lt", "", "", 8, 7, 8, 7)
	add("constant", "200", "")
	add("constant", "0", "")
	add("select_lt", "", "", 10, 3, 9, 11)
	member.Channels = []contracts.IRChannel{{ChannelID: "support_bonus", Kind: "direct", ActorKey: "driver", AttackTag: "skill", DamageType: "synthetic", RootNodeID: 12, HitCount: 1, BaselineDamage: "0.8", ResponseCoordinates: []string{"support.em"}}}
	compiled, err := CompileSeedMember(member, []string{"driver", "support"}, []string{"support.em"})
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct{ delta, want float64 }{{-850, 0}, {-800, 0}, {-799, .001}, {-470, .33}, {0, .8}, {1, .8}, {187, .8}} {
		slow, err := EvaluateSeedMember(member, map[string]float64{"support.em": tc.delta})
		if err != nil {
			t.Fatal(err)
		}
		dense, err := compiled.EvaluateDense([]float64{tc.delta})
		if err != nil {
			t.Fatal(err)
		}
		if _, err = compiled.EvaluateDamageDense([]float64{0}); err != nil {
			t.Fatal(err)
		}
		actor, err := compiled.EvaluateDamageDenseForActor([]float64{tc.delta}, 1)
		if err != nil {
			t.Fatal(err)
		}
		for _, got := range []float64{slow.Damage, dense.Damage, actor} {
			if math.Abs(got-tc.want) > 1e-12 {
				t.Fatalf("delta %g got %g want %g", tc.delta, got, tc.want)
			}
		}
	}
	broken := member
	broken.Nodes = append([]contracts.IRNode(nil), member.Nodes...)
	broken.Nodes[11].Inputs = broken.Nodes[11].Inputs[:3]
	if _, err := CompileSeedMember(broken, []string{"driver", "support"}, []string{"support.em"}); err == nil {
		t.Fatal("malformed select accepted")
	}
}
