package seteffects

import (
	"math"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
)

func TestNeutralBindingTheoryForkOwnsSymbolicGraphsAndRetainsDAGSharing(t *testing.T) {
	first := &formula.InputExpression{Operation: "constant", Value: 1.25}
	second := &formula.InputExpression{Operation: "artifact", Key: "other.hp", Value: 2}
	root := &formula.InputExpression{Operation: "add", Key: "port", Value: math.Copysign(0, -1), Inputs: []*formula.InputExpression{first, second, first}}
	choice := RuleChoice{Owner: 0, Key: "symbolic", Pieces: 4}
	binding := &NeutralBinding{
		components: map[RuleChoice]neutralComponent{choice: {expressions: map[int]*formula.InputExpression{0: root}}},
		groups:     map[string]neutralComponent{"group": {expressions: map[int]*formula.InputExpression{0: root}}},
		composedPayloads: map[string]NeutralExpressions{"payload": {
			SparseEffects: map[int]*formula.InputExpression{0: root},
			Effects:       map[string]*formula.InputExpression{"read": first},
		}},
	}
	branch, sibling := binding.ForkTheory(), binding.ForkTheory()
	cloned := branch.components[choice].expressions[0]
	if cloned == root || cloned.Inputs[0] == first || cloned.Inputs[1] == second {
		t.Fatal("expression nodes remain shared with the parent")
	}
	if cloned.Operation != root.Operation || cloned.Key != root.Key || math.Float64bits(cloned.Value) != math.Float64bits(root.Value) ||
		cloned.Inputs[0].Value != 1.25 || cloned.Inputs[1].Operation != "artifact" || cloned.Inputs[1].Key != "other.hp" || cloned.Inputs[1].Value != 2 {
		t.Fatal("fork changed expression fields, exact value bits, or operand order")
	}
	if cloned.Inputs[0] != cloned.Inputs[2] || cloned != branch.groups["group"].expressions[0] ||
		cloned != branch.composedPayloads["payload"].SparseEffects[0] || cloned.Inputs[0] != branch.composedPayloads["payload"].Effects["read"] {
		t.Fatal("fork lost shared subgraphs within its retained payloads")
	}
	cloned.Inputs[0].Value = 99
	cloned.Inputs[1].Key = "changed.hp"
	cloned.Inputs[2] = nil
	if first.Value != 1.25 || second.Key != "other.hp" || root.Inputs[2] != first ||
		sibling.components[choice].expressions[0].Inputs[0].Value != 1.25 || sibling.components[choice].expressions[0].Inputs[2] == nil {
		t.Fatal("branch expression mutation reached the parent or sibling")
	}
	branch.components[choice].expressions[1] = cloned
	branch.composedPayloads["payload"].SparseEffects[1] = cloned
	branch.composedPayloads["payload"].Effects["other"] = cloned
	if len(binding.components[choice].expressions) != 1 || len(binding.composedPayloads["payload"].SparseEffects) != 1 || len(binding.composedPayloads["payload"].Effects) != 1 {
		t.Fatal("expression map mutation reached the parent")
	}
}

func TestNeutralBindingTheoryForkOwnsPayloadVectorsFootprintsOrdersAndCounters(t *testing.T) {
	choice := RuleChoice{Owner: 0, Key: "constant", Pieces: 2}
	dependency := ruleStatDependency{owner: 0, stat: "hp", mode: "stat"}
	footprint := ruleFootprint{
		reads: map[string]bool{"read": true}, writes: map[string]bool{"write": true},
		statReads: map[ruleStatDependency]bool{dependency: true}, statWrites: map[ruleStatDependency]bool{dependency: true},
	}
	identity := [32]byte{7}
	component := neutralComponent{effectIdentity: identity, raw: []float64{1}, footprint: footprint, uncertainty: []string{"component"}, usable: true}
	groupOrder, payloadOrder := make([]string, 1, 8), make([]string, 1, 8)
	groupOrder[0], payloadOrder[0] = "group", "payload"
	binding := &NeutralBinding{
		familySerial: 8, twoPieceFamilies: map[[32]byte]bool{identity: true},
		components: map[RuleChoice]neutralComponent{choice: component},
		groups:     map[string]neutralComponent{"group": component}, groupOrder: groupOrder, groupValues: 1,
		composedPayloads: map[string]NeutralExpressions{"payload": {
			raw: []float64{2}, Constants: []float64{3}, footprint: footprint,
			Boundaries: []string{"boundary"}, Uncertainty: []string{"payload"},
		}},
		composedPayloadOrder: payloadOrder, composedPayloadValues: 2, composedPayloadNodes: 3,
		componentExpressionNodes: 4, stats: NeutralPreparationStats{Requests: 5},
	}
	branch := binding.ForkTheory()
	branch.familySerial++
	branch.stats.Requests++
	branch.groupValues++
	branch.composedPayloadValues++
	branch.composedPayloadNodes++
	branch.componentExpressionNodes++
	delete(branch.twoPieceFamilies, identity)
	branch.groupOrder[0], branch.composedPayloadOrder[0] = "other", "other"
	branch.groups["group"].raw[0] = 10
	branch.components[choice].raw[0] = 11
	branch.components[choice].uncertainty[0] = "changed"
	componentFootprint := branch.components[choice].footprint
	delete(componentFootprint.reads, "read")
	delete(componentFootprint.writes, "write")
	delete(componentFootprint.statReads, dependency)
	delete(componentFootprint.statWrites, dependency)
	payload := branch.composedPayloads["payload"]
	payload.raw[0], payload.Constants[0] = 12, 13
	payload.Boundaries[0], payload.Uncertainty[0] = "changed", "changed"
	delete(payload.footprint.reads, "read")
	delete(payload.footprint.statWrites, dependency)
	delete(branch.groups, "group")
	delete(branch.composedPayloads, "payload")
	delete(branch.components, choice)
	if binding.familySerial != 8 || binding.stats.Requests != 5 || binding.groupValues != 1 || binding.composedPayloadValues != 2 || binding.composedPayloadNodes != 3 || binding.componentExpressionNodes != 4 {
		t.Fatal("branch counter mutation reached the parent")
	}
	if !binding.twoPieceFamilies[identity] || binding.groupOrder[0] != "group" || binding.composedPayloadOrder[0] != "payload" ||
		len(binding.components) != 1 || len(binding.groups) != 1 || len(binding.composedPayloads) != 1 {
		t.Fatal("branch map or FIFO mutation reached the parent")
	}
	parentComponent, parentGroup, parentPayload := binding.components[choice], binding.groups["group"], binding.composedPayloads["payload"]
	if parentComponent.raw[0] != 1 || parentGroup.raw[0] != 1 || parentComponent.uncertainty[0] != "component" ||
		parentPayload.raw[0] != 2 || parentPayload.Constants[0] != 3 || parentPayload.Boundaries[0] != "boundary" || parentPayload.Uncertainty[0] != "payload" {
		t.Fatal("branch payload slice mutation reached the parent")
	}
	for _, parent := range []ruleFootprint{parentComponent.footprint, parentGroup.footprint, parentPayload.footprint} {
		if !parent.reads["read"] || !parent.writes["write"] || !parent.statReads[dependency] || !parent.statWrites[dependency] {
			t.Fatal("branch footprint mutation reached the parent")
		}
	}
}
