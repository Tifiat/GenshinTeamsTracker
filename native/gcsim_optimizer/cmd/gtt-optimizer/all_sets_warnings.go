package main

func allSetsHasUnknownEffectBoundary(boundaries []string, neutralModelUnavailable int) bool {
	if neutralModelUnavailable > 0 {
		return true
	}
	for _, boundary := range boundaries {
		switch boundary {
		case "joint_package_seed_allocation_deferred",
			"joint_package_frontier_heuristic",
			"joint_inventory_work_deferred",
			"finalist_stabilization_deferred",
			"joint_reservation_feasibility_unresolved":
			// These describe bounded search work, not unknown model/effect behavior.
		default:
			// Unknown and future boundary codes remain visible as uncertainty.
			return true
		}
	}
	return false
}
