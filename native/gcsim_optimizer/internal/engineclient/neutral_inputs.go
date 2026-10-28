package engineclient

import (
	"fmt"
	"math"
	"strconv"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func validateNeutralInputs(n *contracts.NeutralInputs, member contracts.IRSeedMember, owners []string, occupied map[uint32]bool) error {
	if n == nil {
		return nil
	} // Historical installed captures are not neutral-capable.
	if n.Context.DurationFrames <= 0 || int64(math.Round(float64(n.Context.DurationFrames)*1000/60)) != member.DurationMS {
		return fmt.Errorf("neutral schedule horizon differs from damage member")
	}
	if n.SchemaVersion != 1 || !n.Context.NoSets || len(n.Context.Characters) != len(owners) ||
		n.Stats == nil || n.States == nil || n.Hits == nil || n.Ledger.Events == nil || n.Uncertainty == nil {
		return fmt.Errorf("neutral capture incomplete or contains a set")
	}
	ownerKeys := map[string]bool{}
	for i, c := range n.Context.Characters {
		if c.Index != i || c.Key != owners[i] {
			return fmt.Errorf("neutral capture changed character initialization order")
		}
		ownerKeys[c.Key] = true
		if !validEventValue(c.Base, 0) || !validEventValue(c.Stats, 0) {
			return fmt.Errorf("invalid neutral character payload")
		}
		if len(c.Facts) > 64 {
			return fmt.Errorf("neutral character facts exceed budget")
		}
		for key, value := range c.Facts {
			if key == "" || !validEventValue(value, 0) {
				return fmt.Errorf("invalid neutral character fact")
			}
		}
	}
	if n.Context.Active < -1 || n.Context.Active >= len(owners) {
		return fmt.Errorf("invalid neutral active character")
	}
	if n.World != nil {
		if n.World.States == nil || (n.World.Complete && len(n.World.States) == 0) {
			return fmt.Errorf("empty neutral world ledger")
		}
		previous := uint64(0)
		for _, world := range n.World.States {
			if world.Facts != nil && (world.Facts.Kind != "object" || !validEventValue(*world.Facts, 0)) {
				return fmt.Errorf("invalid neutral resource facts")
			}
			if world.Order <= previous || world.Active < -1 || world.Active >= len(owners) || world.Modifiers == nil {
				return fmt.Errorf("invalid neutral world ordering")
			}
			keys := map[string]bool{}
			targets := map[int]bool{}
			for _, target := range world.Targets {
				key, ok := target.Fields["Key"]
				if !validEventValue(target, 0) || target.Kind != "target" || !ok || key.Kind != "number" || key.Number < 0 || key.Number != math.Trunc(key.Number) || targets[int(key.Number)] {
					return fmt.Errorf("invalid neutral target fact identity")
				}
				targets[int(key.Number)] = true
			}
			for _, m := range world.Modifiers {
				key := strconv.Itoa(m.Owner) + ":" + m.Key
				if m.Owner < 0 || m.Owner >= len(owners) || m.Key == "" || keys[key] || m.Expiry < -1 {
					return fmt.Errorf("invalid neutral modifier identity")
				}
				keys[key] = true
			}
			previous = world.Order
		}
	}
	byOrder, positions := map[uint64]contracts.CombatEvent{}, map[uint64]bool{}
	if n.Hitlag != nil {
		if n.Hitlag.Events == nil {
			return fmt.Errorf("invalid neutral hitlag ledger")
		}
		previous := uint64(0)
		for _, e := range n.Hitlag.Events {
			if e.Order <= previous || e.Owner < -1 || e.Owner >= len(owners) || e.Target < -1 || (e.Owner == -1) == (e.Target == -1) {
				return fmt.Errorf("invalid neutral hitlag identity")
			}
			positions[e.Order] = true
			previous = e.Order
		}
	}
	stack := []contracts.CombatEvent{}
	previous := uint64(0)
	for _, e := range n.Ledger.Events {
		if e.Order <= previous || e.EndOrder <= e.Order || positions[e.Order] || positions[e.EndOrder] ||
			e.Event < 0 || e.Active < -1 || e.Active >= len(owners) || e.StateSequence < 0 || len(e.Arguments) > 64 {
			return fmt.Errorf("invalid neutral event ordering or payload")
		}
		for len(stack) > 0 && stack[len(stack)-1].EndOrder < e.Order {
			stack = stack[:len(stack)-1]
		}
		expectedParent := uint64(0)
		if len(stack) > 0 {
			expectedParent = stack[len(stack)-1].Order
		}
		if e.ParentOrder != expectedParent {
			return fmt.Errorf("neutral event parent does not match execution stack")
		}
		if e.ParentOrder != 0 {
			parent, ok := byOrder[e.ParentOrder]
			if !ok || parent.EndOrder <= e.EndOrder || parent.Frame != e.Frame {
				return fmt.Errorf("invalid nested neutral event")
			}
		}
		for _, v := range e.Arguments {
			if !validEventValue(v, 0) {
				return fmt.Errorf("invalid neutral event value")
			}
		}
		byOrder[e.Order], positions[e.Order], positions[e.EndOrder] = e, true, true
		stack = append(stack, e)
		previous = e.Order
	}
	previous = 0
	for _, s := range n.States {
		if s.Order <= previous || positions[s.Order] || s.Owner < 0 || s.Owner >= len(owners) || s.Key == "" ||
			(s.Kind != "status_add" && s.Kind != "status_delete") || (s.Kind == "status_add" && s.Expiry == nil) {
			return fmt.Errorf("invalid neutral status timeline")
		}
		previous = s.Order
	}
	nodes := map[uint32]contracts.IRNode{}
	for _, node := range member.Nodes {
		nodes[node.NodeID] = node
	}
	if n.ReadsComplete && n.Reads == nil {
		return fmt.Errorf("missing complete neutral read roots")
	}
	readIDs := map[uint32]bool{}
	for _, read := range n.Reads {
		_, ok := nodes[read.NodeID]
		x, err := strconv.ParseFloat(read.Observed, 64)
		if !ok || readIDs[read.NodeID] || !ownerKeys[read.Owner] || read.Stat == "" || read.Point.Order == 0 || err != nil || math.IsNaN(x) || math.IsInf(x, 0) || read.Uncertainty == nil {
			return fmt.Errorf("invalid neutral read root identity")
		}
		if read.Point.Mode != "stat" && read.Point.Mode != "non_extra_stat" {
			return fmt.Errorf("unknown neutral read filter")
		}
		if read.Projection && read.Point.Mode != "non_extra_stat" {
			return fmt.Errorf("invalid neutral Extra projection")
		}
		readIDs[read.NodeID] = true
	}
	for _, p := range n.Stats {
		node, ok := nodes[p.NodeID]
		value, err := strconv.ParseFloat(node.Value, 64)
		if !ok || occupied[p.NodeID] || node.Operation != "constant" || err != nil || value != 0 ||
			!ownerKeys[p.Owner] || p.Stat == "" || (p.Kind != "stat" && p.Kind != "attack" && p.Kind != "heal_bonus" && p.Kind != "flat_event") {
			return fmt.Errorf("invalid neutral stat input identity")
		}
		switch p.Point.Mode {
		case "stat", "non_extra_stat", "snapshot", "unresolved":
		default:
			return fmt.Errorf("unknown neutral query mode")
		}
		occupied[p.NodeID] = true
	}
	hits := map[uint64]bool{}
	for _, h := range n.Hits {
		if h.HitID == 0 || hits[h.HitID] || h.Actor < 0 || h.Actor >= len(owners) || h.Point.HitID != h.HitID {
			return fmt.Errorf("invalid neutral hit identity")
		}
		hits[h.HitID] = true
		if h.Attack != nil && !validEventValue(*h.Attack, 0) {
			return fmt.Errorf("invalid neutral attack payload")
		}
		keys := map[string]bool{}
		for _, key := range h.TargetKeys {
			if key == "" || keys[key] {
				return fmt.Errorf("invalid neutral target modifier identity")
			}
			keys[key] = true
		}
	}
	for _, p := range n.Stats {
		if p.Kind == "flat_event" && (p.Stat != "FlatDmg" || !hits[p.Point.HitID] || p.Point.Order == 0) {
			return fmt.Errorf("unbound neutral event-flat port")
		}
		if p.Kind == "heal_bonus" && (p.Stat != "heal_bonus" || p.Point.Order == 0) {
			return fmt.Errorf("unbound neutral received-healing port")
		}
	}
	effectIDs := map[string]bool{}
	for _, e := range n.Effects {
		if e.EventID == "" || e.Order == 0 || effectIDs[e.EventID] || (e.Input != nil && !validEventValue(*e.Input, 0)) {
			return fmt.Errorf("invalid neutral effect query metadata")
		}
		effectIDs[e.EventID] = true
	}
	return nil
}

func validEventValue(v contracts.EventValue, depth int) bool {
	if depth > 8 || math.IsNaN(v.Number) || math.IsInf(v.Number, 0) || len(v.Text) > 4096 || len(v.Items) > 128 || len(v.Fields) > 128 {
		return false
	}
	switch v.Kind {
	case "nil", "unknown", "number", "string", "bool", "object", "target", "character", "array", "map", "observation":
	default:
		return false
	}
	for _, f := range v.Fields {
		if !validEventValue(f, depth+1) {
			return false
		}
	}
	for _, f := range v.Items {
		if !validEventValue(f, depth+1) {
			return false
		}
	}
	return true
}
