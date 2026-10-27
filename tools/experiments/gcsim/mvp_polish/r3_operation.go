package contracts

import "os"

// Fixed at process startup, never an environment lookup inside the node loop.
var r3OperationSwitch = os.Getenv("GTT_R3_OPERATION_SWITCH") == "1"

func r3OperationSupported(operation string) bool {
	if r3OperationSwitch {
		switch operation {
		case "constant", "artifact_stat", "add", "multiply", "min", "max", "power", "opaque_frozen", "select_lt":
			return true
		}
		return false
	}
	allowed := map[string]bool{
		"constant": true, "artifact_stat": true, "add": true, "multiply": true,
		"min": true, "max": true, "power": true, "opaque_frozen": true, "select_lt": true,
	}
	return allowed[operation]
}
