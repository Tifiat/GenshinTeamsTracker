package setcontext

import (
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"testing"
)

func TestR4CaptureCanonicalAndMutableValidationParity(t *testing.T) {
	previous := r4TypedPanel
	defer func() { r4TypedPanel = previous }()
	target := fixtureContext(t)
	capture := Capture{ContextSHA256: target.key, ConfigSHA256: target.configSHA, EngineBindingSHA256: target.binding.Engine.BindingSHA256}
	for _, seed := range target.binding.Seeds {
		channels := make([]contracts.IRChannel, len(target.actors))
		for i, actor := range target.actors {
			channels[i] = contracts.IRChannel{ChannelID: fmt.Sprintf("hit%d", i), Kind: "direct", ActorKey: actor, AttackTag: "normal", DamageType: "physical", RootNodeID: 1, HitCount: 1, BaselineDamage: "1", ResponseCoordinates: []string{}}
		}
		capture.Members = append(capture.Members, contracts.IRSeedMember{Seed: seed, DurationMS: 1000, TopologySHA256: contracts.TextSHA256("fixture topology"), Nodes: []contracts.IRNode{{NodeID: 1, Operation: "constant", Inputs: []contracts.IRInput{}, Value: "1"}}, Channels: channels, OpaqueBoundaries: []contracts.IROpaqueBoundary{}})
	}
	wantHash, err := contracts.CanonicalSHA256(capture.Members)
	if err != nil {
		t.Fatal(err)
	}
	for _, enabled := range []bool{false, true} {
		r4TypedPanel = enabled
		compiled, e := compileCapture(target, capture)
		if e != nil {
			t.Fatal(e)
		}
		if compiled.graphSHA != wantHash {
			t.Fatal("capture canonical digest changed")
		}
	}
	// Public mutable slices cannot carry a durable validation token. Both
	// routes must still reject a later mutation before arithmetic is usable.
	for _, value := range []string{"NaN", "bad\xffvalue"} {
		capture.Members[0].Nodes[0].Value = value
		r4TypedPanel = false
		_, old := compileCapture(target, capture)
		r4TypedPanel = true
		_, got := compileCapture(target, capture)
		if old == nil || got == nil || fmt.Sprint(old) != fmt.Sprint(got) {
			t.Fatal("mutated member validation/error changed", old, got)
		}
	}
}
