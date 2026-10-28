package main

import (
	"reflect"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
)

func sessionDomainFixture() (contracts.OptimizerRequest, []domain.Package) {
	req := contracts.OptimizerRequest{Wearers: []contracts.Wearer{{WearerKey: "north"}, {WearerKey: "east"}, {WearerKey: "south"}, {WearerKey: "west"}}}
	rows := []domain.Package{{Sets: []contracts.SetRequirement{{SetUID: "a", Count: 4}}}, {}}
	return req, rows
}

func TestTheorySessionDomainsKeepDefaultAndExplicitOrder(t *testing.T) {
	req, packages := sessionDomainFixture()
	domains, err := theorySessionAllowedDomains(req, packages)
	if err != nil {
		t.Fatal(err)
	}
	for _, rows := range domains {
		if !reflect.DeepEqual(rows, packages) {
			t.Fatal("default catalog changed")
		}
	}
	req.TheoryOptions = &contracts.TheorySearchOptions{AllowedPackages: map[string][][]contracts.SetRequirement{
		"east": {{}, {{SetUID: "a", Count: 4}}}, "west": {{{SetUID: "a", Count: 4}}},
	}}
	domains, err = theorySessionAllowedDomains(req, packages)
	if err != nil || domains[1][0].Key() != "none" || domains[1][1].Key() != "a:4" || len(domains[3]) != 1 || domains[3][0].Key() != "a:4" {
		t.Fatalf("explicit package order/domain changed: %v %v", domains, err)
	}
	if !reflect.DeepEqual(domains[0], packages) || !reflect.DeepEqual(domains[2], packages) {
		t.Fatal("one wearer's override changed another wearer")
	}
}

func TestTheorySessionDomainsRejectInvalidBeforeCapture(t *testing.T) {
	req, packages := sessionDomainFixture()
	for name, allowed := range map[string]map[string][][]contracts.SetRequirement{
		"duplicate": {"east": {{}, {}}},
		"empty":     {"east": {}},
		"owner":     {"foreign": {{}}},
		"catalog":   {"east": {{{SetUID: "missing", Count: 4}}}},
		"package":   {"east": {{{SetUID: "a", Count: 3}}}},
	} {
		t.Run(name, func(t *testing.T) {
			req.TheoryOptions = &contracts.TheorySearchOptions{AllowedPackages: allowed}
			if _, err := theorySessionAllowedDomains(req, packages); err == nil {
				t.Fatal("invalid domain accepted before engine preparation")
			}
		})
	}
}
