package contracts

import (
	"fmt"
	"math/big"
	"sort"
)

func (compact CompactIR) Validate() error {
	if err := validateHeader(compact.SchemaVersion, compact.SchemaKind, CompactIRKind); err != nil {
		return err
	}
	for field, value := range map[string]string{
		"request_sha256":        compact.RequestSHA256,
		"engine_binding_sha256": compact.EngineBindingSHA256,
		"context_sha256":        compact.ContextSHA256,
	} {
		if err := validateSHA256(field, value, false); err != nil {
			return err
		}
	}
	if len(compact.Members) == 0 {
		return fmt.Errorf("members must not be empty")
	}
	for index, member := range compact.Members {
		if index > 0 && compact.Members[index-1].Seed >= member.Seed {
			return fmt.Errorf("members must be strictly sorted by seed")
		}
		if err := member.validate(index); err != nil {
			return err
		}
	}
	return nil
}

// ValidateSeedMember validates the direct engine-adapter boundary before a
// standalone optimizer wraps it in the request/context identities of CompactIR.
func ValidateSeedMember(member IRSeedMember) error {
	return member.validate(0)
}

func (member IRSeedMember) validate(memberIndex int) error {
	field := fmt.Sprintf("members[%d]", memberIndex)
	if member.DurationMS <= 0 {
		return fmt.Errorf("%s.duration_ms must be positive", field)
	}
	if err := validateSHA256(field+".topology_sha256", member.TopologySHA256, false); err != nil {
		return err
	}
	if len(member.Nodes) == 0 || len(member.Channels) == 0 {
		return fmt.Errorf("%s must contain nodes and channels", field)
	}
	if member.OpaqueBoundaries == nil {
		return fmt.Errorf("%s.opaque_boundaries must be an array", field)
	}
	nodeIDs := make(map[uint32]struct{}, len(member.Nodes))
	opaqueNodes := make(map[uint32]struct{})
	coveredOpaqueNodes := make(map[uint32]struct{})
	for index, node := range member.Nodes {
		expectedID := uint32(index + 1)
		if node.NodeID != expectedID {
			return fmt.Errorf("%s.nodes must use contiguous IDs starting at 1", field)
		}
		if err := node.validate(field, nodeIDs); err != nil {
			return err
		}
		nodeIDs[node.NodeID] = struct{}{}
		if node.Operation == "opaque_frozen" {
			opaqueNodes[node.NodeID] = struct{}{}
		}
	}
	for index, channel := range member.Channels {
		channelField := fmt.Sprintf("%s.channels[%d]", field, index)
		if err := validateToken(channelField+".channel_id", channel.ChannelID); err != nil {
			return err
		}
		if index > 0 && member.Channels[index-1].ChannelID >= channel.ChannelID {
			return fmt.Errorf("%s.channels must be strictly sorted by channel_id", field)
		}
		if channel.Kind != "direct" && channel.Kind != "reaction" {
			return fmt.Errorf("%s.kind is unsupported", channelField)
		}
		for name, value := range map[string]string{"actor_key": channel.ActorKey, "attack_tag": channel.AttackTag, "damage_type": channel.DamageType} {
			if err := validateToken(channelField+"."+name, value); err != nil {
				return err
			}
		}
		if _, ok := nodeIDs[channel.RootNodeID]; !ok {
			return fmt.Errorf("%s.root_node_id is unknown", channelField)
		}
		if channel.HitCount <= 0 {
			return fmt.Errorf("%s.hit_count must be positive", channelField)
		}
		if err := validateNonNegativeDecimal(channelField+".baseline_damage", channel.BaselineDamage); err != nil {
			return err
		}
		if channel.ResponseCoordinates == nil {
			return fmt.Errorf("%s.response_coordinates must be an array", channelField)
		}
		if err := validateSortedUniqueStrings(channelField+".response_coordinates", channel.ResponseCoordinates); err != nil {
			return err
		}
	}
	for index, boundary := range member.OpaqueBoundaries {
		boundaryField := fmt.Sprintf("%s.opaque_boundaries[%d]", field, index)
		if err := validateToken(boundaryField+".boundary_id", boundary.BoundaryID); err != nil {
			return err
		}
		if index > 0 && member.OpaqueBoundaries[index-1].BoundaryID >= boundary.BoundaryID {
			return fmt.Errorf("%s.opaque_boundaries must be strictly sorted by boundary_id", field)
		}
		if _, ok := opaqueNodes[boundary.NodeID]; !ok {
			return fmt.Errorf("%s.node_id must reference opaque_frozen node", boundaryField)
		}
		if _, exists := coveredOpaqueNodes[boundary.NodeID]; exists {
			return fmt.Errorf("%s.node_id repeats an opaque_frozen node", boundaryField)
		}
		coveredOpaqueNodes[boundary.NodeID] = struct{}{}
		if err := validateToken(boundaryField+".reason_code", boundary.ReasonCode); err != nil {
			return err
		}
		if err := validateNonNegativeDecimal(boundaryField+".baseline_damage", boundary.BaselineDamage); err != nil {
			return err
		}
		if err := validateUnitDecimal(boundaryField+".baseline_damage_share", boundary.BaselineDamageShare); err != nil {
			return err
		}
	}
	if len(opaqueNodes) != len(member.OpaqueBoundaries) {
		return fmt.Errorf("%s must describe every opaque_frozen node exactly once", field)
	}
	if member.EnergyLedger != nil {
		if err := member.EnergyLedger.validate(field + ".energy_ledger"); err != nil {
			return err
		}
	}
	return nil
}

func (ledger IREnergyLedger) validate(field string) error {
	if len(ledger.InitialStates) < 1 || len(ledger.InitialStates) > 4 || ledger.Events == nil || ledger.UncertaintyCodes == nil {
		return fmt.Errorf("%s must contain one to four initial states and array fields", field)
	}
	keys := make([]string, len(ledger.InitialStates))
	for index, state := range ledger.InitialStates {
		row := fmt.Sprintf("%s.initial_states[%d]", field, index)
		if state.CharacterIndex != index {
			return fmt.Errorf("%s.character_index must match array order", row)
		}
		if err := validateToken(row+".character_key", state.CharacterKey); err != nil {
			return err
		}
		if err := validateNonNegativeDecimal(row+".energy", state.Energy); err != nil {
			return err
		}
		if err := validateNonNegativeDecimal(row+".energy_max", state.EnergyMax); err != nil {
			return err
		}
		current, _ := new(big.Rat).SetString(state.Energy)
		maximum, _ := new(big.Rat).SetString(state.EnergyMax)
		if maximum.Sign() <= 0 || current.Cmp(maximum) > 0 {
			return fmt.Errorf("%s energy bounds are invalid", row)
		}
		keys[index] = state.CharacterKey
	}
	lastFrame := -1
	for index, event := range ledger.Events {
		row := fmt.Sprintf("%s.events[%d]", field, index)
		if event.SequenceIndex != index || event.Frame < lastFrame || event.Frame < 0 ||
			event.CharacterIndex < 0 || event.CharacterIndex >= len(keys) ||
			event.CharacterKey != keys[event.CharacterIndex] {
			return fmt.Errorf("%s identity or order is invalid", row)
		}
		if err := validateToken(row+".source", event.Source); err != nil {
			return err
		}
		for name, value := range map[string]string{
			"energy_before": event.EnergyBefore, "energy_after": event.EnergyAfter,
			"energy_max": event.EnergyMax,
		} {
			if err := validateNonNegativeDecimal(row+"."+name, value); err != nil {
				return err
			}
		}
		if err := validateDecimal(row+".amount", event.Amount); err != nil {
			return err
		}
		switch event.Kind {
		case "particle":
			if event.RawAtER100 == nil || event.ObservedER == nil || event.OnField == nil {
				return fmt.Errorf("%s particle scaling fields are required", row)
			}
			if err := validateNonNegativeDecimal(row+".raw_at_er_100", *event.RawAtER100); err != nil {
				return err
			}
			if err := validateNonNegativeDecimal(row+".observed_er", *event.ObservedER); err != nil {
				return err
			}
		case "flat":
			if event.RawAtER100 != nil || event.ObservedER != nil || event.OnField != nil {
				return fmt.Errorf("%s flat event carries particle fields", row)
			}
		case "burst":
			if event.RawAtER100 != nil || event.ObservedER != nil || event.OnField != nil {
				return fmt.Errorf("%s burst event carries particle fields", row)
			}
			amount, _ := new(big.Rat).SetString(event.Amount)
			if amount.Sign() <= 0 {
				return fmt.Errorf("%s burst cost must be positive", row)
			}
		default:
			return fmt.Errorf("%s.kind is unsupported", row)
		}
		lastFrame = event.Frame
	}
	return validateSortedUniqueStrings(field+".uncertainty_codes", ledger.UncertaintyCodes)
}

func (node IRNode) validate(memberField string, prior map[uint32]struct{}) error {
	field := fmt.Sprintf("%s.nodes[%d]", memberField, node.NodeID-1)
	if node.Inputs == nil {
		return fmt.Errorf("%s.inputs must be an array", field)
	}
	allowed := map[string]bool{
		"constant": true, "artifact_stat": true, "add": true, "multiply": true,
		"min": true, "max": true, "power": true, "opaque_frozen": true,
		"select_lt": true,
	}
	if !allowed[node.Operation] {
		return fmt.Errorf("%s.operation is unsupported", field)
	}
	for index, input := range node.Inputs {
		if _, ok := prior[input.NodeID]; !ok {
			return fmt.Errorf("%s.inputs[%d] must reference an earlier node", field, index)
		}
		if err := validateToken(fmt.Sprintf("%s.inputs[%d].relation", field, index), input.Relation); err != nil {
			return err
		}
	}
	switch node.Operation {
	case "constant", "opaque_frozen":
		if len(node.Inputs) != 0 || node.Coordinate != "" {
			return fmt.Errorf("%s constant/opaque node has invalid inputs or coordinate", field)
		}
		return validateDecimal(field+".value", node.Value)
	case "artifact_stat":
		if len(node.Inputs) != 0 || node.Value != "" {
			return fmt.Errorf("%s artifact_stat has invalid inputs or value", field)
		}
		return validateToken(field+".coordinate", node.Coordinate)
	case "power":
		if len(node.Inputs) != 2 || node.Value != "" || node.Coordinate != "" {
			return fmt.Errorf("%s power must contain exactly two inputs", field)
		}
	case "select_lt":
		if len(node.Inputs) != 4 || node.Value != "" || node.Coordinate != "" {
			return fmt.Errorf("%s select_lt must contain left, right, true, false inputs", field)
		}
	default:
		if len(node.Inputs) < 2 || node.Value != "" || node.Coordinate != "" {
			return fmt.Errorf("%s aggregate operation must contain at least two inputs", field)
		}
		for index := 1; index < len(node.Inputs); index++ {
			if node.Inputs[index-1].NodeID >= node.Inputs[index].NodeID {
				return fmt.Errorf("%s commutative inputs must be sorted and unique", field)
			}
		}
	}
	return nil
}

func (progress ProgressRecord) Validate() error {
	if err := validateHeader(progress.SchemaVersion, progress.SchemaKind, ProgressSchemaKind); err != nil {
		return err
	}
	if err := validateSHA256("request_sha256", progress.RequestSHA256, false); err != nil {
		return err
	}
	allowedStages := map[string]bool{
		"validating_request": true, "loading_evidence": true, "compiling_formula": true,
		"searching": true, "validating_finalists": true, "simulating_finalists": true,
		"completed": true, "cancelled": true, "failed": true,
	}
	if !allowedStages[progress.Stage] {
		return fmt.Errorf("unsupported progress stage %q", progress.Stage)
	}
	if progress.Sequence < 0 || progress.CompletedWork < 0 || progress.TotalWork < 0 || progress.ElapsedMS < 0 {
		return fmt.Errorf("progress counters must be non-negative")
	}
	if progress.TotalWork > 0 && progress.CompletedWork > progress.TotalWork {
		return fmt.Errorf("completed_work exceeds total_work")
	}
	return validateSHA256("cache_identity_sha256", progress.CacheIdentitySHA256, true)
}

func (result OptimizerResult) Validate() error {
	if err := validateHeader(result.SchemaVersion, result.SchemaKind, ResultSchemaKind); err != nil {
		return err
	}
	if err := validateSHA256("request_sha256", result.RequestSHA256, false); err != nil {
		return err
	}
	if result.Warnings == nil {
		return fmt.Errorf("warnings must be an array")
	}
	if err := validateSortedUniqueStrings("warnings", result.Warnings); err != nil {
		return err
	}
	switch result.Status {
	case "success":
		return result.validateSuccess()
	case "cancelled":
		if len(result.Winner) != 0 || len(result.Candidates) != 0 || result.Measured != nil || result.Energy != nil || result.Error != nil || result.FormulaDPS != "" || result.FormulaResidual != "" {
			return fmt.Errorf("cancelled result must not contain winner, measured result, error, or formula result")
		}
	case "failed":
		if result.Error == nil {
			return fmt.Errorf("failed result requires error")
		}
		if err := validateToken("error.code", result.Error.Code); err != nil {
			return err
		}
		if result.Error.Message == "" || len(result.Winner) != 0 || len(result.Candidates) != 0 || result.Measured != nil || result.Energy != nil || result.FormulaDPS != "" || result.FormulaResidual != "" {
			return fmt.Errorf("failed result has invalid payload")
		}
	default:
		return fmt.Errorf("unsupported result status %q", result.Status)
	}
	return nil
}

func (result OptimizerResult) validateSuccess() error {
	if (result.CompactIRSHA256 == "") == (result.SetContextPanelSHA256 == "") {
		return fmt.Errorf("success requires exactly one compact IR or set-context panel identity")
	}
	if result.CompactIRSHA256 != "" {
		if err := validateSHA256("compact_ir_sha256", result.CompactIRSHA256, false); err != nil {
			return err
		}
	}
	if result.SetContextPanelSHA256 != "" {
		if err := validateSHA256("set_context_panel_sha256", result.SetContextPanelSHA256, false); err != nil {
			return err
		}
	}
	if err := validateResultArtifacts("winner", result.Winner); err != nil {
		return err
	}
	if result.Measured == nil {
		return fmt.Errorf("successful result requires measured result")
	}
	if len(result.Candidates) > 0 {
		var previousDPS *big.Rat
		for index, candidate := range result.Candidates {
			field := fmt.Sprintf("candidates[%d]", index)
			if candidate.Rank != index+1 {
				return fmt.Errorf("%s rank must match measured order", field)
			}
			if err := validateResultArtifacts(field+".artifacts", candidate.Artifacts); err != nil {
				return err
			}
			if err := validateNonNegativeDecimal(field+".formula_dps", candidate.FormulaDPS); err != nil {
				return err
			}
			if err := validateDecimal(field+".formula_residual", candidate.FormulaResidual); err != nil {
				return err
			}
			if candidate.Measured.Iterations <= 0 {
				return fmt.Errorf("%s requires measured iterations", field)
			}
			if err := validateNonNegativeDecimal(field+".measured.dps", candidate.Measured.DPS); err != nil {
				return err
			}
			currentDPS, _ := new(big.Rat).SetString(candidate.Measured.DPS)
			if previousDPS != nil && previousDPS.Cmp(currentDPS) < 0 {
				return fmt.Errorf("candidates must be sorted by descending measured DPS")
			}
			previousDPS = currentDPS
			if err := validateNonNegativeDecimal(field+".measured.standard_error", candidate.Measured.StandardError); err != nil {
				return err
			}
			if err := validateSHA256(field+".measured.engine_result_sha256", candidate.Measured.EngineResultSHA256, false); err != nil {
				return err
			}
			for prior := 0; prior < index; prior++ {
				if sameArtifactAssignments(result.Candidates[prior].Artifacts, candidate.Artifacts) {
					return fmt.Errorf("candidates must not repeat artifact assignments")
				}
			}
		}
		first := result.Candidates[0]
		if !sameArtifactAssignments(first.Artifacts, result.Winner) ||
			first.FormulaDPS != result.FormulaDPS ||
			first.FormulaResidual != result.FormulaResidual ||
			first.Measured != *result.Measured {
			return fmt.Errorf("first ranked candidate must be the product winner")
		}
	}
	if err := validateNonNegativeDecimal("formula_dps", result.FormulaDPS); err != nil {
		return err
	}
	if err := validateDecimal("formula_residual", result.FormulaResidual); err != nil {
		return err
	}
	if result.Measured == nil || result.Measured.Iterations <= 0 {
		return fmt.Errorf("successful result requires measured iterations")
	}
	if err := validateNonNegativeDecimal("measured.dps", result.Measured.DPS); err != nil {
		return err
	}
	if err := validateNonNegativeDecimal("measured.standard_error", result.Measured.StandardError); err != nil {
		return err
	}
	if err := validateSHA256("measured.engine_result_sha256", result.Measured.EngineResultSHA256, false); err != nil {
		return err
	}
	if result.Energy != nil {
		if err := result.Energy.validate("energy"); err != nil {
			return err
		}
	}
	if result.DebugReceiptPath == "" || result.Error != nil {
		return fmt.Errorf("successful result requires debug receipt and no error")
	}
	return nil
}

func (result EnergyResult) validate(field string) error {
	if err := validateNonNegativeDecimal(field+".maximum_shortage", result.MaximumShortage); err != nil {
		return err
	}
	if len(result.Wearers) != 4 {
		return fmt.Errorf("%s must contain four wearers", field)
	}
	seen := map[string]bool{}
	for index, wearer := range result.Wearers {
		row := fmt.Sprintf("%s.wearers[%d]", field, index)
		if err := validateToken(row+".wearer_key", wearer.WearerKey); err != nil {
			return err
		}
		if seen[wearer.WearerKey] {
			return fmt.Errorf("%s repeats wearer", row)
		}
		seen[wearer.WearerKey] = true
		for name, value := range map[string]string{
			"artifact_er": wearer.ArtifactER, "required_artifact_er": wearer.RequiredArtifactER,
			"maximum_shortage": wearer.MaximumShortage,
		} {
			if err := validateNonNegativeDecimal(row+"."+name, value); err != nil {
				return err
			}
		}
		if err := validateDecimal(row+".artifact_er_margin", wearer.Margin); err != nil {
			return err
		}
		if wearer.BurstDeadlines < 0 || wearer.Sources == nil || wearer.UncertaintyCodes == nil {
			return fmt.Errorf("%s has invalid energy detail arrays or counters", row)
		}
		if err := validateSortedUniqueStrings(row+".uncertainty_codes", wearer.UncertaintyCodes); err != nil {
			return err
		}
		for sourceIndex, source := range wearer.Sources {
			sourceField := fmt.Sprintf("%s.sources[%d]", row, sourceIndex)
			if err := validateToken(sourceField+".source", source.Source); err != nil {
				return err
			}
			if err := validateNonNegativeDecimal(sourceField+".particle_raw_at_er_100", source.ParticleRaw); err != nil {
				return err
			}
			if err := validateDecimal(sourceField+".flat_observed", source.FlatObserved); err != nil {
				return err
			}
		}
	}
	return nil
}

func validateResultArtifacts(field string, assignments []ArtifactAssignment) error {
	if len(assignments) != 20 {
		return fmt.Errorf("%s must contain twenty assignments", field)
	}
	used := make(map[int64]struct{}, 20)
	perWearer := make(map[string]int)
	for index, assignment := range assignments {
		if err := validateToken(fmt.Sprintf("%s[%d].wearer_key", field, index), assignment.WearerKey); err != nil {
			return err
		}
		if !validSlot(assignment.Slot) || assignment.ArtifactID <= 0 {
			return fmt.Errorf("%s[%d] has invalid slot or artifact_id", field, index)
		}
		if index > 0 && compareAssignments(assignments[index-1], assignment) >= 0 {
			return fmt.Errorf("%s must be strictly sorted by wearer and canonical slot", field)
		}
		if _, exists := used[assignment.ArtifactID]; exists {
			return fmt.Errorf("%s repeats artifact_id %d", field, assignment.ArtifactID)
		}
		used[assignment.ArtifactID] = struct{}{}
		perWearer[assignment.WearerKey]++
	}
	if len(perWearer) != 4 {
		return fmt.Errorf("%s must contain four wearers", field)
	}
	for wearer, count := range perWearer {
		if count != 5 {
			return fmt.Errorf("%s wearer %s must contain five artifacts", field, wearer)
		}
	}
	return nil
}

func sameArtifactAssignments(left, right []ArtifactAssignment) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}

func SortedAssignments(assignments []ArtifactAssignment) bool {
	return sort.SliceIsSorted(assignments, func(left, right int) bool {
		return compareAssignments(assignments[left], assignments[right]) < 0
	})
}
