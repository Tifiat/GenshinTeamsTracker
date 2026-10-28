package theorysearch

import (
	"math"
	"math/big"
	"sort"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/theory"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
)

const ResultKind = "gtt_gcsim_optimizer_theory_result_v2"
const PracticalBandPercent = 3.0
const SensitivityBandPercent = 2.0

type PackageRow struct {
	WearerKey string                     `json:"wearer_key"`
	Sets      []contracts.SetRequirement `json:"sets"`
}
type Alias struct {
	TupleKey      string       `json:"tuple_key"`
	Packages      []PackageRow `json:"packages"`
	ContextSHA256 string       `json:"context_sha256"`
	Uncertainty   []string     `json:"uncertainty"`
}
type Unavailable struct {
	TupleKey string       `json:"tuple_key"`
	Packages []PackageRow `json:"packages"`
	Reasons  []string     `json:"reasons"`
}
type FamilyRow struct {
	Family          string                    `json:"family"`
	FormulaDPS      float64                   `json:"formula_dps"`
	Witness45       alloc.State               `json:"witness45"`
	Allocations     []theory.WearerAllocation `json:"allocations"`
	Aliases         []Alias                   `json:"aliases"`
	DeficitPercent  float64                   `json:"deficit_percent"`
	RefinementLevel int                       `json:"refinement_level"`
	Reason          string                    `json:"reason,omitempty"`
}
type Snapshot struct {
	SchemaVersion            int            `json:"schema_version"`
	SchemaKind               string         `json:"schema_kind"`
	RequestSHA256            string         `json:"request_sha256"`
	SessionID                string         `json:"session_id"`
	SnapshotVersion          int64          `json:"snapshot_version"`
	Phase                    string         `json:"phase"`
	PolicyID                 string         `json:"policy_id"`
	Status                   string         `json:"status"`
	SearchStatus             string         `json:"search_status"`
	ResponseStatus           string         `json:"response_status"`
	FinishedEarly            bool           `json:"finished_early"`
	ReferenceScore           float64        `json:"reference_score"`
	PracticalBandPercent     float64        `json:"practical_band_percent"`
	SensitivityBandPercent   float64        `json:"sensitivity_band_percent"`
	CoLeaders                []FamilyRow    `json:"co_leaders"`
	Pending                  []FamilyRow    `json:"pending"`
	Unavailable              []Unavailable  `json:"unavailable"`
	TotalFoundFamilies       int            `json:"total_found_families"`
	TotalFoundTuples         int            `json:"total_found_tuples"`
	FoundGroupFamilies       int            `json:"found_group_families"`
	FoundGroupTuples         int            `json:"found_group_tuples"`
	SensitivityGroupFamilies int            `json:"sensitivity_group_families"`
	SensitivityGroupTuples   int            `json:"sensitivity_group_tuples"`
	DomainTuples             string         `json:"domain_tuples"`
	UnseenTuples             string         `json:"unseen_tuples"`
	FullCartesianCovered     bool           `json:"full_cartesian_covered"`
	SourceUpper              string         `json:"source_upper"`
	OuterUpper               string         `json:"outer_upper"`
	Work                     Work           `json:"active_branch_work"`
	Rules                    map[string]any `json:"rules"`
}

func packageRows(p [4]domain.Package, wearers [4]string) []PackageRow {
	rows := make([]PackageRow, 4)
	for a := range p {
		rows[a] = PackageRow{wearers[a], append([]contracts.SetRequirement{}, p[a].Sets...)}
	}
	return rows
}
func clonePackageRows(rows []PackageRow) []PackageRow {
	out := make([]PackageRow, len(rows))
	for i, r := range rows {
		out[i] = r
		out[i].Sets = append([]contracts.SetRequirement{}, r.Sets...)
	}
	return out
}
func cloneAlias(a Alias) Alias {
	a.Packages = clonePackageRows(a.Packages)
	a.Uncertainty = append([]string{}, a.Uncertainty...)
	return a
}
func cloneUnavailable(u Unavailable) Unavailable {
	u.Packages = clonePackageRows(u.Packages)
	u.Reasons = append([]string{}, u.Reasons...)
	return u
}
func allocations(s alloc.State, wearers [4]string) []theory.WearerAllocation {
	slots := [5]string{"flower", "plume", "sands", "goblet", "circlet"}
	keys, values := alloc.StatKeys(), alloc.StatValues()
	rolls := s.Rolls()
	rows := make([]theory.WearerAllocation, 4)
	for a := range rows {
		r := theory.WearerAllocation{WearerKey: wearers[a], MainStats: map[string]string{}, Substats: []theory.StatAllocation{}}
		for slot, key := range s.Mains[a] {
			r.MainStats[slots[slot]] = key
		}
		for j, u := range rolls[a] {
			r.Substats = append(r.Substats, theory.StatAllocation{StatKey: keys[j], RollUnits: u, StatValue: u * values[j]})
			r.SpentRollUnits += u
		}
		r.UnspentRollUnits = 45 - r.SpentRollUnits
		rows[a] = r
	}
	return rows
}

// AllocationsForWitness shares the existing display projection with verified
// full-build proposals. It changes neither search nor its numerical policy.
func AllocationsForWitness(s alloc.State, wearers [4]string) ([]theory.WearerAllocation, error) {
	if err := alloc.ValidateFull45(s); err != nil {
		return nil, err
	}
	return allocations(s, wearers), nil
}
func deficit(reference, score float64) float64 {
	if reference == 0 {
		if score == 0 {
			return 0
		}
		return 100
	}
	return 100 * (reference - score) / math.Abs(reference)
}
func (s *Session) publish(terminal bool) Snapshot {
	s.version++
	out := Snapshot{SchemaVersion: 2, SchemaKind: ResultKind, RequestSHA256: s.cfg.RequestSHA256, SessionID: s.cfg.SessionID,
		SnapshotVersion: s.version, Phase: s.phase, PolicyID: PolicyID, Status: "success", SearchStatus: "partial", ResponseStatus: "formula_only",
		PracticalBandPercent: PracticalBandPercent, SensitivityBandPercent: SensitivityBandPercent,
		CoLeaders: []FamilyRow{}, Pending: []FamilyRow{}, Unavailable: []Unavailable{}, SourceUpper: "unbounded", OuterUpper: "unbounded"}
	if out.Phase == "" {
		out.Phase = "first_light"
	}
	out.FinishedEarly = terminal
	out.Work = s.active.work
	rows := sorted(s.archive.pool)
	if len(rows) > 0 {
		out.ReferenceScore = rows[0].value
	}
	for _, c := range rows {
		r := FamilyRow{Family: c.family, FormulaDPS: c.value, Witness45: c.state, Allocations: allocations(c.state, s.cfg.Wearers),
			DeficitPercent: deficit(out.ReferenceScore, c.value), RefinementLevel: s.archive.refined[c.family], Aliases: []Alias{}}
		for _, a := range s.archive.aliases[c.family] {
			r.Aliases = append(r.Aliases, cloneAlias(a))
		}
		sort.Slice(r.Aliases, func(i, j int) bool { return r.Aliases[i].TupleKey < r.Aliases[j].TupleKey })
		out.TotalFoundFamilies++
		out.TotalFoundTuples += len(r.Aliases)
		if r.DeficitPercent <= PracticalBandPercent+1e-12 {
			out.CoLeaders = append(out.CoLeaders, r)
			out.FoundGroupFamilies++
			out.FoundGroupTuples += len(r.Aliases)
		} else {
			r.Reason = "below_practical_band"
			if r.RefinementLevel < 2 {
				r.Reason = "below_practical_band_not_deeply_refined"
			}
			out.Pending = append(out.Pending, r)
		}
		if r.DeficitPercent <= SensitivityBandPercent+1e-12 {
			out.SensitivityGroupFamilies++
			out.SensitivityGroupTuples += len(r.Aliases)
		}
	}
	for _, u := range s.archive.unavailable {
		out.Unavailable = append(out.Unavailable, cloneUnavailable(u))
	}
	sort.Slice(out.Unavailable, func(i, j int) bool { return out.Unavailable[i].TupleKey < out.Unavailable[j].TupleKey })
	total := big.NewInt(1)
	for _, rows := range s.cfg.Domains {
		total.Mul(total, big.NewInt(int64(len(rows))))
	}
	remaining := new(big.Int).Sub(total, big.NewInt(int64(len(s.archive.visited))))
	out.DomainTuples = total.String()
	out.UnseenTuples = remaining.String()
	out.FullCartesianCovered = remaining.Sign() == 0
	out.Rules = map[string]any{"budget_roll_units_per_wearer": 45, "quarter_grid": true, "all_found_aliases": true,
		"reference_scope": "best_attained_across_found_branches", "practical_group_rank": "unordered_equivalent_group",
		"full_search_optimality_proved": false, "final_solution_cache_enabled": false}
	return out
}
