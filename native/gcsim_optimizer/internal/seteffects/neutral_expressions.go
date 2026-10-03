package seteffects

// Binds source-produced arithmetic to retained neutral read roots. Exact query
// matches are preferred. A prior full-snapshot/Extra projection is explicitly
// approximate and must never certify pruning or changed-schedule correctness.
import (
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"sort"
	"time"
)

type NeutralExpressions struct {
	raw       []float64
	footprint ruleFootprint
	// Constants is ordered exactly by binding.Keys() and contains every port.
	// The sparse consumer replaces selected dimensions with SparseEffects;
	// the public general-expression API retains Effects instead.
	SparseEffects map[int]*formula.InputExpression // private compact consumer path
	Constants     []float64
	Effects       map[string]*formula.InputExpression
	Boundaries    []string
	Uncertainty   []string
}

func (x NeutralExpressions) Complete() bool { return len(x.Boundaries) == 0 }

func (s *RuleScalar) Bind(read func(RuleStatRead) (*formula.InputExpression, error)) (*formula.InputExpression, error) {
	memo := map[*RuleScalar]*formula.InputExpression{}
	busy := map[*RuleScalar]bool{}
	visits := 0
	var visit func(*RuleScalar, int) (*formula.InputExpression, error)
	visit = func(s *RuleScalar, depth int) (*formula.InputExpression, error) {
		visits++
		if s == nil || depth > 128 || visits > 16384 {
			return nil, fmt.Errorf("rule scalar binding budget")
		}
		if x, ok := memo[s]; ok {
			return x, nil
		}
		if busy[s] {
			return nil, fmt.Errorf("cyclic rule scalar")
		}
		busy[s] = true
		defer delete(busy, s)
		if s.Operation == "neutral_stat" {
			if s.Read == nil || read == nil {
				return nil, fmt.Errorf("unbound neutral stat")
			}
			return read(*s.Read)
		}
		x := &formula.InputExpression{Operation: s.Operation, Value: s.Value}
		for _, in := range s.Inputs {
			child, err := visit(in, depth+1)
			if err != nil {
				return nil, err
			}
			x.Inputs = append(x.Inputs, child)
		}
		memo[s] = x
		return x, nil
	}
	return visit(s, 0)
}

func (b *NeutralBinding) compilePackagesJoint(choices []RuleChoice) NeutralExpressions {
	started := time.Now()
	b.stats.Replays++
	if len(choices) > 1 {
		b.stats.JointReplays++
	}
	defer func() { b.stats.ReplaySeconds += time.Since(started).Seconds() }()
	out := NeutralExpressions{Effects: map[string]*formula.InputExpression{}, Boundaries: []string{}, Uncertainty: []string{}}
	out.raw = make([]float64, len(b.keys))
	boundaries, uncertainty := map[string]bool{}, map[string]bool{}
	for mi, member := range b.members {
		type resolvedRead struct {
			x   *formula.InputExpression
			err error
		}
		resolved := map[RuleStatRead]resolvedRead{}
		queries, order := member.preparedQueries()
		replay := b.catalog.replayNeutralRulesPrepared(member.neutral, choices, queries, true, order)
		out.footprint.merge(replay.footprint)
		if replay.Boundary != "" {
			boundaries[replay.Boundary] = true
			continue
		}
		for _, code := range replay.Uncertainty {
			uncertainty[code] = true
		}
		for i, p := range member.ports {
			value := replay.Values[i]
			if !value.Known {
				boundaries[value.Boundary] = true
				continue
			}
			if value.Expression == nil {
				x := value.Value
				out.raw[p.dimension] = x
				if p.curve != nil {
					v, err := p.curve.Evaluate(p.resistance + x)
					if err != nil {
						boundaries[err.Error()] = true
						continue
					}
					x = v - p.observed
				}
				out.Effects[b.keys[p.dimension]] = &formula.InputExpression{Operation: "constant", Value: x}
				continue
			}
			out.footprint.statDependent = true
			if p.curve != nil {
				boundaries["stat-dependent resistance curve binding unavailable"] = true
				continue
			}
			x, err := value.Expression.Bind(func(query RuleStatRead) (*formula.InputExpression, error) {
				// Bind visits every neutral-stat leaf, including any future source
				// scalar producer, not just reads observed by statExpression today.
				out.footprint.readStat(query.Owner, query.Stat, query.Mode)
				if cached, ok := resolved[query]; ok {
					return cached.x, cached.err
				}
				root, codes, err := member.reads.find(query)
				if err != nil {
					resolved[query] = resolvedRead{err: err}
					return nil, err
				}
				for _, code := range codes {
					uncertainty[code] = true
				}
				x := &formula.InputExpression{Operation: "read", Key: neutralReadKey(mi, root.NodeID)}
				resolved[query] = resolvedRead{x: x}
				return x, nil
			})
			if err != nil {
				boundaries[err.Error()] = true
				continue
			}
			out.Effects[b.keys[p.dimension]] = x
		}
	}
	for code := range boundaries {
		out.Boundaries = append(out.Boundaries, code)
	}
	for code := range uncertainty {
		out.Uncertainty = append(out.Uncertainty, code)
	}
	sort.Strings(out.Boundaries)
	sort.Strings(out.Uncertainty)
	return out
}

type neutralReadIndex struct {
	neutral *contracts.NeutralInputs
	byKey   map[[3]string][]contracts.NeutralReadRoot
}

func indexNeutralReads(n *contracts.NeutralInputs) *neutralReadIndex {
	x := &neutralReadIndex{neutral: n, byKey: map[[3]string][]contracts.NeutralReadRoot{}}
	if n == nil {
		return x
	}
	for _, root := range n.Reads {
		if len(root.Uncertainty) != 0 {
			continue
		}
		key := [3]string{root.Owner, root.Stat, root.Point.Mode}
		x.byKey[key] = append(x.byKey[key], root)
	}
	for key, roots := range x.byKey {
		sort.SliceStable(roots, func(i, j int) bool {
			if roots[i].Point.Order != roots[j].Point.Order {
				return roots[i].Point.Order < roots[j].Point.Order
			}
			return roots[i].Projection && !roots[j].Projection
		})
		x.byKey[key] = roots
	}
	return x
}

func findNeutralStatRoot(n *contracts.NeutralInputs, query RuleStatRead) (contracts.NeutralReadRoot, []string, error) {
	return indexNeutralReads(n).find(query)
}

func (x *neutralReadIndex) find(query RuleStatRead) (contracts.NeutralReadRoot, []string, error) {
	n := x.neutral
	if n == nil || !n.ReadsComplete || query.Owner < 0 || query.Owner >= len(n.Context.Characters) {
		return contracts.NeutralReadRoot{}, nil, fmt.Errorf("neutral stat observations incomplete")
	}
	owner := n.Context.Characters[query.Owner].Key
	roots := x.byKey[[3]string{owner, query.Stat, query.Mode}]
	best := sort.Search(len(roots), func(i int) bool { return roots[i].Point.Order > query.Order }) - 1
	if best < 0 {
		return contracts.NeutralReadRoot{}, nil, fmt.Errorf("unbound neutral stat read: %s.%s/%s at %d", owner, query.Stat, query.Mode, query.Order)
	}
	root := roots[best]
	codes := []string{}
	if root.Projection {
		codes = append(codes, "non_extra_from_observed_snapshot_approximate")
	}
	if root.Point.Order != query.Order {
		codes = append(codes, "set_stat_query_uses_prior_observation")
	}
	if root.Point.StatKeys == nil || len(*root.Point.StatKeys) != 1 || (*root.Point.StatKeys)[0] != query.Stat {
		codes = append(codes, "set_stat_query_filter_projected")
	}
	return root, codes, nil
}
