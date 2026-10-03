"""Research-only reuse of equal resolved effect components, never item pools."""


def apply_families(root, replace):
    path = "internal/seteffects/neutral_binding.go"
    replace(root, path, "type NeutralBinding struct {", """type NeutralBinding struct {
    hypothesisFamilySerial uint64
    hypothesisTwoPieceFamilies map[[32]byte]bool
    hypothesisPayloads map[string]NeutralExpressions
    hypothesisPayloadOrder []string
    hypothesisPayloadValues int
    hypothesisPayloadNodes int""")
    path = "internal/seteffects/neutral_composition.go"
    replace(root, path, "type NeutralPreparationStats struct {", """type NeutralPreparationStats struct {
    FamilyHits, FamilyMisses, TwoPieceChoices, TwoPieceEffectFamilies int""")
    replace(root, path, "type neutralComponent struct {", """type neutralComponent struct {
    hypothesisIdentity [32]byte""")
    replace(root, path, "\treturn c\n}\n\nfunc (b *NeutralBinding) conflictGroup", """    b.hypothesisIdentify(&c)
    return c
}

func (b *NeutralBinding) conflictGroup""")
    replace(root, path, "b.components[choice] = component", """b.components[choice] = component
                    if choice.Pieces == 2 && component.usable && len(component.expressions) == 0 {
                        b.stats.TwoPieceChoices++
                        if b.hypothesisTwoPieceFamilies == nil { b.hypothesisTwoPieceFamilies = map[[32]byte]bool{} }
                        b.hypothesisTwoPieceFamilies[component.hypothesisIdentity] = true
                        b.stats.TwoPieceEffectFamilies = len(b.hypothesisTwoPieceFamilies)
                    }""")
    replace(root, path, "\tcombined := neutralComponent{raw: make([]float64, len(b.keys)), usable: true}", """    // Legality, activation and the fixed-point dependency merge have ALREADY
    // completed. Equal numbers before this point would not prove independence.
    payloadKey := ""
    if sparse {
        identities := make([]byte, 0, 32*len(groups))
        for _, group := range groups { identities = append(identities, group.component.hypothesisIdentity[:]...) }
        payloadKey = string(identities)
        if cached, ok := b.hypothesisPayloads[payloadKey]; ok {
            b.stats.FamilyHits++
            cached.footprint = ruleFootprint{}
            uncertainty := map[string]bool{}
            for _, group := range groups {
                cached.footprint.merge(group.component.footprint)
                for _, code := range group.component.uncertainty { uncertainty[code] = true }
            }
            cached.Uncertainty = []string{}
            for code := range uncertainty { cached.Uncertainty = append(cached.Uncertainty, code) }
            sort.Strings(cached.Uncertainty)
            return cached
        }
        b.stats.FamilyMisses++
    }
    combined := neutralComponent{raw: make([]float64, len(b.keys)), usable: true}""")
    replace(root, path, "\tsort.Strings(out.Uncertainty)\n\treturn out", """    sort.Strings(out.Uncertainty)
    if sparse { b.hypothesisRetainPayload(payloadKey, out) }
    return out""")
