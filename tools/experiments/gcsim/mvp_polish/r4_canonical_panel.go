package contracts

import (
	"crypto/sha256"
	"encoding/hex"
	"unicode/utf8"
)

func BytesSHA256(raw []byte) string {
	digest := sha256.Sum256(raw)
	return hex.EncodeToString(digest[:])
}

// CanonicalSeedMembersJSON preserves CanonicalJSON's exact representation,
// including nil/empty, optional values, and unusual strings. Decode has already
// normalized UTF-8 on the ordinary capture path. Arbitrary Go values with invalid
// UTF-8 retain the generic normalization behavior, rather than a trusted bypass.
func CanonicalSeedMembersJSON(members []IRSeedMember) ([]byte, error) {
	var view []canonicalSeedMember
	if members != nil {
		view = make([]canonicalSeedMember, len(members))
	}
	for i, member := range members {
		if !seedMemberUTF8(member) {
			return CanonicalJSON(members)
		}
		view[i] = seedMemberCanonicalView(member)
	}
	return encodeCanonicalJSON(view)
}

func CanonicalSeedMembersSHA256(members []IRSeedMember) (string, error) {
	raw, err := CanonicalSeedMembersJSON(members)
	if err != nil {
		return "", err
	}
	return BytesSHA256(raw), nil
}

func seedMemberUTF8(member IRSeedMember) bool {
	valid := func(values ...string) bool {
		for _, s := range values {
			if !utf8.ValidString(s) {
				return false
			}
		}
		return true
	}
	if !valid(member.TopologySHA256) {
		return false
	}
	for _, n := range member.Nodes {
		if !valid(n.Operation, n.Coordinate, n.Value) {
			return false
		}
		for _, in := range n.Inputs {
			if !valid(in.Relation) {
				return false
			}
		}
	}
	for _, c := range member.Channels {
		if !valid(c.ChannelID, c.Kind, c.ActorKey, c.AttackTag, c.DamageType, c.BaselineDamage) {
			return false
		}
		if !valid(c.ResponseCoordinates...) {
			return false
		}
	}
	for _, b := range member.OpaqueBoundaries {
		if !valid(b.BoundaryID, b.ReasonCode, b.BaselineDamage, b.BaselineDamageShare) {
			return false
		}
	}
	if l := member.EnergyLedger; l != nil {
		for _, s := range l.InitialStates {
			if !valid(s.CharacterKey, s.Energy, s.EnergyMax) {
				return false
			}
		}
		for _, e := range l.Events {
			if !valid(e.CharacterKey, e.Kind, e.Source, e.EnergyBefore, e.EnergyAfter, e.EnergyMax, e.Amount) {
				return false
			}
			for _, p := range []*string{e.ObservedER, e.RawAtER100} {
				if p != nil && !valid(*p) {
					return false
				}
			}
		}
		if !valid(l.UncertaintyCodes...) {
			return false
		}
	}
	return true
}
