package seteffects

// R1 retains the ordinary neutral arithmetic. A missing package response is
// never an assertion of no effect: the source slot is left untouched and the
// candidate remains an uncertain guide for ordinary verification.
import (
	"fmt"
	"sort"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
)

type R1FrozenPort struct {
	Package, Seed, Key, State, Reason string
	Member, Owner, Dimension          int
	SourceNode                        uint32
	SourceValue                       float64
	PackageAnchorValue                *float64 `json:",omitempty"`
	SourceSlotPreserved               bool
}
type R1FrozenStats struct {
	FallbackReplays, AnchorPorts, ReferencePorts, OmittedRecords int
	Records                                                      []R1FrozenPort
	UnmappedPackageReasons                                       []string
	PackageGuides                                                []R1PackageGuide
}
type R1PackageGuide struct {
	Package, State string
	Reasons        []string
}

func (b *NeutralBinding) EnableR1FrozenResiduals() { b.r1Frozen = true }
func (b *NeutralBinding) R1FrozenStats() R1FrozenStats {
	out := b.r1Stats
	out.Records = append([]R1FrozenPort(nil), out.Records...)
	out.UnmappedPackageReasons = append([]string(nil), out.UnmappedPackageReasons...)
	out.PackageGuides = append([]R1PackageGuide(nil), out.PackageGuides...)
	return out
}

func (b *NeutralBinding) r1Freeze(choices []RuleChoice, out NeutralExpressions) NeutralExpressions {
	if !b.r1Frozen || out.Complete() {
		return out
	}
	for _, boundary := range out.MechanicBoundaries {
		if boundary.Kind == contracts.MechanicInvalidOperation {
			return out
		}
	}
	if len(out.Effects) == 0 && len(b.keys) == 0 {
		// There is no owned source slot to associate with this operation.
		b.r1RememberReasons(choices, out.Boundaries)
		out.Uncertainty = append(out.Uncertainty, "r1_unmapped_package_guide_reference")
		out.Boundaries = nil
		out.r1Frozen = true
		return out
	}
	missing := 0
	for _, key := range b.keys {
		if out.Effects[key] == nil {
			missing++
		}
	}
	if missing == 0 {
		b.r1RememberReasons(choices, out.Boundaries)
		for _, reason := range out.Boundaries {
			out.Uncertainty = append(out.Uncertainty, "r1_unmapped_package_guide:"+reason)
		}
		out.Boundaries = nil
		out.r1Frozen = true
		return out
	}
	concrete := b.EvaluatePackages(choices)
	return b.r1FreezeConcrete(choices, out, concrete)
}

func (b *NeutralBinding) r1FreezeConcrete(choices []RuleChoice, out NeutralExpressions, concrete NeutralEffectVector) NeutralExpressions {
	out.MechanicBoundaries = append(out.MechanicBoundaries, concrete.MechanicBoundaries...)
	for _, boundary := range concrete.MechanicBoundaries {
		if boundary.Kind == contracts.MechanicInvalidOperation {
			out.Boundaries = append(out.Boundaries, boundary.Reason)
			return out
		}
	}
	out.Uncertainty = append(out.Uncertainty, concrete.Uncertainty...)
	if len(concrete.Values) != len(b.keys) || len(concrete.Known) != len(b.keys) {
		return out
	}
	b.r1Stats.FallbackReplays++
	b.r1RememberReasons(choices, append(append([]string(nil), out.Boundaries...), concrete.Boundaries...))
	if out.Effects == nil {
		out.Effects = map[string]*formula.InputExpression{}
	}
	for mi, member := range b.members {
		for _, port := range member.ports {
			dim := port.dimension
			key := b.keys[dim]
			if out.Effects[key] != nil {
				continue
			}
			source := b.ports[dim]
			if source.Member != mi || source.Key != key || source.NodeID == 0 || !isRuleFinite(source.Observed) {
				out.Boundaries = append(out.Boundaries, "R1 invalid source-slot ownership")
				return out
			}
			record := R1FrozenPort{Package: ruleChoicesKey(choices), Seed: member.seed, Key: key, Member: mi, Owner: port.query.Owner, Dimension: dim, SourceNode: source.NodeID, SourceValue: source.Observed}
			if concrete.Known[dim] && isRuleFinite(concrete.Values[dim]) {
				value := concrete.Values[dim]
				out.Effects[key] = &formula.InputExpression{Operation: "constant", Value: value}
				record.State = "observed_package_anchor_frozen"
				record.PackageAnchorValue = &value
				record.Reason = "symbolic_dependency_unbound"
				b.r1Stats.AnchorPorts++
				out.Uncertainty = append(out.Uncertainty, "r1_observed_package_anchor_frozen")
			} else if concrete.Known[dim] {
				out.Boundaries = append(out.Boundaries, "R1 nonfinite package anchor")
				return out
			} else {
				// Effect inputs are ADDITIVE interventions on the original node.
				// No intervention leaves that source arithmetic/value in place; it
				// does not measure the unknown package's effect as zero.
				out.Effects[key] = &formula.InputExpression{Operation: "constant", Value: 0}
				record.State = "no_package_anchor_reference_guide"
				record.SourceSlotPreserved = true
				record.Reason = "concrete_package_response_unresolved"
				b.r1Stats.ReferencePorts++
				out.Uncertainty = append(out.Uncertainty, "r1_no_package_anchor_source_slot_preserved")
			}
			if len(b.r1Stats.Records) < 128 {
				b.r1Stats.Records = append(b.r1Stats.Records, record)
			} else {
				b.r1Stats.OmittedRecords++
			}
		}
	}
	for _, reason := range out.Boundaries {
		out.Uncertainty = append(out.Uncertainty, "r1_unresolved:"+reason)
	}
	out.Boundaries = nil
	out.r1Frozen = true
	// Preserve sparse symbolic expressions, using the existing region/constant
	// binder rather than rebuilding the full aggregate for each package.
	out.Constants = make([]float64, len(b.keys))
	out.SparseEffects = map[int]*formula.InputExpression{}
	for dim, key := range b.keys {
		x := out.Effects[key]
		if x == nil {
			out.Boundaries = append(out.Boundaries, fmt.Sprintf("R1 missing slot%d", dim))
			continue
		}
		if x.Operation == "constant" {
			out.Constants[dim] = x.Value
		} else {
			out.SparseEffects[dim] = x
		}
	}
	if len(out.SparseEffects) == 0 {
		out.SparseEffects = nil
	}
	sort.Strings(out.Uncertainty)
	compact := out.Uncertainty[:0]
	for _, reason := range out.Uncertainty {
		if len(compact) == 0 || compact[len(compact)-1] != reason {
			compact = append(compact, reason)
		}
	}
	out.Uncertainty = compact
	return out
}

func (b *NeutralBinding) r1RememberReasons(choices []RuleChoice, reasons []string) {
	if len(b.r1Stats.PackageGuides) < 64 {
		b.r1Stats.PackageGuides = append(b.r1Stats.PackageGuides, R1PackageGuide{Package: ruleChoicesKey(choices), State: "unresolved_operation_mapping_not_certified", Reasons: append([]string(nil), reasons...)})
	}
	for _, reason := range reasons {
		found := false
		for _, prior := range b.r1Stats.UnmappedPackageReasons {
			if prior == reason {
				found = true
				break
			}
		}
		if !found && len(b.r1Stats.UnmappedPackageReasons) < 64 {
			b.r1Stats.UnmappedPackageReasons = append(b.r1Stats.UnmappedPackageReasons, reason)
		}
	}
}
