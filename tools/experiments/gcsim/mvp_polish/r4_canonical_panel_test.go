package contracts

import (
	"bytes"
	"math"
	"testing"
)

func r4PanelParity(t *testing.T, members []IRSeedMember) {
	t.Helper()
	want, we := CanonicalJSON(members)
	got, ge := CanonicalSeedMembersJSON(members)
	if (we == nil) != (ge == nil) || !bytes.Equal(want, got) {
		t.Fatal("panel canonical bytes differ", we, ge)
	}
	hash, err := CanonicalSeedMembersSHA256(members)
	expected, e := CanonicalSHA256(members)
	if (err == nil) != (e == nil) || hash != expected {
		t.Fatal("panel canonical identity differs", err, e)
	}
}

func TestR4CanonicalPanelBytesNilNumbersAndPointers(t *testing.T) {
	t.Setenv("GTT_R3_TYPED_CANONICAL", "1")
	r4PanelParity(t, nil)
	r4PanelParity(t, []IRSeedMember{})
	for _, ledger := range []bool{false, true} {
		for _, text := range []string{"", "-0", "1.000", "1e+09", "<>&\"\\\n\t", "\u2028\u2029", "日本語", "\x00"} {
			a := seedCanonicalFixture(ledger)
			a.Seed = math.MaxUint64
			a.DurationMS = math.MaxInt64
			a.Nodes[0].Value = text
			a.Channels[0].BaselineDamage = text
			if ledger {
				flag := false
				value := text
				a.EnergyLedger.Events = []IREnergyEvent{{SequenceIndex: 1, ObservedER: &value, RawAtER100: &value, OnField: &flag, Source: text}}
			}
			r4PanelParity(t, []IRSeedMember{a, a})
			a.Nodes[0].Inputs = nil
			a.Channels[0].ResponseCoordinates = nil
			a.OpaqueBoundaries = nil
			if ledger {
				a.EnergyLedger.InitialStates = nil
				a.EnergyLedger.Events = []IREnergyEvent{}
				a.EnergyLedger.UncertaintyCodes = nil
			}
			r4PanelParity(t, []IRSeedMember{a})
		}
	}
}

func TestR4CanonicalPanelMalformedGoStrings(t *testing.T) {
	mutators := []func(*IRSeedMember){
		func(m *IRSeedMember) { m.TopologySHA256 = "\xff\xfe" },
		func(m *IRSeedMember) { m.Nodes[0].Operation = "\xff" },
		func(m *IRSeedMember) { m.Nodes[0].Coordinate = "\xff" },
		func(m *IRSeedMember) { m.Nodes[0].Value = "\xff" },
		func(m *IRSeedMember) { m.Nodes[0].Inputs = []IRInput{{Relation: "\xff"}} },
		func(m *IRSeedMember) { m.Channels[0].ChannelID = "\xff" },
		func(m *IRSeedMember) { m.Channels[0].ActorKey = "\xff" },
		func(m *IRSeedMember) { m.Channels[0].Kind = "\xff" },
		func(m *IRSeedMember) { m.Channels[0].AttackTag = "\xff" },
		func(m *IRSeedMember) { m.Channels[0].DamageType = "\xff" },
		func(m *IRSeedMember) { m.Channels[0].BaselineDamage = "\xff" },
		func(m *IRSeedMember) { m.Channels[0].ResponseCoordinates = []string{"\xff"} },
		func(m *IRSeedMember) {
			m.OpaqueBoundaries = []IROpaqueBoundary{{BoundaryID: "\xff", ReasonCode: "\xff", BaselineDamage: "\xff", BaselineDamageShare: "\xff"}}
		},
		func(m *IRSeedMember) { m.EnergyLedger.InitialStates[0].CharacterKey = "\xff" },
		func(m *IRSeedMember) { m.EnergyLedger.InitialStates[0].Energy = "\xff" },
		func(m *IRSeedMember) { m.EnergyLedger.InitialStates[0].EnergyMax = "\xff" },
		func(m *IRSeedMember) { bad := "\xff"; m.EnergyLedger.Events = []IREnergyEvent{{ObservedER: &bad}} },
		func(m *IRSeedMember) { bad := "\xff"; m.EnergyLedger.Events = []IREnergyEvent{{RawAtER100: &bad}} },
		func(m *IRSeedMember) {
			m.EnergyLedger.Events = []IREnergyEvent{{CharacterKey: "\xff", Kind: "\xff", Source: "\xff", Amount: "\xff", EnergyBefore: "\xff", EnergyAfter: "\xff", EnergyMax: "\xff"}}
		},
		func(m *IRSeedMember) { m.EnergyLedger.UncertaintyCodes = []string{"\xff"} },
	}
	for i, mutate := range mutators {
		member := seedCanonicalFixture(true)
		mutate(&member)
		if seedMemberUTF8(member) {
			t.Fatal("invalid Go string missed", i)
		}
		r4PanelParity(t, []IRSeedMember{member})
	}
}

func TestR4RawAndCanonicalDigestRemainDifferent(t *testing.T) {
	member := seedCanonicalFixture(true)
	raw, err := CanonicalJSON(member)
	if err != nil {
		t.Fatal(err)
	}
	alternate := append([]byte(" \n"), raw...)
	if BytesSHA256(raw) == BytesSHA256(alternate) {
		t.Fatal("raw identity lost whitespace")
	}
	for _, b := range [][]byte{nil, {}, []byte("abc"), {0xff, 0, 0xfe}} {
		if BytesSHA256(b) != TextSHA256(string(b)) {
			t.Fatal("byte digest changed")
		}
	}
	r4PanelParity(t, []IRSeedMember{member})
}
