package contracts

import "fmt"

func (source SourceText) validate(field string) error {
	if source.Text == "" {
		return fmt.Errorf("%s.text must not be empty", field)
	}
	if err := validateSHA256(field+".sha256", source.SHA256, false); err != nil {
		return err
	}
	if actual := TextSHA256(source.Text); actual != source.SHA256 {
		return fmt.Errorf("%s.sha256 does not match text", field)
	}
	return nil
}

func contextIdentity(context RunContext) (string, error) {
	payload := struct {
		PreparedConfigSHA256 string `json:"prepared_config_sha256"`
		RotationSHA256       string `json:"rotation_sha256"`
		TargetSHA256         string `json:"target_sha256"`
	}{
		PreparedConfigSHA256: context.PreparedConfig.SHA256,
		RotationSHA256:       context.Rotation.SHA256,
		TargetSHA256:         context.Target.SHA256,
	}
	return CanonicalSHA256(payload)
}

func (request OptimizerRequest) Validate() error {
	return request.validate(false)
}

// ValidateTheory keeps the ordinary optimizer contract strict while allowing
// the inventory-independent Theory request expanded by DecodeTheoryRequest.
func (request OptimizerRequest) ValidateTheory() error {
	return request.validate(true)
}

func (request OptimizerRequest) validate(theory bool) error {
	if err := validateHeader(request.SchemaVersion, request.SchemaKind, RequestSchemaKind); err != nil {
		return err
	}
	if request.StrategyID != StrategyID {
		return fmt.Errorf("unsupported strategy_id %q", request.StrategyID)
	}
	if request.Engine.BinaryPath == "" {
		return fmt.Errorf("engine.binary_path must not be empty")
	}
	for field, value := range map[string]string{
		"engine.artifact_sha256":        request.Engine.ArtifactSHA256,
		"engine.binding_sha256":         request.Engine.BindingSHA256,
		"engine.source_manifest_sha256": request.Engine.SourceManifestSHA256,
		"engine.patch_manifest_sha256":  request.Engine.PatchManifestSHA256,
	} {
		if err := validateSHA256(field, value, false); err != nil {
			return err
		}
	}
	if len(request.Engine.Capabilities) == 0 {
		return fmt.Errorf("engine.capabilities must not be empty")
	}
	if err := validateSortedUniqueStrings("engine.capabilities", request.Engine.Capabilities); err != nil {
		return err
	}
	if err := request.Context.PreparedConfig.validate("context.prepared_config"); err != nil {
		return err
	}
	if err := request.Context.Rotation.validate("context.rotation"); err != nil {
		return err
	}
	if err := request.Context.Target.validate("context.target"); err != nil {
		return err
	}
	if err := validateSHA256("context.context_sha256", request.Context.ContextSHA256, false); err != nil {
		return err
	}
	if err := validateSHA256("context.trace_context_sha256", request.Context.TraceContextSHA256, false); err != nil {
		return err
	}
	expectedContext, err := contextIdentity(request.Context)
	if err != nil {
		return err
	}
	if expectedContext != request.Context.ContextSHA256 {
		return fmt.Errorf("context.context_sha256 does not match source identities")
	}

	artifacts, err := request.validateArtifacts()
	if err != nil {
		return err
	}
	if err := request.validateWearers(artifacts, theory); err != nil {
		return err
	}
	if err := request.validatePolicies(artifacts, theory); err != nil {
		return err
	}
	return nil
}

func (request OptimizerRequest) validateArtifacts() (map[int64]Artifact, error) {
	if len(request.Artifacts) == 0 {
		return nil, fmt.Errorf("artifacts must not be empty")
	}
	byID := make(map[int64]Artifact, len(request.Artifacts))
	var previousID int64
	for index, artifact := range request.Artifacts {
		field := fmt.Sprintf("artifacts[%d]", index)
		if artifact.ArtifactID <= 0 {
			return nil, fmt.Errorf("%s.artifact_id must be positive", field)
		}
		if index > 0 && previousID >= artifact.ArtifactID {
			return nil, fmt.Errorf("artifacts must be strictly sorted by artifact_id")
		}
		previousID = artifact.ArtifactID
		if !validSlot(artifact.Slot) {
			return nil, fmt.Errorf("%s.slot is unsupported", field)
		}
		if err := validateToken(field+".set_uid", artifact.SetUID); err != nil {
			return nil, err
		}
		if artifact.Rarity < 1 || artifact.Rarity > 5 {
			return nil, fmt.Errorf("%s.rarity must be between 1 and 5", field)
		}
		if artifact.Level < 0 || artifact.Level > 20 {
			return nil, fmt.Errorf("%s.level must be between 0 and 20", field)
		}
		if artifact.Substats == nil {
			return nil, fmt.Errorf("%s.substats must be an array", field)
		}
		if err := validateStat(field+".main_stat", artifact.MainStat); err != nil {
			return nil, err
		}
		for subIndex, stat := range artifact.Substats {
			if err := validateStat(fmt.Sprintf("%s.substats[%d]", field, subIndex), stat); err != nil {
				return nil, err
			}
			if stat.Key == artifact.MainStat.Key {
				return nil, fmt.Errorf("%s repeats main stat in substats", field)
			}
			if subIndex > 0 && artifact.Substats[subIndex-1].Key >= stat.Key {
				return nil, fmt.Errorf("%s.substats must be strictly sorted by key", field)
			}
		}
		byID[artifact.ArtifactID] = artifact
	}
	return byID, nil
}

func validateStat(field string, stat StatValue) error {
	if err := validateToken(field+".key", stat.Key); err != nil {
		return err
	}
	return validateDecimal(field+".value", stat.Value)
}

func (request OptimizerRequest) validateWearers(artifacts map[int64]Artifact, theory bool) error {
	if len(request.Wearers) != 4 {
		return fmt.Errorf("wearers must contain exactly four characters")
	}
	used := make(map[int64]struct{}, 20)
	for index, wearer := range request.Wearers {
		field := fmt.Sprintf("wearers[%d]", index)
		if err := validateToken(field+".wearer_key", wearer.WearerKey); err != nil {
			return err
		}
		if index > 0 && request.Wearers[index-1].WearerKey >= wearer.WearerKey {
			return fmt.Errorf("wearers must be strictly sorted by wearer_key")
		}
		if err := validateToken(field+".weapon_key", wearer.WeaponKey); err != nil {
			return err
		}
		if theory {
			if wearer.SelectedSetUID != "" || len(wearer.SelectedSets) != 0 {
				return fmt.Errorf("%s theory baseline must not select an initial set package", field)
			}
		} else {
			if err := validateSetRequirements(field, wearer); err != nil {
				return err
			}
		}
		if wearer.TheoryBaseline != nil {
			return fmt.Errorf("%s contains an unexpanded theory baseline", field)
		}
		if len(wearer.CurrentArtifacts) != len(canonicalSlots) {
			return fmt.Errorf("%s.current_artifacts must contain five slots", field)
		}
		for slotIndex, assignment := range wearer.CurrentArtifacts {
			expectedSlot := canonicalSlots[slotIndex]
			if assignment.WearerKey != wearer.WearerKey {
				return fmt.Errorf("%s.current_artifacts[%d].wearer_key mismatch", field, slotIndex)
			}
			if assignment.Slot != expectedSlot {
				return fmt.Errorf("%s.current_artifacts must use canonical slot order", field)
			}
			artifact, ok := artifacts[assignment.ArtifactID]
			if !ok {
				return fmt.Errorf("%s references unknown artifact_id %d", field, assignment.ArtifactID)
			}
			if artifact.Slot != assignment.Slot {
				return fmt.Errorf("%s artifact slot mismatch for id %d", field, assignment.ArtifactID)
			}
			if _, exists := used[assignment.ArtifactID]; exists {
				return fmt.Errorf("artifact_id %d is assigned more than once", assignment.ArtifactID)
			}
			used[assignment.ArtifactID] = struct{}{}
		}
	}
	return nil
}

func (request OptimizerRequest) validatePolicies(artifacts map[int64]Artifact, theory bool) error {
	policy := request.Legality
	if theory {
		if !policy.TheorySearch || policy.FixedFourPiece || policy.FixedSetPackages || policy.MaxOffSetPiecesPerWearer != 0 || !policy.GloballyUniqueArtifactIDs || policy.DefaultMinimumRarity != 5 {
			return fmt.Errorf("legality policy does not match Theory v1")
		}
	} else {
		if policy.TheorySearch || policy.FixedFourPiece == policy.FixedSetPackages || policy.MaxOffSetPiecesPerWearer != 1 || !policy.GloballyUniqueArtifactIDs || policy.DefaultMinimumRarity != 5 {
			return fmt.Errorf("legality policy does not match Selected v1")
		}
		for _, wearer := range request.Wearers {
			if policy.FixedFourPiece && len(wearer.SetRequirements()) != 1 {
				return fmt.Errorf("fixed_four_piece policy cannot contain a 2+2 package")
			}
		}
	}
	if policy.AuthorizedLowerRarityArtifactIDs == nil {
		return fmt.Errorf("legality.authorized_lower_rarity_artifact_ids must be an array")
	}
	if err := validateSortedUniqueInt64("legality.authorized_lower_rarity_artifact_ids", policy.AuthorizedLowerRarityArtifactIDs); err != nil {
		return err
	}
	authorized := make(map[int64]struct{}, len(policy.AuthorizedLowerRarityArtifactIDs))
	for _, id := range policy.AuthorizedLowerRarityArtifactIDs {
		artifact, ok := artifacts[id]
		if !ok {
			return fmt.Errorf("authorized lower-rarity artifact_id %d is unknown", id)
		}
		if artifact.Rarity >= policy.DefaultMinimumRarity {
			return fmt.Errorf("artifact_id %d does not require lower-rarity authorization", id)
		}
		authorized[id] = struct{}{}
	}
	for id, artifact := range artifacts {
		if artifact.Rarity < policy.DefaultMinimumRarity {
			if _, ok := authorized[id]; !ok {
				return fmt.Errorf("artifact_id %d is below default rarity without authorization", id)
			}
		}
	}
	if request.Stochastic.Mode != "equal_weight_fixed_panel_v1" {
		return fmt.Errorf("unsupported stochastic.mode %q", request.Stochastic.Mode)
	}
	if len(request.Stochastic.Seeds) == 0 {
		return fmt.Errorf("stochastic.seeds must not be empty")
	}
	if err := validateSortedUniqueUint64("stochastic.seeds", request.Stochastic.Seeds); err != nil {
		return err
	}
	if len(request.Stochastic.Seeds) == 1 {
		if err := validateSHA256("stochastic.topology_stability_proof_sha256", request.Stochastic.TopologyStabilityProofSHA256, false); err != nil {
			return fmt.Errorf("one-trace mode requires topology proof: %w", err)
		}
	} else if request.Stochastic.TopologyStabilityProofSHA256 != "" {
		return fmt.Errorf("topology proof is allowed only for one-trace mode")
	}
	if request.Budgets.ProductTimeoutMS <= 0 || request.Budgets.DevelopmentTimeoutMS < request.Budgets.ProductTimeoutMS {
		return fmt.Errorf("budgets must be positive and development must cover product")
	}
	if request.Finalists != nil {
		if err := validateToken("finalists.policy_id", request.Finalists.PolicyID); err != nil {
			return err
		}
		if request.Finalists.MaxCandidates <= 0 || request.Finalists.Iterations <= 0 {
			return fmt.Errorf("finalist counts must be positive")
		}
	}
	if request.Cancellation.Mode != "process_interrupt_v1" {
		return fmt.Errorf("unsupported cancellation.mode %q", request.Cancellation.Mode)
	}
	return nil
}
