package contracts

// Neutral no-set capture ABI for the approved event/parametric overhaul (trace
// handoff section 2). Observation is not counterfactual completeness. Unknown
// fields/modes and truncated tapes cannot certify set activation or hard bounds.
type EventValue struct {
	Kind    string                `json:"kind"`
	Type    string                `json:"type,omitempty"`
	Number  float64               `json:"number,omitempty"`
	Text    string                `json:"text,omitempty"`
	Boolean bool                  `json:"boolean,omitempty"`
	Fields  map[string]EventValue `json:"fields,omitempty"`
	Items   []EventValue          `json:"items,omitempty"`
}
type EventProvider struct {
	Known      bool   `json:"known"`
	Kind       string `json:"kind"`
	Key        string `json:"key"`
	OwnerIndex int    `json:"owner_index"`
	PieceCount int    `json:"piece_count"`
}
type CombatEvent struct {
	Order         uint64        `json:"order"`
	EndOrder      uint64        `json:"end_order"`
	ParentOrder   uint64        `json:"parent_order"`
	Frame         int           `json:"frame"`
	Event         int           `json:"event"`
	Active        int           `json:"active"`
	StateSequence int           `json:"state_sequence"`
	Provider      EventProvider `json:"provider"`
	Arguments     []EventValue  `json:"arguments"`
}
type CombatEventLedger struct {
	Events    []CombatEvent `json:"events"`
	Truncated bool          `json:"truncated"`
}
type NeutralCharacter struct {
	Facts map[string]EventValue `json:"facts,omitempty"`
	Index int                   `json:"index"`
	Key   string                `json:"key"`
	Base  EventValue            `json:"base"`
	Stats EventValue            `json:"stats"`
}
type NeutralContext struct {
	DurationFrames int                `json:"duration_frames"`
	NoSets         bool               `json:"no_sets"`
	Moonsign       int                `json:"moonsign"`
	Active         int                `json:"active"`
	Characters     []NeutralCharacter `json:"characters"`
}
type NeutralInputPoint struct {
	StatKeys    *[]string `json:"stat_keys,omitempty"`
	Frame       int       `json:"frame"`
	Order       uint64    `json:"order"`
	HitFrame    int       `json:"hit_frame"`
	HitOrder    uint64    `json:"hit_order"`
	AttackOrder uint64    `json:"attack_order"`
	HitID       uint64    `json:"hit_id"`
	TargetKey   int       `json:"target_key"`
	EventID     string    `json:"event_id,omitempty"`
	Mode        string    `json:"mode"`
	AttackTag   string    `json:"attack_tag,omitempty"`
	Element     string    `json:"element,omitempty"`
}
type NeutralStatInput struct {
	NodeID uint32            `json:"node_id"`
	Kind   string            `json:"kind"`
	Owner  string            `json:"owner"`
	Stat   string            `json:"stat"`
	Point  NeutralInputPoint `json:"point"`
}
type NeutralStatePoint struct {
	Order  uint64 `json:"order"`
	Frame  int    `json:"frame"`
	Kind   string `json:"kind"`
	Owner  int    `json:"owner"`
	Key    string `json:"key"`
	Expiry *int   `json:"expiry,omitempty"`
}
type NeutralHitPoint struct {
	TargetKeys []string          `json:"target_keys"`
	Attack     *EventValue       `json:"attack,omitempty"`
	HitID      uint64            `json:"hit_id"`
	Actor      int               `json:"actor"`
	Point      NeutralInputPoint `json:"point"`
}
type NeutralInputs struct {
	Reads         []NeutralReadRoot    `json:"reads"`
	ReadsComplete bool                 `json:"reads_complete"`
	Hitlag        *NeutralHitlagLedger `json:"hitlag,omitempty"`
	SchemaVersion int                  `json:"schema_version"`
	Context       NeutralContext       `json:"context"`
	Ledger        CombatEventLedger    `json:"ledger"`
	States        []NeutralStatePoint  `json:"states"`
	Stats         []NeutralStatInput   `json:"stats"`
	Hits          []NeutralHitPoint    `json:"hits"`
	Uncertainty   []string             `json:"uncertainty"`
	World         *NeutralWorldLedger  `json:"world,omitempty"`
	Effects       []NeutralEffectPoint `json:"effects"`
}

type NeutralReadRoot struct {
	NodeID      uint32            `json:"node_id"`
	Owner       string            `json:"owner"`
	Stat        string            `json:"stat"`
	Observed    string            `json:"observed"`
	Point       NeutralInputPoint `json:"point"`
	Projection  bool              `json:"projection"`
	Uncertainty []string          `json:"uncertainty"`
}

type NeutralHitlagEvent struct {
	Order     uint64 `json:"order"`
	Frame     int    `json:"frame"`
	Owner     int    `json:"owner"`
	Target    int    `json:"target"`
	Extension int    `json:"extension"`
}
type NeutralHitlagLedger struct {
	Complete bool                 `json:"complete"`
	Events   []NeutralHitlagEvent `json:"events"`
}

type NeutralEffectPoint struct {
	EventID string      `json:"event_id"`
	Order   uint64      `json:"order"`
	Frame   int         `json:"frame"`
	Input   *EventValue `json:"input,omitempty"`
}

type NeutralModifierIdentity struct {
	Owner  int    `json:"owner"`
	Key    string `json:"key"`
	Expiry int    `json:"expiry"`
}
type NeutralWorldState struct {
	Facts     *EventValue               `json:"facts,omitempty"`
	Targets   []EventValue              `json:"targets,omitempty"`
	Order     uint64                    `json:"order"`
	Frame     int                       `json:"frame"`
	Active    int                       `json:"active"`
	Modifiers []NeutralModifierIdentity `json:"modifiers"`
}
type NeutralWorldLedger struct {
	Complete bool                `json:"complete"`
	States   []NeutralWorldState `json:"states"`
}
