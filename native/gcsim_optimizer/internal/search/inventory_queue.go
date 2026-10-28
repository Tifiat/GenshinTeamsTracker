package search

// Shared best-potential ordering for the All Sets fixed-package inventory
// foundation. These are arithmetic regions, not independently ranked sets.
// Infinite/unknown bounds remain unresolved and ties receive FIFO breadth.
type inventoryRegion struct {
	pools     [5][]int64
	upper     float64
	potential float64
	count     int64
	order     int
	// Resumable frontiers retain exact enumeration position and whether this
	// region already has its own bound (rather than its parent's priority).
	offset  int64
	bounded bool
}
type inventoryRegionQueue []inventoryRegion

func (q inventoryRegionQueue) Len() int { return len(q) }
func (q inventoryRegionQueue) Less(i, j int) bool {
	if q[i].potential != q[j].potential {
		return q[i].potential > q[j].potential
	}
	return q[i].order < q[j].order
}
func (q inventoryRegionQueue) Swap(i, j int) { q[i], q[j] = q[j], q[i] }
func (q *inventoryRegionQueue) Push(x any)   { *q = append(*q, x.(inventoryRegion)) }
func (q *inventoryRegionQueue) Pop() any {
	n := len(*q) - 1
	x := (*q)[n]
	(*q)[n] = inventoryRegion{}
	*q = (*q)[:n]
	return x
}
