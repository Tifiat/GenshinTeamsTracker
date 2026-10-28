package setcontext

// Scratch-only, same-schedule Marechaussee Hunter probe. This deliberately uses
// the observed event tape through ReplayNeutralRules; it is not a counterfactual
// health model and must not be wired into the production Resolve path.
import (
	"fmt"
	"math"
	"strings"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

const researchHunterFrozenHealUncertainty = "research_marechausseehunter_observed_heal_schedule_frozen"

// Only the saved Chasca control's original sets and the three announced
// substitutions are allowed here. The active sources for these sets have no
// other heal/HP-drain callbacks; Hunter is the only health-event consumer in
// this bounded family.
var researchHunterAllowedSetKeys = map[string]bool{
	"marechausseehunter":          true,
	"goldentroupe":                true,
	"tenacityofthemillelith":      true,
	"obsidiancodex":               true,
	"scrolloftheheroofcindercity": true,
	"noblesseoblige":              true,
}

// ResearchResolveHunterObservedSchedule binds the captured heal-event values
// to the candidate's set effects while keeping the captured damage formula
// parametric in candidate artifact stats. It is restricted to Chasca Hunter4
// and the fixed experiment's other set choices. Every package is still replayed
// and validated by the active source catalog; any unsupported/unknown effect
// remains a boundary. The heal activation schedule itself is frozen to the
// no-set capture, so the returned handle is explicitly approximate.
func (m *NeutralModel) ResearchResolveHunterObservedSchedule(target *Context) (*Handle, []string, error) {
	if m == nil || m.origin == nil || target == nil || !m.origin.SameFrame(target) || m.binding == nil {
		return nil, nil, fmt.Errorf("research Hunter probe requires the captured frame")
	}
	choices := []seteffects.RuleChoice{}
	hunterCount := 0
	for _, actor := range target.actors {
		owner, ok := m.owners[actor]
		if !ok {
			return nil, nil, fmt.Errorf("neutral target changed owner identity")
		}
		for _, set := range target.Sets(actor) {
			if strings.TrimSpace(set.Parameters) != "" {
				return nil, []string{"set_parameters_not_bound:" + actor + ":" + set.UID}, nil
			}
			if !researchHunterAllowedSetKeys[set.UID] || set.Count != 4 {
				return nil, []string{"research_hunter_package_outside_fixed_family:" + actor + ":" + set.UID}, nil
			}
			if set.UID == "marechausseehunter" {
				if actor != "chasca" {
					return nil, []string{"research_hunter_wearer_must_be_chasca"}, nil
				}
				hunterCount++
			}
			choices = append(choices, seteffects.RuleChoice{Owner: owner, Key: set.UID, Pieces: set.Count})
		}
	}
	if hunterCount != 1 {
		return nil, []string{"research_hunter_requires_one_chasca_four_piece_package"}, nil
	}

	m.stats.Requests++
	started := time.Now()
	values := m.binding.EvaluatePackages(choices)
	m.stats.RuleSeconds += time.Since(started).Seconds()
	if !values.Complete() {
		m.stats.Unavailable++
		return nil, append([]string(nil), values.Boundaries...), nil
	}
	program, err := m.bindConstants(values.Values)
	if err != nil {
		return nil, nil, err
	}
	uncertainty := append([]string(nil), values.Uncertainty...)
	uncertainty = append(uncertainty, researchHunterFrozenHealUncertainty)
	return m.contextView(target, program, uncertainty)
}

// ResearchHunterLedgerRow preserves only source-relevant, observed heal/drain
// operands needed to inspect Hunter trigger coverage. Missing operands remain
// nil; no event identity or health result is inferred from absent fields.
type ResearchHunterLedgerRow struct {
	Order       uint64   `json:"order"`
	EndOrder    uint64   `json:"end_order"`
	Frame       int      `json:"frame"`
	Active      int      `json:"active"`
	EventID     int      `json:"event_id"`
	Kind        string   `json:"kind"`
	ActorIndex  *int     `json:"actor_index,omitempty"`
	TargetIndex *int     `json:"target_index,omitempty"`
	Amount      *float64 `json:"amount,omitempty"`
	Overheal    *float64 `json:"overheal,omitempty"`
	RawAmount   *float64 `json:"raw_amount,omitempty"`
}

type ResearchHunterLedgerMember struct {
	Seed                string                    `json:"seed"`
	ContextSHA256       string                    `json:"context_sha256"`
	EngineBindingSHA256 string                    `json:"engine_binding_sha256"`
	DurationFrames      int                       `json:"duration_frames"`
	LedgerTruncated     bool                      `json:"ledger_truncated"`
	HitlagComplete      bool                      `json:"hitlag_complete"`
	ChascaOwnerIndex    int                       `json:"chasca_owner_index"`
	HealthEventRows     []ResearchHunterLedgerRow `json:"health_event_rows"`
}

// ResearchHunterScheduleLedger reads the exact neutral capture retained by the
// caller's Handle before ResearchNeutralFactory transfers its private copy.
// Rows are raw observations in ledger order; callers can reconstruct trigger
// frames and stack-window coverage with the set's source rules and must carry
// the truncation/hitlag completeness flags into any uptime statement.
func (h *Handle) ResearchHunterScheduleLedger() ([]ResearchHunterLedgerMember, error) {
	if h == nil || h.compiled == nil || h.compiled.effectCapture == nil {
		return nil, fmt.Errorf("research Hunter ledger requires retained neutral capture")
	}
	capture := h.compiled.effectCapture
	out := make([]ResearchHunterLedgerMember, 0, len(capture.Effects))
	for _, sidecar := range capture.Effects {
		n := sidecar.Neutral
		if n == nil || !n.Context.NoSets {
			return nil, fmt.Errorf("research Hunter ledger requires no-set neutral members")
		}
		chasca := -1
		for _, actor := range n.Context.Characters {
			if actor.Key == "chasca" {
				chasca = actor.Index
				break
			}
		}
		if chasca < 0 {
			return nil, fmt.Errorf("captured neutral member has no Chasca owner")
		}
		member := ResearchHunterLedgerMember{
			Seed: sidecar.Seed, ContextSHA256: sidecar.ContextSHA256,
			EngineBindingSHA256: capture.EngineBindingSHA256,
			DurationFrames:      n.Context.DurationFrames, LedgerTruncated: n.Ledger.Truncated,
			HitlagComplete:   n.Hitlag != nil && n.Hitlag.Complete,
			ChascaOwnerIndex: chasca, HealthEventRows: []ResearchHunterLedgerRow{},
		}
		for _, event := range n.Ledger.Events {
			if len(event.Arguments) == 0 || event.Arguments[0].Kind != "object" {
				continue
			}
			argType := strings.TrimPrefix(event.Arguments[0].Type, "*")
			row := ResearchHunterLedgerRow{Order: event.Order, EndOrder: event.EndOrder, Frame: event.Frame, Active: event.Active, EventID: event.Event}
			switch {
			case strings.HasSuffix(argType, "pkg/core/info.HealInfo"):
				row.Kind = "heal"
				if len(event.Arguments) > 1 {
					row.TargetIndex = researchHunterInt(event.Arguments[1])
				}
				if len(event.Arguments) > 2 {
					row.Amount = researchHunterFloat(event.Arguments[2])
				}
				if len(event.Arguments) > 3 {
					row.Overheal = researchHunterFloat(event.Arguments[3])
				}
				if len(event.Arguments) > 4 {
					row.RawAmount = researchHunterFloat(event.Arguments[4])
				}
			case strings.HasSuffix(argType, "pkg/core/info.DrainInfo"):
				row.Kind = "drain"
				if index, ok := event.Arguments[0].Fields["ActorIndex"]; ok {
					row.ActorIndex = researchHunterInt(index)
				}
				if amount, ok := event.Arguments[0].Fields["Amount"]; ok {
					row.Amount = researchHunterFloat(amount)
				}
			default:
				continue
			}
			member.HealthEventRows = append(member.HealthEventRows, row)
		}
		out = append(out, member)
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("neutral capture has no seed members")
	}
	return out, nil
}

func researchHunterInt(value contracts.EventValue) *int {
	if value.Kind != "number" || math.IsNaN(value.Number) || math.IsInf(value.Number, 0) || math.Trunc(value.Number) != value.Number {
		return nil
	}
	x := int(value.Number)
	return &x
}

func researchHunterFloat(value contracts.EventValue) *float64 {
	if value.Kind != "number" || math.IsNaN(value.Number) || math.IsInf(value.Number, 0) {
		return nil
	}
	x := value.Number
	return &x
}
