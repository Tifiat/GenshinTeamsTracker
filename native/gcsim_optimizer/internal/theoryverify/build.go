// Package theoryverify publishes only ordinary-GCSIM measurements of complete
// idealized Theory builds. Formula search and its checkpoints stay independent.
package theoryverify

import (
	"encoding/json"
	"fmt"
	"math"
	"sort"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
	"genshinteamstracker/native/gcsim_optimizer/internal/theorypackages"
	"genshinteamstracker/native/gcsim_optimizer/internal/theorysearch"
)

const BuildKind = "theory_witness45_v1"

type VerificationLane string

const FormulaLane VerificationLane = "formula"
const ResponseLane VerificationLane = "support_response"

// ProposalPriority orders a reserved response lane only. It is not formula DPS,
// ordinary DPS, a confidence interval or a stat cap. CrossAncestryMissing is
// supplied from the common structural report, never inferred from actor names.
type ProposalPriority struct {
	ForeignPositive       bool
	CrossAncestryMissing  bool
	LegalStatDisplacement float64
	LocalOtherDPSGuide    float64
}

// BuildIdentity includes every coordinate that can change the ordinary run.
// A family, alias name or identical formula value cannot stand in for it.
type BuildIdentity struct {
	Kind      string                    `json:"kind"`
	Packages  []theorysearch.PackageRow `json:"packages"`
	Witness45 alloc.State               `json:"witness45"`
}

// Candidate is also the proposal seam for future generic support-response
// producers. Origins describe how a build was proposed, not verification.
type Candidate struct {
	Build    finalists.FullBuildCandidate
	Row      theorysearch.FamilyRow
	Key      string
	Lane     VerificationLane
	Priority ProposalPriority
}

func (candidate Candidate) Packages() ([4]domain.Package, error) {
	if len(candidate.Row.Aliases) != 1 || len(candidate.Row.Aliases[0].Packages) != 4 {
		return [4]domain.Package{}, fmt.Errorf("candidate has no concrete complete package tuple")
	}
	var wearers [4]string
	for actor, row := range candidate.Row.Aliases[0].Packages {
		wearers[actor] = row.WearerKey
	}
	return validatePackages(candidate.Row.Aliases[0].Packages, wearers)
}

func finite(v float64) bool { return !math.IsNaN(v) && !math.IsInf(v, 0) }

func validatePackages(rows []theorysearch.PackageRow, wearers [4]string) ([4]domain.Package, error) {
	var packages [4]domain.Package
	if len(rows) != len(wearers) {
		return packages, fmt.Errorf("Theory ordinary build requires four wearer packages")
	}
	seen := map[string]bool{}
	for actor, row := range rows {
		if row.WearerKey == "" || seen[row.WearerKey] || row.WearerKey != wearers[actor] {
			return packages, fmt.Errorf("Theory ordinary wearer order changed")
		}
		seen[row.WearerKey] = true
		packages[actor] = domain.Package{Sets: append([]contracts.SetRequirement{}, row.Sets...)}
		if err := packages[actor].Validate(); err != nil {
			return packages, err
		}
	}
	return packages, nil
}

func cloneAlias(alias theorysearch.Alias) theorysearch.Alias {
	alias.Packages = append([]theorysearch.PackageRow{}, alias.Packages...)
	for actor := range alias.Packages {
		alias.Packages[actor].Sets = append([]contracts.SetRequirement{}, alias.Packages[actor].Sets...)
	}
	alias.Uncertainty = append([]string{}, alias.Uncertainty...)
	return alias
}

func cloneOrigins(origins []finalists.FullBuildOrigin) []finalists.FullBuildOrigin {
	out := append([]finalists.FullBuildOrigin{}, origins...)
	for index := range out {
		out[index].DiagnosticCodes = append([]string{}, out[index].DiagnosticCodes...)
	}
	return out
}

// NewCandidate accepts a complete build without knowing a character or an
// inventory ID. Each producer must supply the actual proposed witness/alias.
func NewCandidate(frameSHA string, witness alloc.State, alias theorysearch.Alias, formulaDPS float64, origins []finalists.FullBuildOrigin, refinement int) (Candidate, error) {
	var out Candidate
	if err := alloc.ValidateFull45(witness); err != nil {
		return out, err
	}
	if !finite(formulaDPS) || formulaDPS < 0 || len(origins) == 0 || len(alias.Packages) != 4 {
		return out, fmt.Errorf("invalid Theory ordinary proposal")
	}
	var wearers [4]string
	for actor, row := range alias.Packages {
		wearers[actor] = row.WearerKey
	}
	packages, err := validatePackages(alias.Packages, wearers)
	if err != nil {
		return out, err
	}
	if alias.TupleKey != theorypackages.Key(packages) {
		return out, fmt.Errorf("Theory alias key does not bind its concrete package tuple")
	}
	alias = cloneAlias(alias)
	identity, err := json.Marshal(BuildIdentity{Kind: BuildKind, Packages: alias.Packages, Witness45: witness})
	if err != nil {
		return out, err
	}
	key, err := finalists.FullBuildCandidateSHA256(frameSHA, identity)
	if err != nil {
		return out, err
	}
	allocations, err := theorysearch.AllocationsForWitness(witness, wearers)
	if err != nil {
		return out, err
	}
	out = Candidate{
		Build: finalists.FullBuildCandidate{FrameSHA256: frameSHA, BuildIdentity: identity, FormulaDPS: formulaDPS, Origins: cloneOrigins(origins)},
		Row:   theorysearch.FamilyRow{Family: key, FormulaDPS: formulaDPS, Witness45: witness, Allocations: allocations, Aliases: []theorysearch.Alias{alias}, RefinementLevel: refinement},
		Key:   key,
		Lane:  FormulaLane,
	}
	return out, nil
}

// SearchCandidates expands formula aliases into separately checkable builds.
// Expansion authorizes proposals only; it supplies no ordinary receipt.
func SearchCandidates(frameSHA string, snapshot theorysearch.Snapshot) ([]Candidate, error) {
	out := make([]Candidate, 0, snapshot.TotalFoundTuples)
	for _, group := range [][]theorysearch.FamilyRow{snapshot.CoLeaders, snapshot.Pending} {
		for _, row := range group {
			for _, alias := range row.Aliases {
				origin := finalists.FullBuildOrigin{Kind: "formula_search", Phase: snapshot.Phase, Family: row.Family, ContextSHA256: alias.ContextSHA256, DiagnosticCodes: append([]string{}, alias.Uncertainty...)}
				candidate, err := NewCandidate(frameSHA, row.Witness45, alias, row.FormulaDPS, []finalists.FullBuildOrigin{origin}, row.RefinementLevel)
				if err != nil {
					return nil, err
				}
				out = append(out, candidate)
			}
		}
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Build.FormulaDPS != out[j].Build.FormulaDPS {
			return out[i].Build.FormulaDPS > out[j].Build.FormulaDPS
		}
		return out[i].Key < out[j].Key
	})
	return out, nil
}
