"""Research-only literal two-piece direct component; exact replay is fallback."""


def apply_literal_fast(root, replace):
    replace(root, "internal/seteffects/source_bundle.go",
            "hypothesisLiteral2P map[string]map[string]float64",
            "hypothesisLiteral2P map[string]map[string]float64\n\thypothesisFast2P map[string][]hypothesisFastMod")
    replace(root, "internal/seteffects/source_bundle.go",
            "c.hypothesisLiteral2P[item.Key] = hint",
            """c.hypothesisLiteral2P[item.Key] = hint
			if mods, strict := hypothesisExtractFastLiteral2P(sources, c.Stats); strict {
				if c.hypothesisFast2P == nil { c.hypothesisFast2P = map[string][]hypothesisFastMod{} }
				c.hypothesisFast2P[item.Key] = mods
			}""")
    replace(root, "internal/seteffects/neutral_composition.go",
            "ReplaySeconds                                                                                 float64",
            "ReplaySeconds                                                                                 float64\n\tHypothesisFastChoices int")
    replace(root, "internal/seteffects/neutral_composition.go",
            "out := b.compilePackagesJoint([]RuleChoice{choice})",
            """out, fast := b.hypothesisFastLiteralChoice(choice)
			if !fast { out = b.compilePackagesJoint([]RuleChoice{choice}) }""")
