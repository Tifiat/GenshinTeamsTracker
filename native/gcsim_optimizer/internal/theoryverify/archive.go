package theoryverify

import (
	"context"
	"fmt"
	"path/filepath"
	"sort"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/theory"
	"genshinteamstracker/native/gcsim_optimizer/internal/theorysearch"
)

const ResultKind = "gtt_gcsim_optimizer_theory_result_v3"
const DefaultLimit = 7
const DefaultIterations = 500
const PolicyID = "theory_ordinary_finalists_v1"

// Policy is a lifetime ordinary-call limit, not an offline search limit. The
// defaults reuse the existing finite All Sets finalist count/fidelity. An
// explicit request.Finalists overrides them; continuations never reset it.
type Policy struct {
	Limit           int
	Iterations      int
	ResponseReserve int
}

func PolicyFromRequest(request contracts.OptimizerRequest) (Policy, error) {
	p := Policy{Limit: DefaultLimit, Iterations: DefaultIterations}
	if request.Finalists != nil {
		p.Limit, p.Iterations = request.Finalists.MaxCandidates, request.Finalists.Iterations
	}
	if p.Limit <= 0 || p.Iterations <= 0 {
		return Policy{}, fmt.Errorf("Theory ordinary verification requires an explicit finite positive policy")
	}
	p.ResponseReserve = p.Limit / 3
	return p, nil
}

type Verification struct {
	PolicyID                   string `json:"policy_id"`
	Limit                      int    `json:"limit"`
	Iterations                 int    `json:"iterations"`
	AttemptedCount             int    `json:"attempted_count"`
	CompletedCount             int    `json:"completed_count"`
	FailedCount                int    `json:"failed_count"`
	EnergyRejectedCount        int    `json:"energy_rejected_count"`
	CandidateCount             int    `json:"candidate_count"`
	UnverifiedCount            int    `json:"unverified_count"`
	OmittedCount               int    `json:"omitted_count"`
	RemainingBudget            int    `json:"remaining_budget"`
	InProgress                 bool   `json:"in_progress"`
	ResponseLaneReserve        int    `json:"response_lane_reserve"`
	ResponseLaneAttemptedCount int    `json:"response_lane_attempted_count"`
}

type VerifiedRow struct {
	theorysearch.FamilyRow
	Measurement finalists.FullBuildMeasurement `json:"measurement"`
}

func cloneVerifiedRow(row VerifiedRow) VerifiedRow {
	row.Aliases = append([]theorysearch.Alias{}, row.Aliases...)
	for index := range row.Aliases {
		row.Aliases[index] = cloneAlias(row.Aliases[index])
	}
	row.Allocations = append([]theory.WearerAllocation{}, row.Allocations...)
	for index := range row.Allocations {
		allocation := &row.Allocations[index]
		mains := make(map[string]string, len(allocation.MainStats))
		for slot, main := range allocation.MainStats {
			mains[slot] = main
		}
		allocation.MainStats = mains
		allocation.Substats = append([]theory.StatAllocation{}, allocation.Substats...)
	}
	row.Measurement.BuildIdentity = append([]byte(nil), row.Measurement.BuildIdentity...)
	row.Measurement.Origins = cloneOrigins(row.Measurement.Origins)
	if row.Measurement.StandardDeviation != nil {
		sd := *row.Measurement.StandardDeviation
		row.Measurement.StandardDeviation = &sd
	}
	if row.Measurement.StandardError != nil {
		se := *row.Measurement.StandardError
		row.Measurement.StandardError = &se
	}
	return row
}

// Search counters remain search counters. Only these outer row arrays contain
// recommendation pages; the embedded formula arrays are not serialized.
type Snapshot struct {
	theorysearch.Snapshot
	PublicationVersion int64         `json:"publication_version"`
	Verification       Verification  `json:"verification"`
	CoLeaders          []VerifiedRow `json:"co_leaders"`
	Pending            []VerifiedRow `json:"pending"`
}

// Archive lives outside theorysearch.Session and its preDeep branch. Access is
// on the session thread or the common verifier's serialized observer callbacks.
type Archive struct {
	frameSHA          string
	policy            Policy
	ignoreEnergy      bool
	engineSHA         string
	sourceSHA         string
	wearers           [4]string
	candidates        map[string]Candidate
	attempted         map[string]bool
	failed            map[string]bool
	energyRejected    map[string]bool
	verified          map[string]VerifiedRow
	version           int64
	rounds            int
	inProgress        bool
	responseAttempted bool
	responseStatus    string
}

func NewArchive(request contracts.OptimizerRequest, policy Policy) (*Archive, error) {
	if policy.Limit <= 0 || policy.Iterations <= 0 || policy.ResponseReserve < 0 || policy.ResponseReserve > policy.Limit {
		return nil, fmt.Errorf("invalid finite Theory ordinary policy")
	}
	if len(request.Wearers) != 4 {
		return nil, fmt.Errorf("Theory ordinary archive requires four wearers")
	}
	frame, err := finalists.FullBuildFrameSHA256(request)
	if err != nil {
		return nil, err
	}
	ignoreEnergy, err := setcontext.IgnoreBurstEnergy(request.Context.PreparedConfig.Text)
	if err != nil {
		return nil, err
	}
	a := &Archive{frameSHA: frame, policy: policy, ignoreEnergy: ignoreEnergy,
		engineSHA: request.Engine.ArtifactSHA256, sourceSHA: request.Engine.SourceManifestSHA256,
		candidates: map[string]Candidate{}, attempted: map[string]bool{}, failed: map[string]bool{},
		energyRejected: map[string]bool{}, verified: map[string]VerifiedRow{}}
	for actor, wearer := range request.Wearers {
		a.wearers[actor] = wearer.WearerKey
	}
	return a, nil
}

func (a *Archive) FrameSHA256() string { return a.frameSHA }

// Offer accepts proposals from any producer. No family, origin or formula
// alias can authorize measurement reuse. The key always includes full build.
func (a *Archive) Offer(candidates []Candidate) error {
	for _, candidate := range candidates {
		key, err := finalists.FullBuildCandidateSHA256(candidate.Build.FrameSHA256, candidate.Build.BuildIdentity)
		if err != nil || key != candidate.Key || candidate.Build.FrameSHA256 != a.frameSHA {
			return fmt.Errorf("Theory ordinary proposal identity/frame changed")
		}
		if len(candidate.Row.Aliases) != 1 || !finite(candidate.Build.FormulaDPS) || candidate.Build.FormulaDPS < 0 {
			return fmt.Errorf("invalid concrete Theory ordinary proposal")
		}
		if candidate.Lane != FormulaLane && candidate.Lane != ResponseLane {
			return fmt.Errorf("unknown Theory verification proposal lane")
		}
		alias := candidate.Row.Aliases[0]
		if _, err := validatePackages(alias.Packages, a.wearers); err != nil {
			return err
		}
		normalized, err := NewCandidate(a.frameSHA, candidate.Row.Witness45, alias, candidate.Build.FormulaDPS, candidate.Build.Origins, candidate.Row.RefinementLevel)
		if err != nil || normalized.Key != key {
			return fmt.Errorf("Theory proposal payload does not bind its displayed alias/witness")
		}
		normalized.Lane = candidate.Lane
		if !finite(candidate.Priority.LocalOtherDPSGuide) || candidate.Priority.LocalOtherDPSGuide < 0 || !finite(candidate.Priority.LegalStatDisplacement) {
			return fmt.Errorf("invalid response proposal priority")
		}
		normalized.Priority = candidate.Priority
		if _, exists := a.candidates[key]; !exists || !a.attempted[key] {
			a.candidates[key] = normalized
		}
	}
	return nil
}

func (a *Archive) OfferSearch(snapshot theorysearch.Snapshot) error {
	candidates, err := SearchCandidates(a.frameSHA, snapshot)
	if err != nil {
		return err
	}
	return a.Offer(candidates)
}

func (a *Archive) remaining() int { return a.policy.Limit - len(a.attempted) }

// Reserve later phases without changing their numerical searches. With default
// seven calls, First/Breadth use at most two each; Deep or Finish can spend the
// remainder. A terminal First therefore still has the complete seven-call cap.
func (a *Archive) batchLimit(phase string, terminal bool) int {
	remaining := a.remaining()
	if terminal || phase == "deep_baseline" {
		return remaining
	}
	share := a.policy.Limit / 3
	if share < 1 {
		share = 1
	}
	if remaining < share {
		return remaining
	}
	return share
}

func (a *Archive) selectCandidates(limit int) []Candidate {
	if limit <= 0 {
		return nil
	}
	rows := make([]Candidate, 0, len(a.candidates))
	for key, candidate := range a.candidates {
		if !a.attempted[key] {
			rows = append(rows, candidate)
		}
	}
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].Build.FormulaDPS != rows[j].Build.FormulaDPS {
			return rows[i].Build.FormulaDPS > rows[j].Build.FormulaDPS
		}
		return rows[i].Key < rows[j].Key
	})
	responseAttempts, formulaAttempts := 0, 0
	for key := range a.attempted {
		if a.candidates[key].Lane == ResponseLane {
			responseAttempts++
		} else {
			formulaAttempts++
		}
	}
	responseNeed := a.policy.ResponseReserve - responseAttempts
	formulaCapacity := a.policy.Limit - a.policy.ResponseReserve - formulaAttempts
	selected := make([]Candidate, 0, limit)
	used := map[string]bool{}
	responseRows := make([]Candidate, 0)
	for _, candidate := range rows {
		if candidate.Lane == ResponseLane {
			responseRows = append(responseRows, candidate)
		}
	}
	sort.Slice(responseRows, func(i, j int) bool {
		left, right := responseRows[i].Priority, responseRows[j].Priority
		if left.ForeignPositive != right.ForeignPositive {
			return left.ForeignPositive
		}
		if left.ForeignPositive && left.CrossAncestryMissing != right.CrossAncestryMissing {
			return left.CrossAncestryMissing
		}
		if left.LocalOtherDPSGuide != right.LocalOtherDPSGuide {
			return left.LocalOtherDPSGuide > right.LocalOtherDPSGuide
		}
		if responseRows[i].Build.FormulaDPS != responseRows[j].Build.FormulaDPS {
			return responseRows[i].Build.FormulaDPS > responseRows[j].Build.FormulaDPS
		}
		return responseRows[i].Key < responseRows[j].Key
	})
	// A genuinely proposed response build is protected even when the formula
	// misses its support channel and ranks it below every formula-only proposal.
	for _, candidate := range responseRows {
		if responseNeed > 0 && len(selected) < limit {
			selected = append(selected, candidate)
			used[candidate.Key] = true
			responseNeed--
		}
	}
	for _, candidate := range rows {
		if len(selected) == limit {
			break
		}
		if used[candidate.Key] || (candidate.Lane == FormulaLane && formulaCapacity <= 0) {
			continue
		}
		selected = append(selected, candidate)
		if candidate.Lane == FormulaLane {
			formulaCapacity--
		}
	}
	return selected
}

func (a *Archive) attemptedBuild(key string) error {
	if _, exists := a.candidates[key]; !exists || a.attempted[key] || a.remaining() <= 0 {
		return fmt.Errorf("Theory ordinary invocation violates identity/lifetime budget")
	}
	a.attempted[key] = true
	return nil
}

func (a *Archive) commit(measurement finalists.FullBuildMeasurement) error {
	key, err := finalists.FullBuildCandidateSHA256(measurement.FrameSHA256, measurement.BuildIdentity)
	candidate, exists := a.candidates[measurement.CandidateSHA256]
	if err != nil || !exists || key != measurement.CandidateSHA256 || key != candidate.Key || !a.attempted[key] ||
		measurement.FrameSHA256 != a.frameSHA || measurement.Iterations != a.policy.Iterations ||
		measurement.EngineArtifactSHA256 != a.engineSHA || measurement.SourceManifestSHA256 != a.sourceSHA ||
		measurement.IgnoreBurstEnergy != a.ignoreEnergy || !finite(measurement.MeasuredDPS) || measurement.MeasuredDPS < 0 {
		return fmt.Errorf("ordinary receipt does not bind the complete comparable Theory build")
	}
	row := candidate.Row
	row.Family = key
	row.FormulaDPS = measurement.FormulaDPS
	row.Aliases = []theorysearch.Alias{cloneAlias(row.Aliases[0])}
	row.Reason = ""
	a.verified[key] = cloneVerifiedRow(VerifiedRow{FamilyRow: row, Measurement: measurement})
	return nil
}

// Verify reuses the common ordinary verifier. Completed receipts are committed
// and published immediately, so a later error or process-tree Cancel cannot
// erase a preceding fully verified publication. It never uses searchCtx.
func (a *Archive) Verify(ctx context.Context, request contracts.OptimizerRequest, search theorysearch.Snapshot,
	terminal bool, render finalists.FullBuildRenderer, runRoot string, cpuBudget int,
	checkBinding func() error, publish func(Snapshot) error, runner finalists.OrdinaryRunner) error {
	if checkBinding != nil {
		if err := checkBinding(); err != nil {
			return err
		}
	}
	selected := a.selectCandidates(a.batchLimit(search.Phase, terminal))
	if len(selected) == 0 {
		if publish != nil {
			return publish(a.Publish(search))
		}
		return nil
	}
	a.rounds++
	a.inProgress = true
	if publish != nil {
		if err := publish(a.Publish(search)); err != nil {
			a.inProgress = false
			return err
		}
	}
	builds := make([]finalists.FullBuildCandidate, len(selected))
	for index, candidate := range selected {
		builds[index] = candidate.Build
	}
	observer := finalists.FullBuildObserver{
		Attempted: a.attemptedBuild,
		Measured: func(measurement finalists.FullBuildMeasurement) error {
			if checkBinding != nil {
				if err := checkBinding(); err != nil {
					return err
				}
			}
			if err := a.commit(measurement); err != nil {
				return err
			}
			if publish != nil {
				return publish(a.Publish(search))
			}
			return nil
		},
	}
	result, err := finalists.VerifyFullBuildsWithRenderer(ctx, request, builds, render,
		filepath.Join(runRoot, fmt.Sprintf("ordinary-%02d", a.rounds)), a.policy.Iterations, 4, cpuBudget, runner, observer)
	a.inProgress = false
	for _, key := range result.FailedSHA256 {
		a.failed[key] = true
	}
	for _, key := range result.EnergyRejectedSHA256 {
		a.energyRejected[key] = true
	}
	// A publish callback can fail while another ordinary run already completed.
	// Recover only the common verifier's fully validated receipts, after checking
	// the request/source binding again; failed/incomplete rows are never imported.
	bindingValid := true
	if checkBinding != nil {
		if bindingErr := checkBinding(); bindingErr != nil {
			bindingValid = false
			if err == nil {
				err = bindingErr
			}
		}
	}
	if bindingValid {
		for _, measurement := range result.Measurements {
			if _, exists := a.verified[measurement.CandidateSHA256]; !exists {
				if commitErr := a.commit(measurement); commitErr != nil && err == nil {
					err = commitErr
				}
			}
		}
	}
	if publish != nil {
		if publishErr := publish(a.Publish(search)); publishErr != nil && err == nil {
			err = publishErr
		}
	}
	return err
}

func (a *Archive) Publish(search theorysearch.Snapshot) Snapshot {
	a.version++
	search.SchemaVersion, search.SchemaKind = 3, ResultKind
	search.Status, search.ResponseStatus = "no_verified_result", "no_verified_result"
	search.ReferenceScore = 0
	search.FoundGroupFamilies, search.FoundGroupTuples = 0, 0
	search.SensitivityGroupFamilies, search.SensitivityGroupTuples = 0, 0
	search.Rules = map[string]any{"budget_roll_units_per_wearer": 45, "quarter_grid": true,
		"all_found_aliases": false, "all_verified_aliases": true,
		"reference_scope": "best_attained_comparable_ordinary", "practical_group_rank": "unordered_measured_group",
		"full_search_optimality_proved": false, "confidence_certificate": false, "final_solution_cache_enabled": false,
		"verification_policy": PolicyID, "ordinary_seed_policy": "prepared_config_seed_unchanged",
		"verification_selection":  "reserved_response_priority_then_original_formula_rank_and_exact_candidate_key",
		"support_response_status": a.responseStatus}
	search.CoLeaders, search.Pending = nil, nil
	if search.Unavailable == nil {
		search.Unavailable = []theorysearch.Unavailable{}
	}
	verification := Verification{PolicyID: PolicyID, Limit: a.policy.Limit, Iterations: a.policy.Iterations,
		AttemptedCount: len(a.attempted), CompletedCount: len(a.verified), FailedCount: len(a.failed), EnergyRejectedCount: len(a.energyRejected),
		CandidateCount: len(a.candidates), UnverifiedCount: len(a.candidates) - len(a.verified), OmittedCount: len(a.candidates) - len(a.attempted),
		RemainingBudget: a.remaining(), InProgress: a.inProgress, ResponseLaneReserve: a.policy.ResponseReserve}
	for key := range a.attempted {
		if a.candidates[key].Lane == ResponseLane {
			verification.ResponseLaneAttemptedCount++
		}
	}
	out := Snapshot{Snapshot: search, PublicationVersion: a.version, Verification: verification, CoLeaders: []VerifiedRow{}, Pending: []VerifiedRow{}}
	rows := make([]VerifiedRow, 0, len(a.verified))
	for _, row := range a.verified {
		if row.Measurement.MeasuredDPS > out.ReferenceScore {
			out.ReferenceScore = row.Measurement.MeasuredDPS
		}
		rows = append(rows, cloneVerifiedRow(row))
	}
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].Measurement.MeasuredDPS != rows[j].Measurement.MeasuredDPS {
			return rows[i].Measurement.MeasuredDPS > rows[j].Measurement.MeasuredDPS
		}
		return rows[i].Measurement.CandidateSHA256 < rows[j].Measurement.CandidateSHA256
	})
	if len(rows) > 0 {
		out.Status, out.ResponseStatus = "success", "ordinary_verified"
	}
	for _, row := range rows {
		row.DeficitPercent = 0
		if out.ReferenceScore > 0 {
			row.DeficitPercent = 100 * (out.ReferenceScore - row.Measurement.MeasuredDPS) / out.ReferenceScore
		}
		if row.DeficitPercent <= theorysearch.PracticalBandPercent+1e-12 {
			out.CoLeaders = append(out.CoLeaders, row)
			out.FoundGroupFamilies++
			out.FoundGroupTuples++
		} else {
			row.Reason = "below_verified_practical_band"
			out.Pending = append(out.Pending, row)
		}
		if row.DeficitPercent <= theorysearch.SensitivityBandPercent+1e-12 {
			out.SensitivityGroupFamilies++
			out.SensitivityGroupTuples++
		}
	}
	return out
}
