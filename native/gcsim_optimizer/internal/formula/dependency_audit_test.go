package formula

import "testing"

// Actual source-derived graph slices with independent changed-engine values:
// vector caps, owner-switching extrema, snapshot/flat ancestry and reaction
// participants. The synthetic tests separately test unsupported/frozen paths.
func TestDependencyAuditResponses(t *testing.T) {
	checkEngineResponseSamples(t, "gob11_dependency_audit_samples_v1.json", 14)
	checkContributorDenseAndWearerPaths(t, "gob11_dependency_audit_samples_v1.json")
}
