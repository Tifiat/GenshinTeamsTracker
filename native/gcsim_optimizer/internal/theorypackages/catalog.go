// Package theorypackages owns Theory's ordered catalog and tuple identities.
// It contains no allocation/search implementation or gameplay rules.
package theorypackages

import (
	"fmt"
	"sort"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
)

// Packages enumerates all declared virtual packages, including the independent
// zero-bonus alternative. A source's unresolved mechanics are not a filter.
// This is the unchanged catalog policy extracted from the retained Theory draft.
func Packages(catalog []domain.SetCapability) ([]domain.Package, error) {
	seen := map[string]bool{}
	out := []domain.Package{{}}
	var pairs []string
	for _, s := range catalog {
		if s.UID == "" || seen[s.UID] || (!s.TwoPiece && s.FourPiece) {
			return nil, fmt.Errorf("invalid theory catalog")
		}
		seen[s.UID] = true
		if s.TwoPiece {
			pairs = append(pairs, s.UID)
			out = append(out, domain.Package{Sets: []contracts.SetRequirement{{SetUID: s.UID, Count: 2}}})
		}
		if s.FourPiece {
			out = append(out, domain.Package{Sets: []contracts.SetRequirement{{SetUID: s.UID, Count: 4}}})
		}
	}
	sort.Strings(pairs)
	for i, a := range pairs {
		for _, b := range pairs[i+1:] {
			out = append(out, domain.Package{Sets: []contracts.SetRequirement{{SetUID: a, Count: 2}, {SetUID: b, Count: 2}}})
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Key() < out[j].Key() })
	return out, nil
}

func Key(p [4]domain.Package) string {
	keys := make([]string, 4)
	for i := range p {
		keys[i] = p[i].Key()
	}
	return strings.Join(keys, "|")
}
