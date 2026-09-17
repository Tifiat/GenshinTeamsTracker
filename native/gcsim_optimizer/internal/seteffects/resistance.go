package seteffects

import (
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"math"
	"math/big"
	"sort"
	"strconv"
)

// The adapter binds these ports at the actual multiplication sites, not by
// graph constant value. Raw resistance is observed at that hit, not a team-wide
// average. Curves are separately extracted from the bound engine source.
type ResistanceInput = contracts.ResistanceInput
type ResistanceEnvelope struct {
	SchemaVersion int               `json:"schema_version"`
	MemberSHA256  string            `json:"member_sha256"`
	Inputs        []ResistanceInput `json:"inputs"`
}
type ResistanceProbe struct {
	program                    *formula.InterventionProgram
	inputs                     []ResistanceInput
	resistance, observed, zero []float64
	curve                      ScalarSlice
	baseline, scale            float64
	coordinates                []string
}

func NewResistanceProbe(member contracts.IRSeedMember, owners []string, envelope ResistanceEnvelope, curves []ScalarSlice) (*ResistanceProbe, error) {
	sha, e := contracts.CanonicalSHA256(member)
	if e != nil {
		return nil, e
	}
	if envelope.SchemaVersion != 1 || envelope.MemberSHA256 != sha || len(curves) == 0 {
		return nil, fmt.Errorf("resistance graph/source binding missing")
	}
	for _, curve := range curves {
		if curve.SourceSHA256 == "" || curve.SourceSHA256 != curves[0].SourceSHA256 || curve.RecipeSHA256 != curves[0].RecipeSHA256 {
			return nil, fmt.Errorf("ambiguous contextual curves")
		}
	}
	coords := []string{}
	seen := map[string]bool{}
	for _, n := range member.Nodes {
		if n.Operation == "artifact_stat" && !seen[n.Coordinate] {
			seen[n.Coordinate] = true
			coords = append(coords, n.Coordinate)
		}
	}
	sort.Strings(coords)
	nodes := []uint32{}
	hits := map[uint64]bool{}
	p := &ResistanceProbe{inputs: append([]ResistanceInput(nil), envelope.Inputs...), curve: curves[0], zero: make([]float64, len(coords)), scale: 1000 / float64(member.DurationMS)}
	for _, in := range p.inputs {
		if in.HitID == 0 || hits[in.HitID] || in.Element == "" {
			return nil, fmt.Errorf("ambiguous resistance ownership")
		}
		hits[in.HitID] = true
		r, e := strconv.ParseFloat(in.Resistance, 64)
		if e != nil || !finite(r) {
			return nil, fmt.Errorf("invalid resistance")
		}
		value, e := strconv.ParseFloat(in.Observed, 64)
		if e != nil || !finite(value) {
			return nil, fmt.Errorf("invalid resistance multiplier")
		}
		expected, e := p.curve.Evaluate(r)
		if e != nil || math.Abs(expected-value) > 1e-10*math.Max(1, math.Abs(value)) {
			return nil, fmt.Errorf("source curve disagrees with observed multiplier")
		}
		p.resistance = append(p.resistance, r)
		p.observed = append(p.observed, value)
		nodes = append(nodes, in.NodeID)
	}
	p.program, e = formula.CompileInterventions(member, owners, coords, nodes)
	if e != nil {
		return nil, e
	}
	values := p.program.ReferenceInputs()
	for i, in := range p.inputs {
		if math.Abs(values[in.NodeID]-p.observed[i]) > 1e-10*math.Max(1, math.Abs(p.observed[i])) {
			return nil, fmt.Errorf("resistance port does not match graph")
		}
	}
	result, e := p.program.Evaluate(p.zero, nil)
	if e != nil {
		return nil, e
	}
	p.baseline = result.Damage
	p.coordinates = coords
	return p, nil
}

// Increment is an old-context intervention, NOT a real set replacement. The
// amount/element come from a source recipe (or an explicit synthetic test).
func (p *ResistanceProbe) Increment(element string, amount float64) (float64, int, error) {
	if p == nil || element == "" || !finite(amount) {
		return 0, 0, fmt.Errorf("invalid resistance intervention")
	}
	offsets := map[uint32]float64{}
	for i, in := range p.inputs {
		if in.Element != element {
			continue
		}
		value, e := p.curve.Evaluate(p.resistance[i] + amount)
		if e != nil {
			return 0, 0, e
		}
		offsets[in.NodeID] = value - p.observed[i]
	}
	result, e := p.program.Evaluate(p.zero, offsets)
	if e != nil {
		return 0, 0, e
	}
	return (result.Damage - p.baseline) * p.scale, len(offsets), nil
}

func (p *ResistanceProbe) Feature(r Recipe, index int, elements map[string]string) (InputFeature, error) {
	out := InputFeature{EffectID: r.Effect.ID, TermIndex: index, Limitations: []string{"old_context_increment_not_replacement", "activation_duration_target_and_stacking_unverified"}}
	if index < 0 || index >= len(r.Terms) {
		return out, fmt.Errorf("invalid resistance term")
	}
	term := r.Terms[index]
	if r.Effect.Kind != "resistance" || term.Coordinate != "Value" || term.Constant == "" {
		out.Limitations = append(out.Limitations, "not_constant_resistance_amount")
		return out, nil
	}
	element := ""
	for _, f := range r.Effect.Fields {
		if f.Name == "Ele" && f.Value.Kind == "qualified" {
			element = elements[f.Value.Symbol]
		}
	}
	if element == "" {
		out.Limitations = append(out.Limitations, "source_element_unresolved")
		return out, nil
	}
	rat, ok := new(big.Rat).SetString(term.Constant)
	if !ok {
		return out, fmt.Errorf("invalid source resistance amount")
	}
	amount, _ := rat.Float64()
	gain, n, e := p.Increment(element, amount)
	if e != nil {
		return out, e
	}
	out.MatchedReads = n
	if n == 0 {
		out.Limitations = append(out.Limitations, "no_matching_observed_read_not_global_zero")
		return out, nil
	}
	out.IncrementDPS = &gain
	return out, nil
}
