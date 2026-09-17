package engineclient

import (
	"bytes"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"strconv"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func decodeEffectInputs(payload, memberBytes []byte, member contracts.IRSeedMember, configSHA, sourceSHA string) (*contracts.EffectInputsOutput, error) {
	var out contracts.EffectInputsOutput
	d := json.NewDecoder(bytes.NewReader(payload))
	d.DisallowUnknownFields()
	if err := d.Decode(&out); err != nil {
		return nil, fmt.Errorf("effect sidecar: %w", err)
	}
	var tail any
	if err := d.Decode(&tail); err != io.EOF {
		return nil, fmt.Errorf("effect sidecar trailing data")
	}
	if out.SchemaVersion != 1 || out.Capability != contracts.EffectInputsCapability ||
		out.MemberContentSHA256 != contracts.TextSHA256(string(memberBytes)) ||
		out.ContextSHA256 != configSHA || out.InputConfigSHA256 != configSHA ||
		out.SourceManifestBodySHA256 != sourceSHA || out.Seed != strconv.FormatUint(member.Seed, 10) {
		return nil, fmt.Errorf("effect sidecar graph/config/source/seed binding mismatch")
	}
	if digest, err := hex.DecodeString(out.SourceConfigSHA256); err != nil || len(digest) != 32 {
		return nil, fmt.Errorf("effect sidecar resolved config digest missing")
	}
	if out.EffectInputs == nil || out.ResistanceInputs == nil || len(out.CharacterKeys) != 4 {
		return nil, fmt.Errorf("effect sidecar incomplete")
	}
	owners := map[string]bool{}
	for _, key := range out.CharacterKeys {
		if key == "" || owners[key] {
			return nil, fmt.Errorf("ambiguous effect sidecar owners")
		}
		owners[key] = true
	}
	nodes := map[uint32]bool{}
	for _, n := range member.Nodes {
		nodes[n.NodeID] = true
	}
	for _, ch := range member.Channels {
		if !owners[ch.ActorKey] {
			return nil, fmt.Errorf("effect sidecar channel owner mismatch")
		}
	}
	seenNodes := map[uint32]bool{}
	events := map[string]bool{}
	hits := map[uint64]bool{}
	finite := func(s string) bool {
		v, e := strconv.ParseFloat(s, 64)
		return e == nil && !math.IsNaN(v) && !math.IsInf(v, 0)
	}
	for _, in := range out.EffectInputs {
		if !nodes[in.NodeID] || seenNodes[in.NodeID] || events[in.EventID] || in.EventID == "" || !owners[in.Owner] || in.Kind == "" || in.AttackTag == "" || !finite(in.Observed) {
			return nil, fmt.Errorf("effect sidecar input identity invalid")
		}
		seenNodes[in.NodeID] = true
		events[in.EventID] = true
	}
	for _, in := range out.ResistanceInputs {
		if !nodes[in.NodeID] || seenNodes[in.NodeID] || in.HitID == 0 || hits[in.HitID] || in.Element == "" || !finite(in.Resistance) || !finite(in.Observed) {
			return nil, fmt.Errorf("effect sidecar resistance identity invalid")
		}
		seenNodes[in.NodeID] = true
		hits[in.HitID] = true
	}
	return &out, nil
}
