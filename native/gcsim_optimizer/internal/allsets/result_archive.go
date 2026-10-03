package allsets

import (
	"math"
	"sort"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
)

// resultArchive is output retention, NOT a search frontier. Observing a scored
// legal assignment cannot change the search leader, queue or expansion budget.
// Keep alternatives for every visited package so a group can re-enter the top.
type resultArchive struct {
	perGroup int
	groups   map[string][]Candidate
}

func newResultArchive(perGroup int) *resultArchive {
	return &resultArchive{max(1, perGroup), map[string][]Candidate{}}
}

func (a *resultArchive) offer(c Candidate) {
	a.offerGroup(packageIdentity(c.Packages), c)
}

// The hot candidate observer knows its fixed package: compute its key once.
func (a *resultArchive) offerGroup(key string, c Candidate) {
	if c.Context == nil || math.IsNaN(c.Score.DPS) || math.IsInf(c.Score.DPS, 0) {
		return
	}
	// Retain identities and scores, not thousands of bound formula programs.
	// The few winning groups are rebound from their immutable context at output.
	c.Handle, c.Index = nil, nil
	rows := a.groups[key]
	if len(rows) >= a.perGroup && !candidateBefore(c, rows[len(rows)-1]) {
		return
	}
	for i, old := range rows {
		if old.Score.Assignment == c.Score.Assignment {
			if !candidateBefore(c, old) {
				return
			}
			rows = append(rows[:i], rows[i+1:]...)
			break
		}
	}
	if len(rows) >= a.perGroup && !candidateBefore(c, rows[len(rows)-1]) {
		return
	}
	rows = append(rows, c)
	sort.Slice(rows, func(i, j int) bool { return candidateBefore(rows[i], rows[j]) })
	if len(rows) > a.perGroup {
		rows = rows[:a.perGroup]
	}
	a.groups[key] = rows
}

func (a *resultArchive) top(groups int) []Candidate {
	keys := make([]string, 0, len(a.groups))
	for key, rows := range a.groups {
		if len(rows) > 0 {
			keys = append(keys, key)
		}
	}
	sort.Slice(keys, func(i, j int) bool { return candidateBefore(a.groups[keys[i]][0], a.groups[keys[j]][0]) })
	if len(keys) > groups {
		keys = keys[:groups]
	}
	var out []Candidate
	seen := map[domain.Assignment]bool{}
	for _, key := range keys {
		for _, c := range a.groups[key] {
			if !seen[c.Score.Assignment] {
				out = append(out, c)
				seen[c.Score.Assignment] = true
			}
		}
	}
	return out
}
