package main

import "testing"

func TestAllSetsHasUnknownEffectBoundary(t *testing.T) {
	tests := []struct {
		name                    string
		boundaries              []string
		neutralModelUnavailable int
		want                    bool
	}{
		{
			name: "pure search allocation and stabilization limits",
			boundaries: []string{
				"joint_package_seed_allocation_deferred",
				"joint_package_frontier_heuristic",
				"joint_inventory_work_deferred",
				"finalist_stabilization_deferred",
				"joint_reservation_feasibility_unresolved",
			},
		},
		{
			name: "search limits mixed with real guide boundaries",
			boundaries: []string{
				"joint_package_frontier_heuristic",
				"uncaptured_bonus_activation_requires_fresh_context",
				"reaction_inputs_absent_or_over_guide_limit",
			},
			want: true,
		},
		{
			name:       "future boundary remains conservatively unknown",
			boundaries: []string{"future_neutral_schedule_boundary"},
			want:       true,
		},
		{
			name:                    "unavailable neutral model warns without a boundary code",
			neutralModelUnavailable: 1,
			want:                    true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := allSetsHasUnknownEffectBoundary(tt.boundaries, tt.neutralModelUnavailable); got != tt.want {
				t.Fatalf("allSetsHasUnknownEffectBoundary(%v, %d) = %v, want %v", tt.boundaries, tt.neutralModelUnavailable, got, tt.want)
			}
		})
	}
}
