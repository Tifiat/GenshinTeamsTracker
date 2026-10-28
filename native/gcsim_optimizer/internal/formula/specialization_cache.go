package formula

// Run-owned reuse of EXACT fixed inputs, not a rounded-stat/DPS heuristic.
// Neutral All Sets opts in; Selected keeps its current preparation path.
// Immutable reduced nodes are shared, while every caller owns its scratch.
// No disk cache, lifetime beyond the run, or search/pruning policy change.
import (
	"encoding/binary"
	"math"
)

type specializationKey struct {
	source     *ArtifactProgram
	fixed      string
	unresolved bool
}

type SpecializationStats struct{ Hits, Misses, Entries, Nodes int }

type SpecializationCache struct {
	entries                     map[specializationKey]*ArtifactProgram
	order                       []specializationKey
	nodes, maxEntries, maxNodes int
	hits, misses                int
}

func NewSpecializationCache(maxEntries, maxNodes int) *SpecializationCache {
	return &SpecializationCache{entries: map[specializationKey]*ArtifactProgram{}, maxEntries: maxEntries, maxNodes: maxNodes}
}

func (c *SpecializationCache) Stats() SpecializationStats {
	return SpecializationStats{c.hits, c.misses, len(c.entries), c.nodes}
}

func (p *ParametricProgram) WithSpecializationCache(c *SpecializationCache) *ParametricProgram {
	view := p.WithOwnScratch()
	view.specializations = c
	return view
}

func (p *ParametricProgram) specializationKey(fixed []float64, dims map[int]int) specializationKey {
	// Each coordinate has an explicit variable/fixed tag. Variable anchors do
	// not affect the reduced function; fixed +0/-0 remain distinct IEEE inputs.
	data := make([]byte, 9*len(fixed))
	for i, value := range fixed {
		if _, variable := dims[i]; variable {
			data[9*i] = 1
		} else {
			binary.LittleEndian.PutUint64(data[9*i+1:], math.Float64bits(value))
		}
	}
	source := p.specializationSource
	if source == nil {
		source = p.program
	}
	return specializationKey{source, string(data), p.program.unresolved}
}

func copyArtifactScratch(p *ArtifactProgram) *ArtifactProgram {
	copy := *p
	copy.values = append([]float64(nil), p.values...)
	copy.previous = append([]float64(nil), p.previous...)
	return &copy
}

func (c *SpecializationCache) get(key specializationKey) *ArtifactProgram {
	if p := c.entries[key]; p != nil {
		c.hits++
		return copyArtifactScratch(p)
	}
	c.misses++
	return nil
}

func (c *SpecializationCache) put(key specializationKey, p *ArtifactProgram) {
	// Include the retained source identity; eviction must not pin an unbounded
	// collection of full team graphs behind small specialized programs.
	cost := p.NodeCount() + key.source.NodeCount()
	if c.maxEntries <= 0 || cost > c.maxNodes {
		return
	}
	for len(c.order) >= c.maxEntries || c.nodes+cost > c.maxNodes {
		old := c.order[0]
		c.order = c.order[1:]
		c.nodes -= c.entries[old].NodeCount() + old.source.NodeCount()
		delete(c.entries, old)
	}
	c.entries[key] = copyArtifactScratch(p)
	c.order = append(c.order, key)
	c.nodes += cost
}
