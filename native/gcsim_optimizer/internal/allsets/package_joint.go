package allsets

// A bounded escape from single-wearer local optima. Conditional package scores
// suggest alternatives; only a newly scored COMPLETE team can improve the leader.
// The frontier is deliberately heuristic, not a bound or a dominance proof.
import (
	"context"
	"math"
	"sort"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
)

const jointPackageWidth = 3

type packageChoice struct {
	Pack domain.Package
	DPS  float64
}

func offerPackageChoice(rows []packageChoice, pack domain.Package, dps float64) []packageChoice {
	if math.IsNaN(dps) || math.IsInf(dps, 0) {
		return rows
	}
	for i, row := range rows {
		if row.Pack.Key() == pack.Key() {
			if dps <= row.DPS {
				return rows
			}
			rows = append(rows[:i], rows[i+1:]...)
			break
		}
	}
	rows = append(rows, packageChoice{pack, dps})
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].DPS != rows[j].DPS {
			return rows[i].DPS > rows[j].DPS
		}
		return rows[i].Pack.Key() < rows[j].Pack.Key()
	})
	return rows[:min(len(rows), jointPackageWidth)]
}

// One complete physical assignment per package tuple prevents tiny item variants
// of one tuple from consuming the entire escape frontier. No raw item is banned.
func offerPackageTeam(rows []Candidate, c Candidate) []Candidate {
	if math.IsNaN(c.Score.DPS) || math.IsInf(c.Score.DPS, 0) {
		return rows
	}
	key := packageIdentity(c.Packages)
	for i, row := range rows {
		if packageIdentity(row.Packages) == key {
			if c.Score.DPS <= row.Score.DPS {
				return rows
			}
			rows = append(rows[:i], rows[i+1:]...)
			break
		}
	}
	rows = append(rows, c)
	sort.SliceStable(rows, func(i, j int) bool {
		// An epsilon comparison followed by a lexical tie-break is NOT a
		// transitive sort order. Neutral candidates share one unconstrained
		// objective, so use finite raw DPS and then canonical package identity.
		if rows[i].Score.DPS != rows[j].Score.DPS {
			return rows[i].Score.DPS > rows[j].Score.DPS
		}
		return packageIdentity(rows[i].Packages) < packageIdentity(rows[j].Packages)
	})
	return rows[:min(len(rows), jointPackageWidth)]
}

func samePackageTeams(a, b []Candidate) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if packageIdentity(a[i].Packages) != packageIdentity(b[i].Packages) || a[i].Score.Assignment != b[i].Score.Assignment {
			return false
		}
	}
	return true
}

type PackageJointStats struct {
	Roots, Proposals, Seeded, Scored, Unavailable, Refined int
	AllocationDeferred                                     int
	Seconds                                                float64
	Heuristic, Finished                                    bool
}

type packagePairMove struct {
	Actors [2]int
	Packs  [4]domain.Package
}

func packagePairMoves(anchor Candidate, choices [4][]packageChoice) []packagePairMove {
	var out []packagePairMove
	for a := 0; a < 4; a++ {
		for b := a + 1; b < 4; b++ {
			options := func(actor, other int) []domain.Package {
				// Always allow removing a bonus AND moving the other wearer's bonus,
				// even when either single change scored poorly. Feasibility follows
				// below, on real IDs, not from this proposal list.
				rows := []domain.Package{{}, anchor.Packages[other]}
				for _, choice := range choices[actor] {
					rows = append(rows, choice.Pack)
				}
				seen := map[string]bool{}
				unique := []domain.Package{}
				for _, p := range rows {
					if p.Key() != anchor.Packages[actor].Key() && !seen[p.Key()] {
						seen[p.Key()] = true
						unique = append(unique, p)
					}
				}
				return unique
			}
			for _, pa := range options(a, b) {
				for _, pb := range options(b, a) {
					packs := anchor.Packages
					packs[a], packs[b] = pa, pb
					out = append(out, packagePairMove{[2]int{a, b}, packs})
				}
			}
		}
	}
	return out
}

// Keep the other two wearers fixed. BOTH allocation orders are scored, rather
// than picking an order by a sum of gradients that need not rank actual DPS.
// Failure of this bounded allocator is unresolved, not package impossibility.
func packagePairSeeds(ctx context.Context, anchor Candidate, move packagePairMove, priorities [4]map[int64]float64) ([]domain.Assignment, error) {
	var out []domain.Assignment
	seen := map[domain.Assignment]bool{}
	for _, order := range [][2]int{move.Actors, {move.Actors[1], move.Actors[0]}} {
		if e := ctx.Err(); e != nil {
			return out, e
		}
		seed := anchor.Score.Assignment
		occupied := map[int64]bool{}
		for actor, ids := range seed {
			if actor != order[0] && actor != order[1] {
				for _, id := range ids {
					occupied[id] = true
				}
			}
		}
		valid := true
		for _, actor := range order {
			ids, _, e := anchor.Index.PackageLinearAssignment(move.Packs[actor], priorities[actor], occupied)
			if e != nil {
				if !strings.HasPrefix(e.Error(), "no legal completion") {
					return out, e
				}
				valid = false
				break
			}
			seed[actor] = ids
			for _, id := range ids {
				occupied[id] = true
			}
		}
		if valid && !seen[seed] {
			if _, e := anchor.Index.ForPackages(move.Packs, seed, anchor.Index.Coordinates); e != nil {
				return out, e
			}
			seen[seed] = true
			out = append(out, seed)
		}
	}
	return out, nil
}

// The callbacks own source binding, exact team scoring and the EXISTING global
// deadline/work allowance. The small scheduler itself is also tested against an
// exhaustive finite shared-bonus objective, without any engine invocations.
func explorePackagePairs(ctx context.Context, roots []Candidate, choices [4][]packageChoice,
	evaluate func(Candidate, packagePairMove) ([]Candidate, error),
	refine func(Candidate) (Candidate, error), retain func(Candidate), stats *PackageJointStats) error {
	stats.Heuristic = true
	var boundedRoots []Candidate
	for _, root := range roots {
		boundedRoots = offerPackageTeam(boundedRoots, root)
	}
	var frontier []Candidate
	for _, root := range boundedRoots {
		if e := ctx.Err(); e != nil {
			return e
		}
		stats.Roots++
		frontier = offerPackageTeam(frontier, root)
		for _, move := range packagePairMoves(root, choices) {
			if e := ctx.Err(); e != nil {
				return e
			}
			stats.Proposals++
			rows, e := evaluate(root, move)
			for _, c := range rows {
				retain(c)
				frontier = offerPackageTeam(frontier, c)
			}
			if e != nil {
				return e
			}
		}
	}
	for _, c := range frontier {
		if e := ctx.Err(); e != nil {
			return e
		}
		improved, e := refine(c)
		retain(improved) // the callback must return its valid partial incumbent
		stats.Refined++
		if e != nil {
			return e
		}
	}
	stats.Finished = true // bounded lane only, not the full package Cartesian domain
	return nil
}
