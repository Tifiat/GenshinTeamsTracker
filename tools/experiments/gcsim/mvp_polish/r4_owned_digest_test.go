package engineclient

import (
	"encoding/json"
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"reflect"
	"strings"
	"testing"
)

func TestR4OwnedDigestReuseAndExternalBytesGuard(t *testing.T) {
	member := contracts.IRSeedMember{Seed: 71, Nodes: []contracts.IRNode{{NodeID: 1}, {NodeID: 2}}}
	raw := []byte("exact member bytes\n")
	side := contracts.EffectInputsOutput{SchemaVersion: 1, Capability: contracts.EffectInputsCapability,
		MemberContentSHA256: contracts.BytesSHA256(raw), ContextSHA256: strings.Repeat("a", 64), InputConfigSHA256: strings.Repeat("a", 64),
		SourceConfigSHA256: strings.Repeat("d", 64), SourceManifestBodySHA256: strings.Repeat("b", 64), Seed: "71", CharacterKeys: []string{"a", "b", "c", "d"},
		EffectInputs:     []contracts.EffectInput{{EventID: "event1", NodeID: 1, Kind: "reaction_bonus", Owner: "a", AttackTag: "tag/9", Observed: "0"}},
		ResistanceInputs: []contracts.ResistanceInput{{NodeID: 2, HitID: 1, Element: "electro", Resistance: "0.1", Observed: "0.9"}}}
	encoded, err := json.Marshal(side)
	if err != nil {
		t.Fatal(err)
	}
	compare := func(body []byte) {
		t.Helper()
		old, oe := decodeEffectInputs(body, raw, member, side.ContextSHA256, side.SourceManifestBodySHA256)
		got, ge := decodeEffectInputsWithMemberSHA(body, contracts.BytesSHA256(raw), member, side.ContextSHA256, side.SourceManifestBodySHA256)
		if !reflect.DeepEqual(old, got) || (oe == nil) != (ge == nil) || fmt.Sprint(oe) != fmt.Sprint(ge) {
			t.Fatal("owned digest changed decode/guards", oe, ge)
		}
	}
	compare(encoded)
	compare(append(append([]byte{}, encoded...), []byte(" {}")...))
	compare([]byte("{}"))
	for _, mutate := range []func(*contracts.EffectInputsOutput){
		func(s *contracts.EffectInputsOutput) { s.MemberContentSHA256 = strings.Repeat("f", 64) },
		func(s *contracts.EffectInputsOutput) { s.ContextSHA256 = strings.Repeat("f", 64) },
		func(s *contracts.EffectInputsOutput) { s.Seed = "72" },
		func(s *contracts.EffectInputsOutput) { s.SourceManifestBodySHA256 = strings.Repeat("f", 64) },
	} {
		changed := side
		mutate(&changed)
		body, _ := json.Marshal(changed)
		compare(body)
	}
	changedRaw := append([]byte{}, raw...)
	changedRaw[0] ^= 1
	if _, err := decodeEffectInputs(encoded, changedRaw, member, side.ContextSHA256, side.SourceManifestBodySHA256); err == nil {
		t.Fatal("arbitrary changed raw bytes bypassed identity")
	}
	if _, err := decodeEffectInputsWithMemberSHA(encoded, strings.Repeat("0", 64), member, side.ContextSHA256, side.SourceManifestBodySHA256); err == nil {
		t.Fatal("wrong internal digest accepted")
	}
}
