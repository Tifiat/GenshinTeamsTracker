package contracts

import "os"

func r3CanonicalDecodedContract(value any) ([]byte, error) {
	if os.Getenv("GTT_R3_TYPED_CANONICAL") == "1" {
		return canonicalDecodedContract(value)
	}
	return CanonicalJSON(value)
}

// canonicalDecodedContract is used only after decodeStrict's standard JSON
// decoder and EOF check. Decoded strings are well-formed UTF-8. Public
// CanonicalJSON deliberately keeps its original round trip, including its
// behavior for arbitrary Go strings containing invalid UTF-8.
func canonicalDecodedContract(value any) ([]byte, error) {
	if member, ok := value.(IRSeedMember); ok {
		return encodeCanonicalJSON(seedMemberCanonicalView(member))
	}
	return CanonicalJSON(value)
}

// Every object below declares its JSON keys in lexical order. These views
// keep scalar types, nil/empty slices, pointer presence and omitempty intact.
// They only borrow immutable scalar/slice/pointer values during one encoding;
// no validated envelope, persistent cache or input mutation is introduced.
type canonicalSeedMember struct {
	Channels         []canonicalIRChannel        `json:"channels"`
	DurationMS       int64                       `json:"duration_ms"`
	EnergyLedger     *canonicalIREnergyLedger    `json:"energy_ledger,omitempty"`
	Nodes            []canonicalIRNode           `json:"nodes"`
	OpaqueBoundaries []canonicalIROpaqueBoundary `json:"opaque_boundaries"`
	Seed             uint64                      `json:"seed"`
	TopologySHA256   string                      `json:"topology_sha256"`
}

type canonicalIRNode struct {
	Coordinate string    `json:"coordinate,omitempty"`
	Inputs     []IRInput `json:"inputs"`
	NodeID     uint32    `json:"node_id"`
	Operation  string    `json:"operation"`
	Value      string    `json:"value,omitempty"`
}

type canonicalIRChannel struct {
	ActorKey            string   `json:"actor_key"`
	AttackTag           string   `json:"attack_tag"`
	BaselineDamage      string   `json:"baseline_damage"`
	ChannelID           string   `json:"channel_id"`
	DamageType          string   `json:"damage_type"`
	HitCount            int      `json:"hit_count"`
	Kind                string   `json:"kind"`
	ResponseCoordinates []string `json:"response_coordinates"`
	RootNodeID          uint32   `json:"root_node_id"`
}

type canonicalIROpaqueBoundary struct {
	BaselineDamage      string `json:"baseline_damage"`
	BaselineDamageShare string `json:"baseline_damage_share"`
	BoundaryID          string `json:"boundary_id"`
	NodeID              uint32 `json:"node_id"`
	ReasonCode          string `json:"reason_code"`
}

type canonicalIREnergyLedger struct {
	Events           []canonicalIREnergyEvent `json:"events"`
	InitialStates    []IREnergyCharacterState `json:"initial_states"`
	UncertaintyCodes []string                 `json:"uncertainty_codes"`
}

type canonicalIREnergyEvent struct {
	Amount         string  `json:"amount"`
	CharacterIndex int     `json:"character_index"`
	CharacterKey   string  `json:"character_key"`
	EnergyAfter    string  `json:"energy_after"`
	EnergyBefore   string  `json:"energy_before"`
	EnergyMax      string  `json:"energy_max"`
	Frame          int     `json:"frame"`
	Kind           string  `json:"kind"`
	ObservedER     *string `json:"observed_er,omitempty"`
	OnField        *bool   `json:"on_field,omitempty"`
	RawAtER100     *string `json:"raw_at_er_100,omitempty"`
	SequenceIndex  int     `json:"sequence_index"`
	Source         string  `json:"source"`
}

func seedMemberCanonicalView(member IRSeedMember) canonicalSeedMember {
	out := canonicalSeedMember{
		DurationMS:     member.DurationMS,
		Seed:           member.Seed,
		TopologySHA256: member.TopologySHA256,
	}
	if member.Nodes != nil {
		out.Nodes = make([]canonicalIRNode, len(member.Nodes))
		for i, node := range member.Nodes {
			out.Nodes[i] = canonicalIRNode{
				Coordinate: node.Coordinate, Inputs: node.Inputs,
				NodeID: node.NodeID, Operation: node.Operation, Value: node.Value,
			}
		}
	}
	if member.Channels != nil {
		out.Channels = make([]canonicalIRChannel, len(member.Channels))
		for i, channel := range member.Channels {
			out.Channels[i] = canonicalIRChannel{
				ActorKey: channel.ActorKey, AttackTag: channel.AttackTag,
				BaselineDamage: channel.BaselineDamage, ChannelID: channel.ChannelID,
				DamageType: channel.DamageType, HitCount: channel.HitCount,
				Kind: channel.Kind, ResponseCoordinates: channel.ResponseCoordinates,
				RootNodeID: channel.RootNodeID,
			}
		}
	}
	if member.OpaqueBoundaries != nil {
		out.OpaqueBoundaries = make([]canonicalIROpaqueBoundary, len(member.OpaqueBoundaries))
		for i, boundary := range member.OpaqueBoundaries {
			out.OpaqueBoundaries[i] = canonicalIROpaqueBoundary{
				BaselineDamage:      boundary.BaselineDamage,
				BaselineDamageShare: boundary.BaselineDamageShare,
				BoundaryID:          boundary.BoundaryID, NodeID: boundary.NodeID,
				ReasonCode: boundary.ReasonCode,
			}
		}
	}
	if ledger := member.EnergyLedger; ledger != nil {
		out.EnergyLedger = &canonicalIREnergyLedger{
			InitialStates:    ledger.InitialStates,
			UncertaintyCodes: ledger.UncertaintyCodes,
		}
		if ledger.Events != nil {
			out.EnergyLedger.Events = make([]canonicalIREnergyEvent, len(ledger.Events))
			for i, event := range ledger.Events {
				out.EnergyLedger.Events[i] = canonicalIREnergyEvent{
					Amount: event.Amount, CharacterIndex: event.CharacterIndex,
					CharacterKey: event.CharacterKey, EnergyAfter: event.EnergyAfter,
					EnergyBefore: event.EnergyBefore, EnergyMax: event.EnergyMax,
					Frame: event.Frame, Kind: event.Kind, ObservedER: event.ObservedER,
					OnField: event.OnField, RawAtER100: event.RawAtER100,
					SequenceIndex: event.SequenceIndex, Source: event.Source,
				}
			}
		}
	}
	return out
}
