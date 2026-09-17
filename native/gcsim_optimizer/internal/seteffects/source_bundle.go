package seteffects

import (
	"fmt"
	"sort"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

type SourceItem struct {
	Key              string                          `json:"key"`
	FourPieceModeled bool                            `json:"four_piece_modeled"`
	Sources          map[string]contracts.SourceText `json:"sources"`
}
type SourceBundle struct {
	SchemaVersion        int                  `json:"schema_version"`
	EngineSHA256         string               `json:"engine_sha256"`
	SourceManifestSHA256 string               `json:"source_manifest_sha256"`
	CatalogSHA256        string               `json:"catalog_sha256"`
	StatSource           contracts.SourceText `json:"stat_source"`
	AttackSource         contracts.SourceText `json:"attack_source"`
	ElementSource        contracts.SourceText `json:"element_source"`
	ContextSource        contracts.SourceText `json:"context_source"`
	Items                []SourceItem         `json:"items"`
}
type DiscoveredSet struct {
	Key              string
	FourPieceModeled bool
	Description      Description
	Recipes          []Recipe
	Unresolved       string
}
type SourceCatalog struct {
	EngineSHA256, SourceManifestSHA256, CatalogSHA256 string
	Stats                                             map[string]string
	Tags                                              map[string]int
	Elements                                          map[string]string
	Curves                                            []ScalarSlice
	Sets                                              []DiscoveredSet
	Boundaries                                        []string
}

// The producer verifies the complete original source tree against the built
// manifest. This consumer checks the bound envelope and every included byte
// sequence again. Unsupported source shapes remain local unresolved entries;
// corrupted provenance is never silently accepted as an unknown game mechanic.
func CompileSourceBundle(b SourceBundle, engine contracts.EngineBinding, catalogSHA string) (*SourceCatalog, error) {
	if b.SchemaVersion != 1 || b.EngineSHA256 != engine.ArtifactSHA256 || b.SourceManifestSHA256 != engine.SourceManifestSHA256 || b.CatalogSHA256 != catalogSHA || len(catalogSHA) != 64 || len(b.Items) > 128 {
		return nil, fmt.Errorf("effect source binding mismatch")
	}
	read := func(s contracts.SourceText) ([]byte, error) {
		if s.Text == "" || contracts.TextSHA256(s.Text) != s.SHA256 {
			return nil, fmt.Errorf("effect source bytes changed")
		}
		return []byte(s.Text), nil
	}
	stat, e := read(b.StatSource)
	if e != nil {
		return nil, e
	}
	attack, e := read(b.AttackSource)
	if e != nil {
		return nil, e
	}
	element, e := read(b.ElementSource)
	if e != nil {
		return nil, e
	}
	damage, e := read(b.ContextSource)
	if e != nil {
		return nil, e
	}
	c := &SourceCatalog{EngineSHA256: b.EngineSHA256, SourceManifestSHA256: b.SourceManifestSHA256, CatalogSHA256: b.CatalogSHA256}
	c.Stats, e = StatVocabulary(stat)
	if e != nil {
		c.Boundaries = append(c.Boundaries, "stat_vocabulary_unresolved: "+e.Error())
	}
	c.Tags, e = AttackTagVocabulary(attack)
	if e != nil {
		c.Boundaries = append(c.Boundaries, "attack_vocabulary_unresolved: "+e.Error())
	}
	c.Elements, e = ElementVocabulary(element)
	if e != nil {
		c.Boundaries = append(c.Boundaries, "element_vocabulary_unresolved: "+e.Error())
	}
	c.Curves, e = ExtractScalarSlices(damage, "Resistance", "ResMod")
	if e != nil || len(c.Curves) == 0 {
		c.Boundaries = append(c.Boundaries, "resistance_curve_unresolved")
		c.Curves = nil
	}
	seen := map[string]bool{}
	for _, item := range b.Items {
		if item.Key == "" || seen[item.Key] {
			return nil, fmt.Errorf("duplicate/empty source set")
		}
		seen[item.Key] = true
		sources := map[string][]byte{}
		for name, s := range item.Sources {
			source, e := read(s)
			if e != nil {
				return nil, e
			}
			sources[name] = source
		}
		row := DiscoveredSet{Key: item.Key, FourPieceModeled: item.FourPieceModeled}
		row.Description, e = Discover(sources)
		if e != nil {
			row.Unresolved = e.Error()
		} else {
			row.Recipes = row.Description.Recipes()
		}
		c.Sets = append(c.Sets, row)
	}
	sort.Slice(c.Sets, func(i, j int) bool { return c.Sets[i].Key < c.Sets[j].Key })
	return c, nil
}
