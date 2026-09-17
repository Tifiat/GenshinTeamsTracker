package contracts

const EffectInputsCapability = "gtt_effect_inputs_v1"

// Neutral observer ABI: typed graph locations, not set ranking or gameplay rules.
type EffectInput struct {
	EventID   string `json:"event_id"`
	NodeID    uint32 `json:"node_id"`
	Kind      string `json:"kind"`
	Owner     string `json:"owner"`
	AttackTag string `json:"attack_tag"`
	Observed  string `json:"observed"`
}

type ResistanceInput struct {
	NodeID     uint32 `json:"node_id"`
	HitID      uint64 `json:"hit_id"`
	TargetKey  int    `json:"target_key"`
	Element    string `json:"element"`
	Resistance string `json:"resistance"`
	Observed   string `json:"observed"`
}

type EffectInputsOutput struct {
	SchemaVersion            int               `json:"schema_version"`
	Capability               string            `json:"capability"`
	MemberContentSHA256      string            `json:"member_content_sha256"`
	ContextSHA256            string            `json:"context_sha256"`
	InputConfigSHA256        string            `json:"input_config_sha256"`
	SourceConfigSHA256       string            `json:"source_config_sha256"`
	SourceManifestBodySHA256 string            `json:"source_manifest_body_sha256"`
	Seed                     string            `json:"seed"`
	CharacterKeys            []string          `json:"character_keys"`
	EffectInputs             []EffectInput     `json:"effect_inputs"`
	ResistanceInputs         []ResistanceInput `json:"resistance_inputs"`
}
