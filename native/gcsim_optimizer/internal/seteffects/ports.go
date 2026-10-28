package seteffects

// Experimental guide-input envelope from the isolated observer. Not accepted
// from the UI and not installed yet. The sidecar must bind the exact member;
// no numeric-value matching or inference from a displayed reaction actor.
import (
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"math"
	"math/big"
	"sort"
	"strconv"
)

type EffectInput = contracts.EffectInput
type InputEnvelope struct {
	SchemaVersion int           `json:"schema_version"`
	MemberSHA256  string        `json:"member_sha256"`
	Inputs        []EffectInput `json:"inputs"`
}
type InputFeature struct {
	EffectID           string   `json:"effect_id"`
	TermIndex          int      `json:"term_index"`
	MatchedReads       int      `json:"matched_reads"`
	UnknownFilterReads int      `json:"unknown_filter_reads"`
	IncrementDPS       *float64 `json:"increment_dps,omitempty"`
	Limitations        []string `json:"limitations"`
}
type InputProbe struct {
	program         *formula.InterventionProgram
	inputs          []EffectInput
	zero            []float64
	coordinates     []string
	baseline, scale float64
}

func NewInputProbe(member contracts.IRSeedMember, owners []string, envelope InputEnvelope) (*InputProbe, error) {
	sha, e := contracts.CanonicalSHA256(member)
	if e != nil {
		return nil, e
	}
	if envelope.SchemaVersion != 1 || envelope.MemberSHA256 != sha {
		return nil, fmt.Errorf("effect inputs belong to another graph")
	}
	known := map[string]bool{}
	for _, owner := range owners {
		known[owner] = true
	}
	coords := []string{}
	seen := map[string]bool{}
	for _, node := range member.Nodes {
		if node.Operation == "artifact_stat" && !seen[node.Coordinate] {
			seen[node.Coordinate] = true
			coords = append(coords, node.Coordinate)
		}
	}
	sort.Strings(coords)
	nodes := []uint32{}
	for _, input := range envelope.Inputs {
		if input.EventID == "" || input.Kind == "" || !known[input.Owner] || input.AttackTag == "" {
			return nil, fmt.Errorf("incomplete effect input ownership")
		}
		nodes = append(nodes, input.NodeID)
	}
	program, e := formula.CompileInterventions(member, owners, coords, nodes)
	if e != nil {
		return nil, e
	}
	values := program.ReferenceInputs()
	for _, input := range envelope.Inputs {
		observed, e := strconv.ParseFloat(input.Observed, 64)
		if e != nil || !finite(observed) || math.Abs(observed-values[input.NodeID]) > 1e-9*math.Max(1, math.Abs(observed)) {
			return nil, fmt.Errorf("effect input observed value differs")
		}
	}
	p := &InputProbe{program: program, inputs: append([]EffectInput(nil), envelope.Inputs...), zero: make([]float64, len(coords)), scale: 1000 / float64(member.DurationMS)}
	base, e := program.Evaluate(p.zero, nil)
	if e != nil {
		return nil, e
	}
	p.baseline = base.Damage
	p.coordinates = coords
	return p, nil
}

func (p *InputProbe) Feature(d Description, r Recipe, index int, wearer string, tags map[string]int) (InputFeature, error) {
	out := InputFeature{EffectID: r.Effect.ID, TermIndex: index, Limitations: []string{"old_context_increment_not_replacement", "activation_stacking_and_schedule_unverified"}}
	if p == nil || index < 0 || index >= len(r.Terms) {
		return out, fmt.Errorf("invalid input feature")
	}
	term := r.Terms[index]
	if r.Effect.Kind != "reaction_bonus" || (r.RecipientScope != "owner" && r.RecipientScope != "team_iteration_member") || term.Constant == "" {
		out.Limitations = append(out.Limitations, "input_kind_recipient_or_amount_unresolved")
		return out, nil
	}
	if r.RecipientScope == "team_iteration_member" {
		out.Limitations = append(out.Limitations, "team_recipient_eligibility_unverified")
	}
	value, ok := new(big.Rat).SetString(term.Constant)
	if !ok {
		return out, fmt.Errorf("invalid source amount")
	}
	amount, _ := value.Float64()
	if !finite(amount) {
		return out, fmt.Errorf("nonfinite source amount")
	}
	offsets := map[uint32]float64{}
	for _, input := range p.inputs {
		if input.Kind != r.Effect.Kind || (r.RecipientScope == "owner" && input.Owner != wearer) {
			continue
		}
		state := d.TermChannelApplicability(term, input.AttackTag, tags)
		if state == Excluded {
			continue
		}
		offsets[input.NodeID] = amount
		out.MatchedReads++
		if state == Unknown {
			out.UnknownFilterReads++
		}
	}
	if len(offsets) == 0 {
		out.Limitations = append(out.Limitations, "no_matching_observed_read_not_global_zero")
		return out, nil
	}
	got, e := p.program.Evaluate(p.zero, offsets)
	if e != nil {
		return out, e
	}
	gain := (got.Damage - p.baseline) * p.scale
	out.IncrementDPS = &gain
	return out, nil
}
