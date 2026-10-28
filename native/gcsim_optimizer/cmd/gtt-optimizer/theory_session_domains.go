package main

import (
	"fmt"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
)

// Keep the allowed package projection independent of the retired allocator.
// Valid inputs preserve catalog/supplied order and the original tuple keys.
func theorySessionAllowedDomains(req contracts.OptimizerRequest, packages []domain.Package) ([4][]domain.Package, error) {
	var domains [4][]domain.Package
	for i := range domains {
		domains[i] = packages
	}
	o := req.TheoryOptions
	if o == nil {
		return domains, nil
	}
	known := map[string]bool{}
	for _, p := range packages {
		known[p.Key()] = true
	}
	owners := map[string]bool{}
	for _, w := range req.Wearers {
		owners[w.WearerKey] = true
	}
	for owner, rows := range o.AllowedPackages {
		if !owners[owner] || len(rows) == 0 {
			return domains, fmt.Errorf("invalid Theory package owner/domain %q", owner)
		}
	}
	for i, w := range req.Wearers {
		if choices, ok := o.AllowedPackages[w.WearerKey]; ok {
			domains[i] = nil
			seen := map[string]bool{}
			for _, rows := range choices {
				p := domain.Package{Sets: rows}
				if err := p.Validate(); err != nil {
					return domains, err
				}
				if !known[p.Key()] {
					return domains, fmt.Errorf("Theory package absent from bound catalog: %s", p.Key())
				}
				if seen[p.Key()] {
					return domains, fmt.Errorf("duplicate Theory package domain for %s", w.WearerKey)
				}
				seen[p.Key()] = true
				domains[i] = append(domains[i], p)
			}
		}
	}
	return domains, nil
}
