package gttcompact

// Audit-only overlay: expose the existing support compiler without changing its
// arithmetic. Never included in the engine patch or product binary.
import (
	"github.com/genshinsim/gcsim/pkg/optimization/optstats"
	"sort"
)

func DependencyAuditSupportGraph(buffer optstats.GTTTraceEquationBuffer, keys []string) IRSeedMember {
	b := &nodeBuilder{}
	p := compileSupportProgram(b, buffer, keys)
	member := IRSeedMember{Seed: 742031889, DurationMS: 1000, Nodes: b.nodes, Channels: []IRChannel{}, OpaqueBoundaries: []IROpaqueBoundary{}}
	ids := []string{}
	for id := range p.eventNodes {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, id := range ids {
		n := p.eventNodes[id]
		member.Channels = append(member.Channels, IRChannel{ChannelID: id, ActorKey: id, RootNodeID: n.id})
	}
	ids = nil
	for id := range p.eventOutputs {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, id := range ids {
		names := []string{}
		for key := range p.eventOutputs[id] {
			names = append(names, key)
		}
		sort.Strings(names)
		for _, key := range names {
			n := p.eventOutputs[id][key]
			member.Channels = append(member.Channels, IRChannel{ChannelID: id + "/" + key, ActorKey: id + "/" + key, RootNodeID: n.id})
		}
	}
	return member
}
