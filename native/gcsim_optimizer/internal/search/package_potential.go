package search

// Inventory-aware package priority: bound real vectors in every legal slot
// pattern of ONE wearer while the others remain fixed. This evaluates neither
// average pieces nor independently maximized fictitious substats. Approximate
// model potential is separate from a certified fixed-model upper enclosure.
import (
	"context"
	"encoding/binary"
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"math"
)

type PackagePotential struct {
	Upper, Priority                float64
	BoundEvaluations, ReducedNodes int
	PhysicalBuilds                 int64
	PendingPatterns                int
}

func (engine *Engine) WearerPotential(ctx context.Context, anchor domain.Assignment, actor int) (out PackagePotential, err error) {
	out.Upper, out.Priority = math.Inf(-1), math.Inf(-1)
	if engine == nil || actor < 0 || actor >= 4 {
		return out, fmt.Errorf("invalid package potential wearer")
	}
	if err = engine.domain.ValidateAssignment(anchor); err != nil {
		return out, err
	}
	dense, err := engine.domain.DenseDeltas(anchor)
	if err != nil {
		return out, err
	}
	program, err := engine.panel.ArtifactProgram(dense, actor)
	if err != nil {
		return out, err
	}
	vectors, ref, err := engine.domain.ArtifactVectors(actor, program.Coordinates())
	if err != nil {
		return out, err
	}
	out.ReducedNodes = program.NodeCount()
	lanes := engine.lanes(anchor, actor)
	// Intern the repeated family/slot pools first. For2+2 the50 slot patterns
	// share at most15 pools; traversing the whole damage graph50 times before
	// even starting refinement used to dominate full-inventory preparation.
	groups := [][][]float64{}
	patterns := [][]int{}
	byPool := map[string]int{}
	for _, lane := range lanes {
		if err = ctx.Err(); err != nil {
			return out, err
		}
		pattern := make([]int, 5)
		for slot, ids := range lane.pools {
			key := make([]byte, 8*len(ids))
			for i, id := range ids {
				binary.LittleEndian.PutUint64(key[i*8:], uint64(id))
			}
			group, found := byPool[string(key)]
			if !found {
				group = len(groups)
				byPool[string(key)] = group
				pool := [][]float64{}
				for _, id := range ids {
					pool = append(pool, vectors[id])
				}
				groups = append(groups, pool)
			}
			pattern[slot] = group
		}
		patterns = append(patterns, pattern)
		out.PhysicalBuilds = saturatingAdd(out.PhysicalBuilds, lane.raw)
	}
	if len(patterns) == 0 {
		return out, fmt.Errorf("feasible package has no inventory patterns")
	}
	if engine.config.MaxExpandedPerActor < 1 {
		out.Upper, out.Priority = math.Inf(1), math.Inf(1)
		out.PendingPatterns = len(patterns)
		return out, nil
	}
	out.Priority = program.PotentialUnion(groups, patterns, ref)
	out.Upper = out.Priority
	if program.HasUnresolvedDependencies() {
		out.Upper = math.Inf(1)
	}
	out.BoundEvaluations = 1
	return out, nil
}
