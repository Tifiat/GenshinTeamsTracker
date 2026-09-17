package engineclient

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func TestEffectSidecarRejectsCrossContextAndMalformedPorts(t *testing.T) {
	m := contracts.IRSeedMember{Seed: 71, Nodes: []contracts.IRNode{{NodeID: 1}, {NodeID: 2}}}
	raw := []byte("exact member bytes\n")
	valid := contracts.EffectInputsOutput{
		SchemaVersion: 1, Capability: contracts.EffectInputsCapability,
		MemberContentSHA256: contracts.TextSHA256(string(raw)), ContextSHA256: strings.Repeat("a", 64),
		InputConfigSHA256: strings.Repeat("a", 64), SourceConfigSHA256: strings.Repeat("d", 64), SourceManifestBodySHA256: strings.Repeat("b", 64), Seed: "71",
		CharacterKeys:    []string{"b", "a", "c", "d"},
		EffectInputs:     []contracts.EffectInput{{EventID: "e1", NodeID: 1, Kind: "reaction_bonus", Owner: "b", AttackTag: "tag/9", Observed: "0"}},
		ResistanceInputs: []contracts.ResistanceInput{{NodeID: 2, HitID: 1, TargetKey: 0, Element: "electro", Resistance: "0.1", Observed: "0.9"}},
	}
	encode := func(v contracts.EffectInputsOutput) []byte {
		b, e := json.Marshal(v)
		if e != nil {
			t.Fatal(e)
		}
		return b
	}
	check := func(v contracts.EffectInputsOutput) error {
		_, e := decodeEffectInputs(encode(v), raw, m, strings.Repeat("a", 64), strings.Repeat("b", 64))
		return e
	}
	if e := check(valid); e != nil {
		t.Fatal(e)
	}
	for name, mutate := range map[string]func(*contracts.EffectInputsOutput){
		"bytes": func(v *contracts.EffectInputsOutput) {
			v.MemberContentSHA256 = contracts.TextSHA256("exact member bytes")
		},
		"context":         func(v *contracts.EffectInputsOutput) { v.ContextSHA256 = strings.Repeat("c", 64) },
		"config":          func(v *contracts.EffectInputsOutput) { v.InputConfigSHA256 = strings.Repeat("c", 64) },
		"resolved_config": func(v *contracts.EffectInputsOutput) { v.SourceConfigSHA256 = "" },
		"source":          func(v *contracts.EffectInputsOutput) { v.SourceManifestBodySHA256 = strings.Repeat("c", 64) },
		"seed":            func(v *contracts.EffectInputsOutput) { v.Seed = "72" },
		"missing":         func(v *contracts.EffectInputsOutput) { v.EffectInputs = nil },
		"owner":           func(v *contracts.EffectInputsOutput) { v.EffectInputs[0].Owner = "display_actor_not_owner" },
		"node":            func(v *contracts.EffectInputsOutput) { v.EffectInputs[0].NodeID = 99 },
		"duplicate":       func(v *contracts.EffectInputsOutput) { v.EffectInputs = append(v.EffectInputs, v.EffectInputs[0]) },
		"nan":             func(v *contracts.EffectInputsOutput) { v.ResistanceInputs[0].Observed = "NaN" },
	} {
		t.Run(name, func(t *testing.T) {
			var v contracts.EffectInputsOutput
			json.Unmarshal(encode(valid), &v)
			mutate(&v)
			if check(v) == nil {
				t.Fatal("bad sidecar accepted")
			}
		})
	}
	if _, e := decodeEffectInputs(append(encode(valid), []byte(" {}")...), raw, m, valid.ContextSHA256, valid.SourceManifestBodySHA256); e == nil {
		t.Fatal("trailing data")
	}
}

func TestMissingEffectCapabilityDoesNotLaunchOrWrite(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "must-not-create")
	if _, e := (BoundEngine{binaryPath: "must-not-launch"}).RunCompactWithEffects(context.Background(), "config", dir, 1, true); e == nil {
		t.Fatal("missing capability accepted")
	}
	if _, e := os.Stat(dir); !os.IsNotExist(e) {
		t.Fatal("directory created")
	}
}
