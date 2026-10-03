package seteffects

// A package is a bonus tier, whereas a physical build can contain three or five
// pieces. Preserve that distinction in the source interpreter instead of
// assuming NewSet(count=2/4) represents every build in the package. An executed
// comparison must have the same answer for every represented count. A count
// used as an amount, index or other unmodeled operation fails closed.
import "go/token"

type rulePieceTier struct{ low, high float64 }

func pieceTier(count int) rulePieceTier {
	if count >= 2 && count <= 3 {
		return rulePieceTier{2, 3}
	}
	if count >= 4 && count <= 5 {
		return rulePieceTier{4, 5}
	}
	ruleFail("invalid physical piece tier")
	return rulePieceTier{}
}

func pieceTierComparison(op token.Token, a, b any) any {
	switch op {
	case token.EQL, token.NEQ, token.LSS, token.LEQ, token.GTR, token.GEQ:
	default:
		ruleFail("piece count affects more than package activation")
	}
	values := func(value any) []any {
		if tier, ok := value.(rulePieceTier); ok {
			return []any{tier.low, tier.high}
		}
		return []any{value}
	}
	var answer bool
	first := true
	for _, x := range values(a) {
		for _, y := range values(b) {
			value := ruleBoolean(ruleBinary(op, x, y))
			if !first && value != answer {
				ruleFail("physical piece counts are not equivalent within package tier")
			}
			answer, first = value, false
		}
	}
	return answer
}
