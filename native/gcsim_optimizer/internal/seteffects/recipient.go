package seteffects

import "strings"

func recipientScope(effect Effect) string {
	if effect.Receiver.Kind == "symbol" || effect.Receiver.Kind == "bound_field" {
		if effect.Receiver.Symbol == "set_owner" {
			return "owner"
		}
		if strings.HasPrefix(effect.Receiver.Symbol, "team_member:") {
			return "team_iteration_member"
		}
	}
	return "unresolved"
}
