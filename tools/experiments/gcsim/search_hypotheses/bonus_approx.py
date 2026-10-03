"""Source-copy-only literal two-piece hint, never a replacement certificate."""


def apply_bonus_approx(root, replace):
    replace(root, "internal/seteffects/source_bundle.go",
            "scheduleMetadataMu                                sync.Mutex",
            "scheduleMetadataMu                                sync.Mutex\n\thypothesisLiteral2P map[string]map[string]float64")
    replace(root, "internal/seteffects/source_bundle.go",
            "row := DiscoveredSet{Key: item.Key, FourPieceModeled: item.FourPieceModeled}",
            """row := DiscoveredSet{Key: item.Key, FourPieceModeled: item.FourPieceModeled}
		if hint, ok := hypothesisExtractLiteral2P(sources, c.Stats); ok {
			if c.hypothesisLiteral2P == nil { c.hypothesisLiteral2P = map[string]map[string]float64{} }
			c.hypothesisLiteral2P[item.Key] = hint
		}""")
