package search

import "sort"

// Research heuristic: retain the K strongest local-gradient items per physical
// set and slot, plus the actual incumbent and items occupied by another wearer.
// This is not Pareto/dominance pruning and may miss a better critical balance.
// The shared domain/index is never mutated; a run-local exclusion map expires
// with this candidate run. The final single-neighbor checker stays unfiltered.
func (r *candidateRun) hypothesisFilter(weights map[int64]float64, width int) {
	keep := map[int64]bool{}
	for _, id := range r.anchor[r.actor] {
		keep[id] = true
	}
	for _, ids := range r.engine.domain.CandidateIDsBySlot {
		ordered := append([]int64(nil), ids...)
		sort.SliceStable(ordered, func(i, j int) bool {
			a, b := ordered[i], ordered[j]
			if weights[a] != weights[b] {
				return weights[a] > weights[b]
			}
			return a < b
		})
		counts := map[string]int{}
		for _, id := range ordered {
			if r.used[id] {
				continue
			}
			set, _ := r.engine.domain.ArtifactSetUID(id)
			if counts[set] < width {
				keep[id] = true
				counts[set]++
			}
		}
		for _, id := range ids {
			if !keep[id] {
				r.used[id] = true
			}
		}
	}
}
