package engineclient

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

// Only the managed candidate-source gate supplies these disposable captures.
// Exercise the same strict graph/config/source decoder as the engine provider.
func TestNeutralCandidateCaptureDecodes(t *testing.T) {
	job := os.Getenv("GTT_NEUTRAL_CAPTURE_DIR")
	if job == "" {
		t.Skip("managed candidate capture only")
	}
	read := func(name string) []byte {
		t.Helper()
		b, err := os.ReadFile(filepath.Join(job, name))
		if err != nil {
			t.Fatal(err)
		}
		return b
	}
	names := []string{"neutral-member.json"}
	if os.Getenv("GTT_NEUTRAL_TWO_SEEDS") == "1" {
		names = append(names, "neutral-member-second.json")
	}
	for _, name := range names {
		raw := read(name)
		var member contracts.IRSeedMember
		if err := json.Unmarshal(raw, &member); err != nil {
			t.Fatal(err)
		}
		var source struct {
			SHA string `json:"source_manifest_sha256"`
		}
		if err := json.Unmarshal(read("rule-sources.json"), &source); err != nil {
			t.Fatal(err)
		}
		n, err := decodeEffectInputs(read(name+".effects.json"), raw, member, contracts.TextSHA256(string(read("neutral.txt"))), source.SHA)
		if err != nil {
			t.Fatal(err)
		}
		if n.Neutral == nil || !n.Neutral.Context.NoSets {
			t.Fatal("lost neutral ABI")
		}
	}
}

func TestNeutralInputIdentityAndEventOrderValidation(t *testing.T) {
	owners := []string{"a", "b", "c", "d"}
	n := contracts.NeutralInputs{SchemaVersion: 1,
		Context: contracts.NeutralContext{NoSets: true, Active: 2, DurationFrames: 60},
		Ledger: contracts.CombatEventLedger{Events: []contracts.CombatEvent{
			{Order: 10, EndOrder: 20, Active: 2, Arguments: []contracts.EventValue{}},
			{Order: 12, EndOrder: 13, ParentOrder: 10, Active: 2, Arguments: []contracts.EventValue{{Kind: "unknown"}}},
		}},
		States: []contracts.NeutralStatePoint{}, Hits: []contracts.NeutralHitPoint{}, Uncertainty: []string{"observed_only"},
		Stats: []contracts.NeutralStatInput{{NodeID: 1, Kind: "stat", Owner: "c", Stat: "em", Point: contracts.NeutralInputPoint{Mode: "non_extra_stat", Order: 14}}},
	}
	for i, key := range owners {
		n.Context.Characters = append(n.Context.Characters, contracts.NeutralCharacter{Index: i, Key: key,
			Base: contracts.EventValue{Kind: "object"}, Stats: contracts.EventValue{Kind: "array"}})
	}
	member := contracts.IRSeedMember{DurationMS: 1000, Nodes: []contracts.IRNode{{NodeID: 1, Operation: "constant", Value: "0"}}}
	check := func(n *contracts.NeutralInputs) error {
		return validateNeutralInputs(n, member, owners, map[uint32]bool{})
	}
	if err := check(&n); err != nil {
		t.Fatal(err)
	}
	for name, change := range map[string]func(*contracts.NeutralInputs){
		"missing horizon":   func(v *contracts.NeutralInputs) { v.Context.DurationFrames = 0 },
		"changed horizon":   func(v *contracts.NeutralInputs) { v.Context.DurationFrames = 61 },
		"set retained":      func(v *contracts.NeutralInputs) { v.Context.NoSets = false },
		"owner order":       func(v *contracts.NeutralInputs) { v.Context.Characters[0].Index = 3 },
		"foreign owner":     func(v *contracts.NeutralInputs) { v.Stats[0].Owner = "display_actor" },
		"foreign node":      func(v *contracts.NeutralInputs) { v.Stats[0].NodeID = 99 },
		"duplicate port":    func(v *contracts.NeutralInputs) { v.Stats = append(v.Stats, v.Stats[0]) },
		"filter lost":       func(v *contracts.NeutralInputs) { v.Stats[0].Point.Mode = "" },
		"crossed events":    func(v *contracts.NeutralInputs) { v.Ledger.Events[1].EndOrder = 25 },
		"lost parent":       func(v *contracts.NeutralInputs) { v.Ledger.Events[1].ParentOrder = 0 },
		"duplicate order":   func(v *contracts.NeutralInputs) { v.Ledger.Events[1].Order = 10 },
		"unknown wire kind": func(v *contracts.NeutralInputs) { v.Ledger.Events[1].Arguments[0].Kind = "invented" },
		"unknown resource": func(v *contracts.NeutralInputs) {
			v.World = &contracts.NeutralWorldLedger{Complete: true, States: []contracts.NeutralWorldState{{Order: 1, Modifiers: []contracts.NeutralModifierIdentity{}, Facts: &contracts.EventValue{Kind: "invented"}}}}
		},
		"unbound flat event": func(v *contracts.NeutralInputs) {
			v.Stats[0].Kind = "flat_event"
			v.Stats[0].Stat = "FlatDmg"
			v.Stats[0].Point.HitID = 999
		},
		"unbound received heal": func(v *contracts.NeutralInputs) {
			v.Stats[0].Kind = "heal_bonus"
			v.Stats[0].Stat = "heal_bonus"
			v.Stats[0].Point.Order = 0
		},
	} {
		t.Run(name, func(t *testing.T) {
			raw, _ := json.Marshal(n)
			var copy contracts.NeutralInputs
			if err := json.Unmarshal(raw, &copy); err != nil {
				t.Fatal(err)
			}
			change(&copy)
			if check(&copy) == nil {
				t.Fatal("invalid neutral evidence accepted")
			}
		})
	}
	if err := validateNeutralInputs(&n, member, owners, map[uint32]bool{1: true}); err == nil {
		t.Fatal("port aliases a different effect")
	}
	member.Nodes[0].Value = "1"
	if err := check(&n); err == nil {
		t.Fatal("nonzero old effect accepted as neutral")
	}
}
