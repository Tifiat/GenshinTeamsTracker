package allsets

// Complete real-build scores order this queue. They are NOT upper bounds.
import (
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
)

type neutralProposal struct {
	actor    int
	pack     domain.Package
	seed     domain.Assignment
	priority float64
	order    int
	screen   search.CandidateReport
}
type neutralProposalQueue []*neutralProposal

func (q neutralProposalQueue) Len() int { return len(q) }
func (q neutralProposalQueue) Less(i, j int) bool {
	if q[i].priority != q[j].priority {
		return q[i].priority > q[j].priority
	}
	return q[i].order < q[j].order
}
func (q neutralProposalQueue) Swap(i, j int) { q[i], q[j] = q[j], q[i] }
func (q *neutralProposalQueue) Push(x any)   { *q = append(*q, x.(*neutralProposal)) }
func (q *neutralProposalQueue) Pop() any {
	n := len(*q) - 1
	p := (*q)[n]
	(*q)[n] = nil
	*q = (*q)[:n]
	return p
}
