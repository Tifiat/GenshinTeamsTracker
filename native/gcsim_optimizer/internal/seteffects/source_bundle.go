package seteffects

import (
	"fmt"
	"sort"
	"sync"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

type SourceItem struct {
	Key              string                          `json:"key"`
	FourPieceModeled bool                            `json:"four_piece_modeled"`
	Sources          map[string]contracts.SourceText `json:"sources"`
}
type SourceBundle struct {
	SchemaVersion        int                             `json:"schema_version"`
	EngineSHA256         string                          `json:"engine_sha256"`
	SourceManifestSHA256 string                          `json:"source_manifest_sha256"`
	CatalogSHA256        string                          `json:"catalog_sha256"`
	StatSource           contracts.SourceText            `json:"stat_source"`
	AttackSource         contracts.SourceText            `json:"attack_source"`
	ElementSource        contracts.SourceText            `json:"element_source"`
	ContextSource        contracts.SourceText            `json:"context_source"`
	RuleLibraries        map[string]contracts.SourceText `json:"rule_libraries,omitempty"`
	Items                []SourceItem                    `json:"items"`
}
type DiscoveredSet struct {
	Key              string
	FourPieceModeled bool
	Description      Description
	Recipes          []Recipe
	Unresolved       string
	rule             *ruleProgram
	RuleUnresolved   string
}
type SourceCatalog struct {
	EngineSHA256, SourceManifestSHA256, CatalogSHA256 string
	Stats                                             map[string]string
	Tags                                              map[string]int
	Elements                                          map[string]string
	Curves                                            []ScalarSlice
	Sets                                              []DiscoveredSet
	Boundaries                                        []string
	ruleSetOrder                                      map[string]int
	setLookup                                         map[string]DiscoveredSet // immutable after compilation
	neutralRules                                      bool
	ParseCache                                        RuleParseCacheStats
	PreparationSeconds                                float64
	LegacyPrepared                                    bool
	scheduleMetadata                                  map[*ruleProgram]scheduleRuleMetadata
	scheduleMetadataMu                                sync.Mutex
}

// HasNeutralRules reports the bound envelope, not completeness of every set.
// Individual unsupported source shapes remain explicit local boundaries.
func (c *SourceCatalog) HasNeutralRules() bool { return c != nil && c.neutralRules }

// The producer verifies the complete original source tree against the built
// manifest. This consumer checks the bound envelope and every included byte
// sequence again. Unsupported source shapes remain local unresolved entries;
// corrupted provenance is never silently accepted as an unknown game mechanic.
func CompileSourceBundle(b SourceBundle, engine contracts.EngineBinding, catalogSHA string) (*SourceCatalog, error) {
	return compileSourceBundle(b, engine, catalogSHA, nil, NewRuleParseCache("", ""), true)
}

// Cache options never enter gameplay identity: each entry is checked against
// the original source bytes before use, and a miss/corruption reparses them.
func CompileSourceBundleCached(b SourceBundle, engine contracts.EngineBinding, catalogSHA string, artifacts []contracts.Artifact, filterInventory bool, cache *RuleParseCache) (*SourceCatalog, error) {
	var feasible map[string]bool
	if filterInventory {
		feasible = inventoryRuleFeasibility(artifacts)
	}
	if cache == nil {
		cache = NewRuleParseCache("", "")
	}
	// The neutral inventory consumer reads executable rules only. Building the
	// old source-recipe description as well is duplicate unused work. Keep it
	// for finite energy, Theory and unfiltered source audits until those routes
	// have an accepted replacement; it is not a neutral fallback.
	legacy := !filterInventory || len(b.RuleLibraries) == 0
	return compileSourceBundle(b, engine, catalogSHA, feasible, cache, legacy)
}

// CompileSourceBundleForCacheWarming parses every source rule and retains
// source-derived schedule metadata without preparing unused legacy recipes.
// It does not filter by an account inventory.
func CompileSourceBundleForCacheWarming(b SourceBundle, engine contracts.EngineBinding, catalogSHA string, cache *RuleParseCache) (*SourceCatalog, error) {
	if cache == nil {
		cache = NewRuleParseCache("", "")
	}
	return compileSourceBundle(b, engine, catalogSHA, nil, cache, false)
}

// A set with fewer than two occupied slot TYPES cannot give any inventory bonus.
// Verify all source bytes, retain catalog identity, but do not parse its rules.
// Individual pieces remain in the inventory and can be used without a bonus.
// nil is the unfiltered path used by Theory/legacy/source audits.
func CompileSourceBundleForInventory(b SourceBundle, engine contracts.EngineBinding, catalogSHA string, artifacts []contracts.Artifact) (*SourceCatalog, error) {
	return compileSourceBundle(b, engine, catalogSHA, inventoryRuleFeasibility(artifacts), NewRuleParseCache("", ""), true)
}

func inventoryRuleFeasibility(artifacts []contracts.Artifact) map[string]bool {
	slots := map[string]map[string]bool{}
	for _, item := range artifacts {
		if slots[item.SetUID] == nil {
			slots[item.SetUID] = map[string]bool{}
		}
		slots[item.SetUID][item.Slot] = true
	}
	feasible := map[string]bool{}
	for key, occupied := range slots {
		feasible[key] = len(occupied) >= 2
	}
	return feasible
}

func compileSourceBundle(b SourceBundle, engine contracts.EngineBinding, catalogSHA string, feasible map[string]bool, cache *RuleParseCache, legacy bool) (*SourceCatalog, error) {
	started := time.Now()
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
	c := &SourceCatalog{EngineSHA256: b.EngineSHA256, SourceManifestSHA256: b.SourceManifestSHA256, CatalogSHA256: b.CatalogSHA256, LegacyPrepared: legacy}
	defer func() { c.PreparationSeconds = time.Since(started).Seconds() }()
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
	libraries := map[string][]byte{}
	if len(b.RuleLibraries) != 0 {
		c.neutralRules = true
		for name, body := range b.RuleLibraries {
			data, err := read(body)
			if err != nil {
				return nil, err
			}
			libraries[name] = data
		}
		for name, body := range map[string][]byte{"pkg/core/attributes/stats.go": stat, "pkg/core/attributes/element.go": element, "pkg/core/attacks/attack.go": attack} {
			if existing, ok := libraries[name]; ok && string(existing) != string(body) {
				return nil, fmt.Errorf("conflicting rule library source")
			}
			libraries[name] = body
		}
	}
	// The live catalog, not just the current inventory, owns retention. Warming
	// another team must not remove parsed rules for its missing artifact sets.
	live := map[string]struct{}{}
	for name, source := range libraries {
		live[cache.sourceKey(name, source)] = struct{}{}
	}
	for _, item := range b.Items {
		for name, source := range item.Sources {
			live[cache.sourceKey(name, []byte(source.Text))] = struct{}{}
		}
	}
	defer func() {
		// Legacy-only envelopes intentionally omit rule libraries. They neither
		// populate nor own this cache, so must not evict another mode's live libs.
		if c.neutralRules {
			_ = cache.cleanup(live) // cleanup failures are observable in cache Stats
		}
		c.ParseCache = cache.Stats()
	}()
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
		if feasible != nil && !feasible[item.Key] {
			row.Unresolved, row.RuleUnresolved = "inventory_bonus_unassemblable", "inventory_bonus_unassemblable"
			c.Sets = append(c.Sets, row)
			continue
		}
		if legacy {
			row.Description, e = Discover(sources)
			if e != nil {
				row.Unresolved = e.Error()
			} else {
				row.Recipes = row.Description.Recipes()
			}
		}
		if len(libraries) != 0 {
			before := cache.Stats()
			row.rule, e = compileRuleProgramCached(sources, libraries, cache)
			after := cache.Stats()
			if e != nil && (after.WritableHits > before.WritableHits || after.BundledHits > before.BundledHits) {
				// A structurally readable entry can still fail semantic loading.
				// Retry source parsing once; unsupported source is not a loop.
				fresh := make(map[string][]byte, len(sources)+len(libraries))
				for name, source := range libraries {
					fresh[name] = source
				}
				for name, source := range sources {
					fresh[name] = source
				}
				_ = cache.invalidateSources(fresh)
				row.rule, e = compileRuleProgramCached(sources, libraries, cache)
			}
			if e != nil {
				row.RuleUnresolved = e.Error()
			}
		} else {
			row.RuleUnresolved = "neutral rule libraries absent"
		}
		c.Sets = append(c.Sets, row)
	}
	sort.Slice(c.Sets, func(i, j int) bool { return c.Sets[i].Key < c.Sets[j].Key })
	c.setLookup = make(map[string]DiscoveredSet, len(c.Sets))
	for _, set := range c.Sets {
		c.setLookup[set.Key] = set
	}
	c.ruleSetOrder = map[string]int{}
	for _, set := range c.Sets {
		if set.rule == nil {
			continue
		}
		v := newRuleVM(set.rule, nil, 10000)
		if keys := v.program.modules[gcsimImport+"pkg/core/keys"]; keys != nil {
			_, err := ruleTry(func() any {
				names := ruleArray(v.lookup(keys.envs[keys.files[0]], "_SetNames"))
				values := ruleArray(v.lookup(keys.envs[keys.files[0]], "_SetValues"))
				if len(names) != len(values) {
					ruleFail("set key registry mismatch")
				}
				for i, name := range names {
					c.ruleSetOrder[ruleString(name)] = ruleInteger(values[i])
				}
				return nil
			})
			if err != nil {
				return nil, fmt.Errorf("source set order: %w", err)
			}
		}
		break
	}
	return c, nil
}
