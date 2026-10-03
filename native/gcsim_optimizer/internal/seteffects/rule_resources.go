package seteffects

// Host seams for observed resources, not set-name rules. Gameplay conditions,
// amounts and timers still execute from the selected engine's source. Energy
// uses observed gains with counterfactual debits (ER response is approximate);
// healing-event amounts remain an explicitly frozen activation envelope until
// health-event expression roots are exported. Source-only producer pilot,
// owned by the parametric section of GCSIM_OPTIMIZER_GO_BACKEND_DESIGN.md.
import (
	"fmt"
	"go/ast"
	"go/token"
	"math"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

type ruleObservation struct{ value contracts.EventValue }

func (h *ruleReplayHost) fact(name string) contracts.EventValue {
	if h.facts == nil {
		ruleFail("neutral resource facts are unobserved: " + name)
	}
	x, ok := h.facts.Fields[name]
	if !ok {
		ruleFail("neutral resource fact is absent: " + name)
	}
	return x
}

func (h *ruleReplayHost) resourceField(receiver any, name string) (any, bool) {
	if x, ok := receiver.(ruleObservation); ok {
		if strings.HasPrefix(name, "$implements:") {
			return strings.TrimPrefix(name, "$implements:") == x.value.Type, true
		}
		if name == "$type" {
			return x.value.Type, true
		}
		return nil, false
	}
	r, ok := receiver.(ruleRef)
	if !ok {
		return nil, false
	}
	if r.kind == "core" && (name == "Status" || name == "Flags" || name == "Constructs") {
		return ruleRef{kind: "core_" + name}, true
	}
	if r.kind == "core_Flags" && name == "Custom" {
		h.footprint.read("core_flags")
		h.footprint.write("core_flags")
		if h.customFlags == nil {
			x := h.fact("Custom")
			h.customFlags = &ruleMap{values: map[any]any{}, valueType: ast.NewIdent("float64")}
			for key, value := range x.Fields {
				h.customFlags.values[key] = h.wire(value)
			}
		}
		return h.customFlags, true
	}
	if r.kind == "char" && (name == "Energy" || name == "EnergyMax") {
		h.footprint.read(fmt.Sprintf("energy:%d", r.index))
		if name == "Energy" {
			if e, ok := h.energy[r.index]; ok {
				return e, true
			}
		}
		chars := h.fact("Characters").Items
		if r.index < 0 || r.index >= len(chars) {
			ruleFail("resource character identity absent")
		}
		value := ruleNumber(h.wire(chars[r.index].Fields[name]))
		if name == "Energy" {
			h.energy[r.index] = value
			h.uncertainty["energy_activation_uses_observed_particle_ER"] = true
		}
		return value, true
	}
	return nil, false
}

func (h *ruleReplayHost) resourceCall(receiver any, name string, args []any) (any, bool) {
	if x, ok := receiver.(ruleObservation); ok {
		if name == "Distance" && len(args) == 1 {
			y, ok := args[0].(ruleObservation)
			if !ok {
				ruleFail("unobserved position")
			}
			number := func(p ruleObservation, key string) float64 { return ruleNumber(h.wire(p.value.Fields[key])) }
			dx, dy := number(x, "X")-number(y, "X"), number(x, "Y")-number(y, "Y")
			return math.Sqrt(dx*dx + dy*dy), true // info.Point.Sub/Magnitude/Dot order.
		}
		if value, ok := x.value.Fields[name]; ok && len(args) == 0 {
			return h.wire(value), true
		}
		return nil, false
	}
	r, ok := receiver.(ruleRef)
	if !ok {
		return nil, false
	}
	switch r.kind {
	case "core_Status":
		if len(args) < 1 {
			ruleFail("core status arity")
		}
		key := ruleString(args[0])
		dependency := "core_status:" + key
		h.footprint.read(dependency)
		expiry, touched := h.coreStatus[key]
		if !touched {
			states := h.fact("Statuses")
			if value, ok := states.Fields[key]; ok {
				expiry = ruleInteger(h.wire(value))
			}
		}
		switch name {
		case "Duration":
			return float64(max(0, expiry-h.frame)), true
		case "Add":
			if len(args) != 2 {
				ruleFail("core status add arity")
			}
			h.footprint.write(dependency)
			h.coreStatus[key] = h.frame + ruleInteger(args[1])
			return nil, true
		case "Delete":
			h.footprint.write(dependency)
			h.coreStatus[key] = 0
			return nil, true
		case "Extend":
			if len(args) != 2 {
				ruleFail("core status extend arity")
			}
			h.footprint.write(dependency)
			if expiry > h.frame {
				h.coreStatus[key] = expiry + ruleInteger(args[1])
			}
			return nil, true
		}
	case "core_Constructs":
		if name == "ConstructsByType" && len(args) == 1 {
			match, rest := &ruleSlice{}, &ruleSlice{}
			for _, item := range h.fact("Constructs").Items {
				if ruleInteger(h.wire(item.Fields["Type"])) == ruleInteger(args[0]) {
					match.values = append(match.values, h.wire(item))
				} else {
					rest.values = append(rest.values, h.wire(item))
				}
			}
			return ruleTuple{match, rest}, true
		}
	case "shields":
		if name == "Get" && len(args) == 1 {
			for _, item := range h.fact("Shields").Items {
				if ruleInteger(h.wire(item.Fields["Type"])) == ruleInteger(args[0]) {
					return h.wire(item), true
				}
			}
			return nil, true
		}
	case "combat":
		if name == "Player" && len(args) == 0 {
			return ruleRef{kind: "player_position"}, true
		}
	case "player_position":
		if name == "Pos" && len(args) == 0 {
			return h.wire(h.fact("Position")), true
		}
	case "char":
		if name == "AddEnergy" && len(args) == 2 {
			if !ruleBoolean(h.wire(h.fact("IgnoreBurstEnergy"))) {
				ruleFail("schedule_change: set changes finite energy")
			}
			before, _ := h.resourceField(r, "Energy")
			cap, _ := h.resourceField(r, "EnergyMax")
			h.energy[r.index] = math.Max(0, math.Min(ruleNumber(cap), ruleNumber(before)+ruleNumber(args[1])))
			h.footprint.write(fmt.Sprintf("energy:%d", r.index))
			h.uncertainty["set_energy_change_callbacks_not_reemitted"] = true
			return nil, true
		}
	}
	return nil, false
}

func (h *ruleReplayHost) eventNumber(name string) (int, bool) {
	if h.vm == nil {
		return 0, false
	}
	m := h.vm.program.modules[gcsimImport+"pkg/core/event"]
	if m == nil {
		return 0, false
	}
	_, ok := m.globals[name]
	if !ok {
		return 0, false
	}
	return ruleInteger(h.vm.lookup(m.envs[m.files[0]], name)), true
}

func (h *ruleReplayHost) observeResourceEvent(e contracts.CombatEvent) error {
	if len(h.energy) == 0 {
		return nil
	}
	// Consume the actual pre-cap gain, not a difference between capped snapshots.
	// Events happen after the engine updates energy, so the event's pre value is
	// the initial state if this wearer has not been read yet.
	_, err := ruleTry(func() any {
		for _, name := range []string{"OnEnergyChange", "OnEnergyBurst"} {
			id, ok := h.eventNumber(name)
			if !ok || id != e.Event {
				continue
			}
			if len(e.Arguments) < 3 {
				ruleFail("energy event missing operands")
			}
			r, ok := h.wire(e.Arguments[0]).(ruleRef)
			if !ok || r.kind != "char" {
				ruleFail("energy event owner absent")
			}
			before, known := h.energy[r.index]
			if !known {
				before = ruleNumber(h.wire(e.Arguments[1]))
			}
			amount := ruleNumber(h.wire(e.Arguments[2]))
			if name == "OnEnergyBurst" {
				amount = -amount
			}
			cap, _ := h.resourceField(r, "EnergyMax")
			h.energy[r.index] = math.Max(0, math.Min(ruleNumber(cap), before+amount))
		}
		return nil
	})
	return err
}

func (h *ruleReplayHost) invokeEvent(sub ruleSubscription, event contracts.CombatEvent, args []any) any {
	if id, ok := h.eventNumber("OnHeal"); ok && event.Event == id {
		h.uncertainty["set_activation_heal_amount_frozen_to_observed_build"] = true
	}
	if id, ok := h.eventNumber("OnEnemyHit"); ok && event.Event == id && len(args) > 1 {
		if attack, ok := args[1].(*ruleObject); ok {
			var hit uint64
			if id, ok := attack.fields["HitID"]; ok {
				hit = uint64(ruleInteger(id))
			}
			if info, ok := attack.fields["Info"].(*ruleObject); ok {
				info.flatWrite = func(before, after any) {
					// Older observers serialize OnEnemyHit before assigning HitID.
					// Diagnose only an attempted write; never guess its damage port.
					if hit == 0 {
						ruleFail("event flat damage has no observed hit identity")
					}
					if !h.flatPorts[hit] {
						ruleFail("event flat damage has no retained formula port")
					}
					h.uncertainty["counterfactual_flat_callback_order_observed"] = true
					delta := ruleBinary(token.SUB, after, before)
					prior, exists := h.flatByHit[hit]
					if !exists {
						prior = float64(0)
					}
					h.flatByHit[hit] = ruleBinary(token.ADD, prior, delta)
					h.footprint.write(fmt.Sprintf("event_flat:%d", hit))
				}
			}
		}
	}
	return sub.vm.invoke(sub.fn, args)
}
