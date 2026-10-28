package theoryprototype

import (
	"container/heap"
	"fmt"
	"math"
	"sort"
)

// BoundRegion is one covered search region. Upper may be +Inf when its bound
// is unresolved; Potential only orders equal-Upper regions and never prunes.
type BoundRegion struct {
	ID        int
	Upper     float64
	Potential float64
}

type boundEntry struct {
	region BoundRegion
	order  uint64
}

type boundHeap []boundEntry

func (h boundHeap) Len() int { return len(h) }
func (h boundHeap) Less(i, j int) bool {
	a, b := h[i], h[j]
	if a.region.Upper != b.region.Upper {
		return a.region.Upper > b.region.Upper
	}
	pa, pb := finitePotential(a.region.Potential), finitePotential(b.region.Potential)
	if pa != pb {
		return pa > pb
	}
	if a.region.ID != b.region.ID {
		return a.region.ID < b.region.ID
	}
	return a.order < b.order
}
func (h boundHeap) Swap(i, j int)   { h[i], h[j] = h[j], h[i] }
func (h *boundHeap) Push(value any) { *h = append(*h, value.(boundEntry)) }
func (h *boundHeap) Pop() any {
	old := *h
	last := old[len(old)-1]
	*h = old[:len(old)-1]
	return last
}
func finitePotential(value float64) float64 {
	if math.IsInf(value, 0) {
		return math.Inf(-1)
	}
	return value
}

// BoundQueue orders regions by descending rigorous Upper, then finite
// Potential, then ID and insertion order. It owns no branching logic or
// coverage certificate; callers must ensure their initial regions and child
// replacement cover every intended combination.
type BoundQueue struct {
	items boundHeap
	next  uint64
}

func (q *BoundQueue) Push(region BoundRegion) error {
	if math.IsNaN(region.Upper) || math.IsNaN(region.Potential) {
		return fmt.Errorf("bound region %d has NaN upper or potential", region.ID)
	}
	heap.Push(&q.items, boundEntry{region: region, order: q.next})
	q.next++
	return nil
}

// Pop removes the best remaining region. A finite feasible threshold prunes
// only regions whose Upper is strictly lower; equality stays eligible. Since
// the heap is ordered by Upper, all lower regions can be discarded together
// once its maximum falls below threshold. Invalid thresholds disable pruning.
func (q *BoundQueue) Pop(threshold float64) (BoundRegion, bool, int) {
	if math.IsNaN(threshold) || math.IsInf(threshold, 1) {
		threshold = math.Inf(-1)
	}
	if len(q.items) == 0 {
		return BoundRegion{}, false, 0
	}
	if q.items[0].region.Upper < threshold {
		pruned := len(q.items)
		q.items = nil
		return BoundRegion{}, false, pruned
	}
	return heap.Pop(&q.items).(boundEntry).region, true, 0
}

func (q *BoundQueue) Len() int { return len(q.items) }
func (q *BoundQueue) MaxUpper() float64 {
	if len(q.items) == 0 {
		return math.Inf(-1)
	}
	return q.items[0].region.Upper
}

// KthLower is the Kth highest finite feasible score across distinct bonus
// combination keys. It returns -Inf until K different keys have valid scores.
// NaN and infinite values are ignored, so they cannot trigger unsafe pruning.
func KthLower(scores map[string]float64, k int) float64 {
	if k <= 0 {
		return math.Inf(-1)
	}
	valid := make([]float64, 0, len(scores))
	for _, score := range scores {
		if finite(score) {
			valid = append(valid, score)
		}
	}
	if len(valid) < k {
		return math.Inf(-1)
	}
	sort.Slice(valid, func(i, j int) bool { return valid[i] > valid[j] })
	return valid[k-1]
}
