package seteffects

import (
	"fmt"
	"math"
	"math/big"
	"sort"
	"strconv"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

type ChannelPanel interface {
	Coordinates() []string
	EvaluateChannelDPS([]float64) ([][]float64, error)
}

// EffectFeature describes a POSSIBLE term on the OLD unchanged context. The
// affected damage is exposure, not an upper bound or additional damage. The
// optional raw-stat proxy is not a replacement DPS: activation, Extra, stacking,
// missing consumer ports and indirect dependencies still require a new context.
type EffectFeature struct {
	EffectID          string   `json:"effect_id"`
	TermIndex         int      `json:"term_index"`
	Kind              string   `json:"kind"`
	Wearer            string   `json:"wearer"`
	SourceConstant    string   `json:"source_constant,omitempty"`
	PossibleDamageDPS float64  `json:"possible_damage_dps"`
	UnknownFilterDPS  float64  `json:"unknown_filter_dps"`
	RawStatProxyDPS   *float64 `json:"raw_stat_proxy_dps,omitempty"`
	Limitations       []string `json:"limitations"`
}

type ExposureProbe struct {
	panel       ChannelPanel
	channels    [][]contracts.IRChannel
	baseline    [][]float64
	coordinates map[string]int
	cache       map[string][][]float64
	Evaluations int
	owners      []string
	anchor      []float64
}

func NewExposureProbe(panel ChannelPanel, members []contracts.IRSeedMember) (*ExposureProbe, error) {
	if panel == nil || len(members) == 0 {
		return nil, fmt.Errorf("channel panel and bound members required")
	}
	p := &ExposureProbe{panel: panel, coordinates: map[string]int{}, cache: map[string][][]float64{}, Evaluations: 1}
	for i, key := range panel.Coordinates() {
		p.coordinates[key] = i
	}
	p.anchor = make([]float64, len(p.coordinates))
	owners := map[string]bool{}
	for key := range p.coordinates {
		if i := strings.IndexByte(key, '.'); i > 0 {
			owners[key[:i]] = true
		}
	}
	for owner := range owners {
		p.owners = append(p.owners, owner)
	}
	sort.Strings(p.owners)
	var e error
	p.baseline, e = panel.EvaluateChannelDPS(make([]float64, len(p.coordinates)))
	if e != nil {
		return nil, e
	}
	if len(p.baseline) != len(members) {
		return nil, fmt.Errorf("channel member count mismatch")
	}
	for i, member := range members {
		if len(p.baseline[i]) != len(member.Channels) {
			return nil, fmt.Errorf("channel count mismatch")
		}
		p.channels = append(p.channels, append([]contracts.IRChannel(nil), member.Channels...))
		weight := 1000 / (float64(member.DurationMS) * float64(len(members)))
		for j, ch := range member.Channels {
			value, err := strconv.ParseFloat(ch.BaselineDamage, 64)
			if err != nil || !finite(value) || !finite(p.baseline[i][j]) || math.Abs(value*weight-p.baseline[i][j]) > 1e-6*math.Max(1, math.Abs(value*weight)) {
				return nil, fmt.Errorf("channel baseline alignment mismatch")
			}
		}
	}
	return p, nil
}

func finite(x float64) bool { return !math.IsNaN(x) && !math.IsInf(x, 0) }

func (p *ExposureProbe) Feature(d Description, r Recipe, termIndex int, wearer string, statVocabulary map[string]string, tags map[string]int) (EffectFeature, error) {
	out := EffectFeature{EffectID: r.Effect.ID, TermIndex: termIndex, Kind: r.Effect.Kind, Wearer: wearer, Limitations: []string{"old_context_not_replacement", "activation_and_stacking_unverified"}}
	if p == nil || wearer == "" || termIndex < 0 || termIndex >= len(r.Terms) {
		return out, fmt.Errorf("invalid effect feature")
	}
	term := r.Terms[termIndex]
	out.SourceConstant = term.Constant
	stat, known := OwnerStatKey(statVocabulary[term.Coordinate])
	// The existing compact compiler exposes an all-damage coordinate for the
	// hit formulas that actually consume it. Do not synthesize it for other hits.
	if statVocabulary[term.Coordinate] == "dmg%" {
		stat = "damage_bonus"
		known = true
	}
	var response [][]float64
	coordinate := wearer + "." + stat
	if (r.Effect.Kind == "stat" || r.Effect.Kind == "attack_bonus") && (r.RecipientScope == "owner" || r.RecipientScope == "team_iteration_member") && known && term.Constant != "" {
		recipients := []string{wearer}
		if r.RecipientScope == "team_iteration_member" {
			recipients = p.owners
			coordinate = "team." + stat
			out.Limitations = append(out.Limitations, "team_recipient_eligibility_unverified")
		}
		indices := []int{}
		for _, owner := range recipients {
			if index, ok := p.coordinates[owner+"."+stat]; ok {
				indices = append(indices, index)
			}
		}
		if len(indices) > 0 {
			value, ok := new(big.Rat).SetString(term.Constant)
			if !ok {
				return out, fmt.Errorf("invalid source constant")
			}
			amount, _ := value.Float64()
			if !finite(amount) {
				return out, fmt.Errorf("nonfinite source constant")
			}
			cacheKey := coordinate + "=" + strconv.FormatFloat(amount, 'g', -1, 64)
			response = p.cache[cacheKey]
			if response == nil {
				deltas := append([]float64(nil), p.anchor...)
				for _, index := range indices {
					deltas[index] += amount
				}
				var e error
				response, e = p.panel.EvaluateChannelDPS(deltas)
				if e != nil {
					return out, e
				}
				p.cache[cacheKey] = response
				p.Evaluations++
			}
			proxy := 0.0
			out.RawStatProxyDPS = &proxy
		}
	}
	if response == nil {
		out.Limitations = append(out.Limitations, "numeric_consumer_port_or_amount_unavailable")
	}
	if r.RecipientScope != "owner" {
		out.Limitations = append(out.Limitations, "recipient_or_contributor_scope_unresolved")
	}
	for i, channels := range p.channels {
		for j, ch := range channels {
			// A reaction's displayed actor need not own every contributing input.
			// Only ordinary attack-mod recipient channels are narrowed by actor.
			if r.Effect.Kind == "attack_bonus" && r.RecipientScope == "owner" && ch.ActorKey != wearer {
				continue
			}
			app := d.TermChannelApplicability(term, ch.AttackTag, tags)
			if app == Excluded {
				continue
			}
			out.PossibleDamageDPS += p.baseline[i][j]
			if app == Unknown {
				out.UnknownFilterDPS += p.baseline[i][j]
			}
			if response != nil {
				*out.RawStatProxyDPS += response[i][j] - p.baseline[i][j]
			}
		}
	}
	return out, nil
}
