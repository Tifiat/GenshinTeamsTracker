// Package contracts owns the versioned process boundary of the standalone GTT
// optimizer. It deliberately contains no GCSIM, search, database, or UI types.
package contracts

const (
	SchemaVersion = 1

	RequestSchemaKind  = "gtt_gcsim_optimizer_request_v1"
	ProgressSchemaKind = "gtt_gcsim_optimizer_progress_v1"
	CompactIRKind      = "gtt_gcsim_optimizer_compact_ir_v1"
	ResultSchemaKind   = "gtt_gcsim_optimizer_result_v1"
	StrategyID         = "gtt_gcsim_optimizer_go_v1"
)

type SourceText struct {
	Text   string `json:"text"`
	SHA256 string `json:"sha256"`
}

type EngineBinding struct {
	BinaryPath           string   `json:"binary_path"`
	ArtifactSHA256       string   `json:"artifact_sha256"`
	BindingSHA256        string   `json:"binding_sha256"`
	SourceManifestSHA256 string   `json:"source_manifest_sha256"`
	PatchManifestSHA256  string   `json:"patch_manifest_sha256"`
	Capabilities         []string `json:"capabilities"`
}

type RunContext struct {
	PreparedConfig     SourceText `json:"prepared_config"`
	Rotation           SourceText `json:"rotation"`
	Target             SourceText `json:"target"`
	ContextSHA256      string     `json:"context_sha256"`
	TraceContextSHA256 string     `json:"trace_context_sha256"`
}

type ArtifactAssignment struct {
	WearerKey  string `json:"wearer_key"`
	Slot       string `json:"slot"`
	ArtifactID int64  `json:"artifact_id"`
}

type Wearer struct {
	WearerKey        string               `json:"wearer_key"`
	WeaponKey        string               `json:"weapon_key"`
	SelectedSetUID   string               `json:"selected_set_uid"`
	CurrentArtifacts []ArtifactAssignment `json:"current_artifacts"`
}

type StatValue struct {
	Key   string `json:"key"`
	Value string `json:"value"`
}

type Artifact struct {
	ArtifactID int64       `json:"artifact_id"`
	Slot       string      `json:"slot"`
	SetUID     string      `json:"set_uid"`
	Rarity     int         `json:"rarity"`
	Level      int         `json:"level"`
	MainStat   StatValue   `json:"main_stat"`
	Substats   []StatValue `json:"substats"`
}

type LegalityPolicy struct {
	FixedFourPiece                   bool    `json:"fixed_four_piece"`
	MaxOffSetPiecesPerWearer         int     `json:"max_off_set_pieces_per_wearer"`
	GloballyUniqueArtifactIDs        bool    `json:"globally_unique_artifact_ids"`
	DefaultMinimumRarity             int     `json:"default_minimum_rarity"`
	AuthorizedLowerRarityArtifactIDs []int64 `json:"authorized_lower_rarity_artifact_ids"`
}

type StochasticPolicy struct {
	Mode                         string   `json:"mode"`
	Seeds                        []uint64 `json:"seeds"`
	TopologyStabilityProofSHA256 string   `json:"topology_stability_proof_sha256,omitempty"`
}

type TimeBudgets struct {
	ProductTimeoutMS     int64 `json:"product_timeout_ms"`
	DevelopmentTimeoutMS int64 `json:"development_timeout_ms"`
}

type FinalistPolicy struct {
	PolicyID      string `json:"policy_id"`
	MaxCandidates int    `json:"max_candidates"`
	Iterations    int    `json:"iterations"`
}

type CancellationPolicy struct {
	Mode string `json:"mode"`
}

type OptimizerRequest struct {
	SchemaVersion int                `json:"schema_version"`
	SchemaKind    string             `json:"schema_kind"`
	StrategyID    string             `json:"strategy_id"`
	Engine        EngineBinding      `json:"engine"`
	Context       RunContext         `json:"context"`
	Wearers       []Wearer           `json:"wearers"`
	Artifacts     []Artifact         `json:"artifacts"`
	Legality      LegalityPolicy     `json:"legality"`
	Stochastic    StochasticPolicy   `json:"stochastic"`
	Budgets       TimeBudgets        `json:"budgets"`
	Finalists     *FinalistPolicy    `json:"finalists,omitempty"`
	Cancellation  CancellationPolicy `json:"cancellation"`
}

type IRInput struct {
	NodeID   uint32 `json:"node_id"`
	Relation string `json:"relation"`
}

type IRNode struct {
	NodeID     uint32    `json:"node_id"`
	Operation  string    `json:"operation"`
	Inputs     []IRInput `json:"inputs"`
	Value      string    `json:"value,omitempty"`
	Coordinate string    `json:"coordinate,omitempty"`
}

type IRChannel struct {
	ChannelID           string   `json:"channel_id"`
	Kind                string   `json:"kind"`
	ActorKey            string   `json:"actor_key"`
	AttackTag           string   `json:"attack_tag"`
	DamageType          string   `json:"damage_type"`
	RootNodeID          uint32   `json:"root_node_id"`
	HitCount            int      `json:"hit_count"`
	BaselineDamage      string   `json:"baseline_damage"`
	ResponseCoordinates []string `json:"response_coordinates"`
}

type IROpaqueBoundary struct {
	BoundaryID          string `json:"boundary_id"`
	NodeID              uint32 `json:"node_id"`
	ReasonCode          string `json:"reason_code"`
	BaselineDamage      string `json:"baseline_damage"`
	BaselineDamageShare string `json:"baseline_damage_share"`
}

type IRSeedMember struct {
	Seed             uint64             `json:"seed"`
	DurationMS       int64              `json:"duration_ms"`
	TopologySHA256   string             `json:"topology_sha256"`
	Nodes            []IRNode           `json:"nodes"`
	Channels         []IRChannel        `json:"channels"`
	OpaqueBoundaries []IROpaqueBoundary `json:"opaque_boundaries"`
}

type CompactIR struct {
	SchemaVersion       int            `json:"schema_version"`
	SchemaKind          string         `json:"schema_kind"`
	RequestSHA256       string         `json:"request_sha256"`
	EngineBindingSHA256 string         `json:"engine_binding_sha256"`
	ContextSHA256       string         `json:"context_sha256"`
	Members             []IRSeedMember `json:"members"`
}

type ProgressRecord struct {
	SchemaVersion         int    `json:"schema_version"`
	SchemaKind            string `json:"schema_kind"`
	RequestSHA256         string `json:"request_sha256"`
	Sequence              int64  `json:"sequence"`
	Stage                 string `json:"stage"`
	CompletedWork         int64  `json:"completed_work"`
	TotalWork             int64  `json:"total_work"`
	ElapsedMS             int64  `json:"elapsed_ms"`
	CancellationRequested bool   `json:"cancellation_requested"`
	CacheIdentitySHA256   string `json:"cache_identity_sha256,omitempty"`
}

type MeasuredResult struct {
	Iterations         int    `json:"iterations"`
	DPS                string `json:"dps"`
	StandardError      string `json:"standard_error"`
	EngineResultSHA256 string `json:"engine_result_sha256"`
}

type ResultError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

type RankedCandidateResult struct {
	Rank            int                  `json:"rank"`
	Artifacts       []ArtifactAssignment `json:"artifacts"`
	FormulaDPS      string               `json:"formula_dps"`
	Measured        MeasuredResult       `json:"measured"`
	FormulaResidual string               `json:"formula_residual"`
}

type OptimizerResult struct {
	SchemaVersion    int                     `json:"schema_version"`
	SchemaKind       string                  `json:"schema_kind"`
	RequestSHA256    string                  `json:"request_sha256"`
	CompactIRSHA256  string                  `json:"compact_ir_sha256,omitempty"`
	Status           string                  `json:"status"`
	Winner           []ArtifactAssignment    `json:"winner,omitempty"`
	Candidates       []RankedCandidateResult `json:"candidates,omitempty"`
	FormulaDPS       string                  `json:"formula_dps,omitempty"`
	Measured         *MeasuredResult         `json:"measured,omitempty"`
	FormulaResidual  string                  `json:"formula_residual,omitempty"`
	Warnings         []string                `json:"warnings"`
	DebugReceiptPath string                  `json:"debug_receipt_path,omitempty"`
	Error            *ResultError            `json:"error,omitempty"`
}
