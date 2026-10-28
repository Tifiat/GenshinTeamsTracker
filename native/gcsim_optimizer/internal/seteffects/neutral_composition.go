package seteffects

// Reuse independently replayed effect components ONLY after checking their
// observed read/write footprints, including typed stat reads and writes.
// Interacting components use joint replay. Resistance is transformed after summing raw changes,
// never by adding already-transformed damage factors. This is run-local bounded
// preparation; item scoring still executes only the reduced arithmetic program.
import (
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"sort"
	"strings"
)

type NeutralPreparationStats struct {
	FamilyHits, FamilyMisses, TwoPieceChoices, TwoPieceEffectFamilies                             int
	Requests, Replays, JointReplays, ComponentHits, GroupHits, GroupMisses, Merges, FullFallbacks int
	ReplaySeconds                                                                                 float64
	GroupEntries, GroupValues                                                                     int
	SymbolicComponents, SymbolicCompositions                                                      int
	ComponentExpressionNodes                                                                      int
}

func (b *NeutralBinding) PreparationStats() NeutralPreparationStats {
	s := b.stats
	s.GroupEntries, s.GroupValues = len(b.groups), b.groupValues
	s.ComponentExpressionNodes = b.componentExpressionNodes
	return s
}

// Constant conflict groups retain only raw vectors/footprints, not expression
// graphs. FIFO limits both entries and floats; eviction changes cost, not scores.
const neutralGroupEntries = 128
const neutralGroupValues = 2_000_000
const neutralComponentExpressionNodes = 128_000

func componentExpressionSize(expressions map[int]*formula.InputExpression, limit int) (int, bool) {
	seen := map[*formula.InputExpression]bool{}
	stack := make([]*formula.InputExpression, 0, len(expressions))
	for _, x := range expressions {
		stack = append(stack, x)
	}
	for len(stack) > 0 {
		x := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		if seen[x] {
			continue
		}
		seen[x] = true
		if x == nil || len(seen) > limit {
			return 0, false
		}
		stack = append(stack, x.Inputs...)
	}
	return len(seen), true
}

func ruleChoicesKey(choices []RuleChoice) string {
	rows := make([]string, len(choices))
	for i, c := range choices {
		rows[i] = fmt.Sprintf("%d:%s:%d", c.Owner, c.Key, c.Pieces)
	}
	sort.Strings(rows)
	return strings.Join(rows, "|")
}

func (b *NeutralBinding) componentOf(out NeutralExpressions) neutralComponent {
	c := neutralComponent{footprint: out.footprint, uncertainty: out.Uncertainty, usable: out.Complete() && out.footprint.trackedStats()}
	if c.usable {
		c.raw = out.raw
		for i, key := range b.keys {
			if x := out.Effects[key]; x != nil && x.Operation != "constant" {
				if c.expressions == nil {
					c.expressions = map[int]*formula.InputExpression{}
				}
				c.expressions[i] = x
			}
		}
		if len(c.expressions) != 0 {
			b.stats.SymbolicComponents++
		}
	}
	b.identifyComponent(&c)
	return c
}

func (b *NeutralBinding) conflictGroup(choices []RuleChoice) neutralComponent {
	key := ruleChoicesKey(choices)
	if c, ok := b.groups[key]; ok {
		b.stats.GroupHits++
		return c
	}
	b.stats.GroupMisses++
	c := b.componentOf(b.compilePackagesJoint(choices))
	// Symbolic independent components are few and catalog-bounded. Do not retain
	// arbitrary joint expression graphs without a separate graph-size budget.
	if !c.usable || len(c.expressions) != 0 || len(c.raw) > neutralGroupValues {
		return c
	}
	if b.groups == nil {
		b.groups = map[string]neutralComponent{}
	}
	for len(b.groupOrder) >= neutralGroupEntries || b.groupValues+len(c.raw) > neutralGroupValues {
		old := b.groupOrder[0]
		b.groupOrder = b.groupOrder[1:]
		b.groupValues -= len(b.groups[old].raw)
		delete(b.groups, old)
	}
	b.groups[key] = c
	b.groupOrder = append(b.groupOrder, key)
	b.groupValues += len(c.raw)
	return c
}

type ruleFootprint struct {
	reads, writes         map[string]bool
	statDependent         bool
	statReads, statWrites map[ruleStatDependency]bool
}

// An empty stat is an unknown/multi-stat writer and conflicts with every read
// of that owner's mode. Extra modifiers never write NonExtraStat.
type ruleStatDependency struct {
	owner      int
	stat, mode string
}

func (f ruleFootprint) trackedStats() bool { return !f.statDependent || len(f.statReads) > 0 }

func (f *ruleFootprint) readStat(owner int, stat, mode string) {
	if f.statReads == nil {
		f.statReads = map[ruleStatDependency]bool{}
	}
	f.statReads[ruleStatDependency{owner, stat, mode}] = true
}

func (f *ruleFootprint) writeStat(owner int, stat string, extra bool) {
	if f.statWrites == nil {
		f.statWrites = map[ruleStatDependency]bool{}
	}
	f.statWrites[ruleStatDependency{owner, stat, "stat"}] = true
	if !extra {
		f.statWrites[ruleStatDependency{owner, stat, "non_extra_stat"}] = true
	}
}

func statFootprintsConflict(reads, writes map[ruleStatDependency]bool) bool {
	for read := range reads {
		if writes[read] || writes[ruleStatDependency{read.owner, "", read.mode}] {
			return true
		}
	}
	return false
}

func ruleModifierKey(owner, target int, key string) string {
	return fmt.Sprintf("modifier:%d:%d:%s", owner, target, key)
}
func (f *ruleFootprint) read(key string) {
	if f.reads == nil {
		f.reads = map[string]bool{}
	}
	f.reads[key] = true
}
func (f *ruleFootprint) write(key string) {
	if f.writes == nil {
		f.writes = map[string]bool{}
	}
	f.writes[key] = true
}
func (f *ruleFootprint) merge(other ruleFootprint) {
	for key := range other.reads {
		f.read(key)
	}
	for key := range other.writes {
		f.write(key)
	}
	f.statDependent = f.statDependent || other.statDependent
	if len(other.statReads) != 0 && f.statReads == nil {
		f.statReads = map[ruleStatDependency]bool{}
	}
	for key := range other.statReads {
		f.statReads[key] = true
	}
	if len(other.statWrites) != 0 && f.statWrites == nil {
		f.statWrites = map[ruleStatDependency]bool{}
	}
	for key := range other.statWrites {
		f.statWrites[key] = true
	}
}
func (f ruleFootprint) independent(other ruleFootprint) bool {
	if !f.trackedStats() || !other.trackedStats() || statFootprintsConflict(f.statReads, other.statWrites) || statFootprintsConflict(other.statReads, f.statWrites) {
		return false
	}
	for key := range f.writes {
		if other.writes[key] || other.reads[key] {
			return false
		}
	}
	for key := range other.writes {
		if f.reads[key] {
			return false
		}
	}
	return true
}

type neutralComponent struct {
	effectIdentity [32]byte
	raw            []float64
	expressions    map[int]*formula.InputExpression
	footprint      ruleFootprint
	uncertainty    []string
	usable         bool
}

func (b *NeutralBinding) CompilePackages(choices []RuleChoice) NeutralExpressions {
	return b.compilePackages(choices, false, false)
}

// CompilePackagesCompact preserves the same source checks and arithmetic, but
// returns composed constants as a dense vector instead of one allocated object
// and string-map entry per port. General source expressions still use Effects.
func (b *NeutralBinding) CompilePackagesCompact(choices []RuleChoice) NeutralExpressions {
	return b.compilePackages(choices, true, false)
}

// Only the owned optimizer consumer opts into dense constants plus sparse
// expressions. Public map/compact APIs retain their existing output shape.
func (b *NeutralBinding) CompilePackagesSparse(choices []RuleChoice) NeutralExpressions {
	return b.compilePackages(choices, true, true)
}

func (b *NeutralBinding) compilePackages(choices []RuleChoice, compact, sparse bool) NeutralExpressions {
	if b == nil || len(b.members) == 0 {
		return NeutralExpressions{Boundaries: []string{"neutral binding is unavailable"}}
	}
	b.stats.Requests++
	// Keep the source interpreter's legality checks even when composition would
	// otherwise avoid it. Single-choice cache keys are bounded by the source
	// catalog (at most128 sets x4 owners x4 legal piece counts).
	counts := map[int]int{}
	seen := map[string]bool{}
	ordered := append([]RuleChoice(nil), choices...)
	for _, c := range ordered {
		key := fmt.Sprintf("%d:%s", c.Owner, c.Key)
		counts[c.Owner] += c.Pieces
		if c.Owner < 0 || c.Owner >= len(b.members[0].neutral.Context.Characters) || c.Pieces < 2 || c.Pieces > 5 || counts[c.Owner] > 5 || seen[key] {
			return NeutralExpressions{Boundaries: []string{"illegal neutral rule package"}}
		}
		seen[key] = true
	}
	sort.Slice(ordered, func(i, j int) bool {
		if ordered[i].Owner != ordered[j].Owner {
			return ordered[i].Owner < ordered[j].Owner
		}
		return ordered[i].Key < ordered[j].Key
	})
	type group struct {
		choices   []RuleChoice
		component neutralComponent
	}
	groups := []group{}
	fallback := func() NeutralExpressions { b.stats.FullFallbacks++; return b.compilePackagesJoint(choices) }
	for _, choice := range ordered {
		component, ok := b.components[choice]
		if !ok {
			out := b.compilePackagesJoint([]RuleChoice{choice})
			component = b.componentOf(out)
			// Reject unknown source keys without retaining caller-created cache keys.
			for _, set := range b.catalog.Sets {
				if set.Key == choice.Key {
					if nodes, fits := componentExpressionSize(component.expressions, neutralComponentExpressionNodes-b.componentExpressionNodes); fits {
						b.components[choice] = component
						if choice.Pieces == 2 && component.usable && len(component.expressions) == 0 {
							b.stats.TwoPieceChoices++
							if b.twoPieceFamilies == nil {
								b.twoPieceFamilies = map[[32]byte]bool{}
							}
							b.twoPieceFamilies[component.effectIdentity] = true
							b.stats.TwoPieceEffectFamilies = len(b.twoPieceFamilies)
						}
						b.componentExpressionNodes += nodes
					}
					break
				}
			}
			if len(ordered) == 1 {
				return out
			}
		} else {
			b.stats.ComponentHits++
		}
		if !component.usable {
			return fallback()
		}
		groups = append(groups, group{[]RuleChoice{choice}, component})
	}
	// Merge to a fixed point. Joint execution can expose NEW reads/writes behind
	// a condition (A enables B, B then conflicts with C). A single graph pass over
	// the original isolated footprints would silently miss that dependency.
	for {
		merged := false
		for i := 0; i < len(groups) && !merged; i++ {
			for j := i + 1; j < len(groups); j++ {
				if groups[i].component.footprint.independent(groups[j].component.footprint) {
					continue
				}
				choices := append(append([]RuleChoice(nil), groups[i].choices...), groups[j].choices...)
				component := b.conflictGroup(choices)
				if !component.usable {
					return fallback()
				}
				// Conservative union retains dependencies from untaken joint paths.
				// Never mutate a cached footprint: allocate its union separately.
				footprint := ruleFootprint{}
				footprint.merge(component.footprint)
				footprint.merge(groups[i].component.footprint)
				footprint.merge(groups[j].component.footprint)
				component.footprint = footprint
				groups[i] = group{choices, component}
				groups = append(groups[:j], groups[j+1:]...)
				b.stats.Merges++
				merged = true
				break
			}
		}
		if !merged {
			break
		}
	}
	// Legality, activation and the fixed-point dependency merge have ALREADY
	// completed. Equal numbers before this point would not prove independence.
	payloadKey := ""
	if sparse {
		identities := make([]byte, 0, 32*len(groups))
		for _, group := range groups {
			identities = append(identities, group.component.effectIdentity[:]...)
		}
		payloadKey = string(identities)
		if cached, ok := b.composedPayloads[payloadKey]; ok {
			b.stats.FamilyHits++
			cached.footprint = ruleFootprint{}
			uncertainty := map[string]bool{}
			for _, group := range groups {
				cached.footprint.merge(group.component.footprint)
				for _, code := range group.component.uncertainty {
					uncertainty[code] = true
				}
			}
			cached.Uncertainty = []string{}
			for code := range uncertainty {
				cached.Uncertainty = append(cached.Uncertainty, code)
			}
			sort.Strings(cached.Uncertainty)
			return cached
		}
		b.stats.FamilyMisses++
	}
	combined := neutralComponent{raw: make([]float64, len(b.keys)), usable: true}
	uncertainty := map[string]bool{}
	for _, group := range groups {
		component := group.component
		combined.footprint.merge(component.footprint)
		for i, x := range component.raw {
			combined.raw[i] += x
		}
		for i, x := range component.expressions {
			if combined.expressions == nil {
				combined.expressions = map[int]*formula.InputExpression{}
			}
			if old := combined.expressions[i]; old != nil {
				x = &formula.InputExpression{Operation: "add", Inputs: []*formula.InputExpression{old, x}}
			}
			combined.expressions[i] = x
		}
		for _, code := range component.uncertainty {
			uncertainty[code] = true
		}
	}
	out := NeutralExpressions{raw: combined.raw, footprint: combined.footprint, Boundaries: []string{}, Uncertainty: []string{}}
	if len(combined.expressions) != 0 {
		b.stats.SymbolicCompositions++
	}
	if sparse && len(combined.expressions) != 0 {
		out.Constants = make([]float64, len(b.keys))
		out.SparseEffects = make(map[int]*formula.InputExpression, len(combined.expressions))
	} else if compact && len(combined.expressions) == 0 {
		out.Constants = make([]float64, len(b.keys))
	} else {
		out.Effects = make(map[string]*formula.InputExpression, len(b.keys))
	}
	for _, member := range b.members {
		for _, port := range member.ports {
			value := combined.raw[port.dimension]
			if expression := combined.expressions[port.dimension]; expression != nil {
				if port.curve != nil {
					out.Boundaries = append(out.Boundaries, "stat-dependent resistance curve binding unavailable")
					continue
				}
				if value != 0 {
					expression = &formula.InputExpression{Operation: "add", Inputs: []*formula.InputExpression{expression, {Operation: "constant", Value: value}}}
				}
				if out.SparseEffects != nil {
					out.SparseEffects[port.dimension] = expression
				} else {
					out.Effects[b.keys[port.dimension]] = expression
				}
				continue
			}
			if port.curve != nil {
				transformed, err := port.curve.Evaluate(port.resistance + value)
				if err != nil {
					out.Boundaries = append(out.Boundaries, err.Error())
					continue
				}
				value = transformed - port.observed
			}
			if out.Constants != nil {
				out.Constants[port.dimension] = value
			} else {
				out.Effects[b.keys[port.dimension]] = &formula.InputExpression{Operation: "constant", Value: value}
			}
		}
	}
	for code := range uncertainty {
		out.Uncertainty = append(out.Uncertainty, code)
	}
	sort.Strings(out.Uncertainty)
	if sparse {
		b.retainComposedPayload(payloadKey, out)
	}
	return out
}
