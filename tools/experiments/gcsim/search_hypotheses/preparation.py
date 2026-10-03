"""Guarded, research-only preparation overlays for copied Go sources."""


def apply_preparation(root, name, replace):
    if name == "inventory_views":
        path = "internal/domain/index.go"
        replace(root, path, 'exactPackages      bool // All Sets views forbid unrepresented bonus tiers.',
                '''exactPackages      bool // All Sets views forbid unrepresented bonus tiers.
\tvectorCache *artifactVectorCache // shared only by views of this immutable inventory''')
        replace(root, path, 'artifactIndexByID: make(map[int64]int, len(request.Artifacts)),',
                'artifactIndexByID: make(map[int64]int, len(request.Artifacts)),\n\t\tvectorCache: &artifactVectorCache{entries: map[artifactVectorKey]artifactVectorEntry{}},')
        path = "internal/domain/vectors.go"
        replace(root, path, 'import "fmt"', '''import (
\t"fmt"
\t"strconv"
\t"strings"
\t"sync"
)''')
        replace(root, path, '// ArtifactVectors exposes', '''// This cache belongs to one Build result and all its ForPackages views. It
// retains at most 16 coordinate shapes and one million float words; oversized
// shapes are computed normally. Cached vectors are read-only to search callers.
const artifactVectorCacheEntries = 16
const artifactVectorCacheWords = 1_000_000

type artifactVectorKey struct { actor int; coordinates string }
type artifactVectorEntry struct { vectors map[int64][]float64; words int }
type artifactVectorCache struct {
\tmu sync.Mutex
\tentries map[artifactVectorKey]artifactVectorEntry
\torder []artifactVectorKey
\twords int
}

func artifactVectorCoordinateKey(coordinates []string) string {
\tvar b strings.Builder
\tfor _, value := range coordinates {
\t\tb.WriteString(strconv.Itoa(len(value)))
\t\tb.WriteByte(':')
\t\tb.WriteString(value)
\t}
\treturn b.String()
}

// ArtifactVectors exposes''')
        replace(root, path, '''\tvectors := make(map[int64][]float64, len(index.Artifacts))''', '''\tcache := index.vectorCache
\tkey := artifactVectorKey{actor: actor, coordinates: artifactVectorCoordinateKey(coordinates)}
\tif cache != nil {
\t\tcache.mu.Lock()
\t\tentry, ok := cache.entries[key]
\t\tcache.mu.Unlock()
\t\tif ok { return entry.vectors, ref, nil }
\t}
\tvectors := make(map[int64][]float64, len(index.Artifacts))''')
        replace(root, path, '''\treturn vectors, ref, nil
}''', '''\t// Exact actor/ordered-coordinate identity is required. A package view
\t// changes constraints and seed, but neither raw inventory nor reference.
\twords := len(index.Artifacts) * len(coordinates)
\tif cache != nil && words <= artifactVectorCacheWords {
\t\tcache.mu.Lock()
\t\tif previous, ok := cache.entries[key]; ok {
\t\t\tvectors = previous.vectors
\t\t} else {
\t\t\tfor len(cache.order) >= artifactVectorCacheEntries || cache.words+words > artifactVectorCacheWords {
\t\t\t\told := cache.order[0]
\t\t\t\tcache.order = cache.order[1:]
\t\t\t\tcache.words -= cache.entries[old].words
\t\t\t\tdelete(cache.entries, old)
\t\t\t}
\t\t\tcache.entries[key] = artifactVectorEntry{vectors: vectors, words: words}
\t\t\tcache.order = append(cache.order, key)
\t\t\tcache.words += words
\t\t}
\t\tcache.mu.Unlock()
\t}
\treturn vectors, ref, nil
}''')
    elif name == "prepared_replay":
        path = "internal/seteffects/neutral_binding.go"
        replace(root, path, '''\tports   []neutralBoundPort
\treads   *neutralReadIndex''', '''\tports   []neutralBoundPort
\tqueries []RuleQuery
\tqueryOrder []int
\treads   *neutralReadIndex''')
        replace(root, path, '''\t\tb.members = append(b.members, member)''', '''\t\tmember.queries = make([]RuleQuery, len(member.ports))
\t\tmember.queryOrder = make([]int, len(member.ports))
\t\tfor i, port := range member.ports {
\t\t\tmember.queries[i], member.queryOrder[i] = port.query, i
\t\t}
\t\tsort.SliceStable(member.queryOrder, func(i, j int) bool {
\t\t\treturn member.queries[member.queryOrder[i]].Order < member.queries[member.queryOrder[j]].Order
\t\t})
\t\tb.members = append(b.members, member)''')
        replace(root, path, '''\t\tqueries := make([]RuleQuery, len(member.ports))
\t\tfor i, p := range member.ports {
\t\t\tqueries[i] = p.query
\t\t}
\t\tr := b.catalog.ReplayNeutralRules(member.neutral, choices, queries)''', '''\t\tqueries, order := member.preparedQueries()
\t\tr := b.catalog.replayNeutralRulesPrepared(member.neutral, choices, queries, false, order)''')
        replace(root, path, '''func (b *NeutralBinding) EvaluatePackages(choices []RuleChoice) NeutralEffectVector {''', '''// Constructor-owned query slices are never changed by replay. Synthetic
// bindings assembled directly by tests retain the ordinary preparation path.
func (member neutralBoundMember) preparedQueries() ([]RuleQuery, []int) {
\tif len(member.queries) == len(member.ports) && len(member.queryOrder) == len(member.ports) {
\t\treturn member.queries, member.queryOrder
\t}
\tqueries := make([]RuleQuery, len(member.ports))
\tfor i, port := range member.ports { queries[i] = port.query }
\treturn queries, nil
}

func (b *NeutralBinding) EvaluatePackages(choices []RuleChoice) NeutralEffectVector {''')
        path = "internal/seteffects/neutral_expressions.go"
        replace(root, path, '''\t\tqueries := make([]RuleQuery, len(member.ports))
\t\tfor i, p := range member.ports {
\t\t\tqueries[i] = p.query
\t\t}
\t\treplay := b.catalog.CompileNeutralRules(member.neutral, choices, queries)''', '''\t\tqueries, order := member.preparedQueries()
\t\treplay := b.catalog.replayNeutralRulesPrepared(member.neutral, choices, queries, true, order)''')
        path = "internal/seteffects/rule_replay.go"
        replace(root, path, '''\tout = RuleReplay{Values: make([]RuleValue, len(queries)), Uncertainty: []string{}}''', '''\treturn c.replayNeutralRulesPrepared(neutral, choices, queries, symbolic, nil)
}
func (c *SourceCatalog) replayNeutralRulesPrepared(neutral *contracts.NeutralInputs, choices []RuleChoice, queries []RuleQuery, symbolic bool, preparedOrder []int) (out RuleReplay) {
\tout = RuleReplay{Values: make([]RuleValue, len(queries)), Uncertainty: []string{}}''')
        replace(root, path, '''\tsetByKey := map[string]DiscoveredSet{}
\tfor _, s := range c.Sets {
\t\tsetByKey[s.Key] = s
\t}''', '''\tsetByKey := c.setLookup
\tif setByKey == nil { // public replay also accepts ad-hoc test catalogs
\t\tsetByKey = make(map[string]DiscoveredSet, len(c.Sets))
\t\tfor _, s := range c.Sets { setByKey[s.Key] = s }
\t}''')
        replace(root, path, '''\tindices := make([]int, len(queries))
\tfor i := range indices {
\t\tindices[i] = i
\t}
\tsort.SliceStable(indices, func(i, j int) bool { return queries[indices[i]].Order < queries[indices[j]].Order })''', '''\tindices := preparedOrder
\tif indices == nil {
\t\tindices = make([]int, len(queries))
\t\tfor i := range indices { indices[i] = i }
\t\tsort.SliceStable(indices, func(i, j int) bool { return queries[indices[i]].Order < queries[indices[j]].Order })
\t}''')
        path = "internal/seteffects/source_bundle.go"
        replace(root, path, '''\truleSetOrder                                      map[string]int''', '''\truleSetOrder                                      map[string]int
\tsetLookup map[string]DiscoveredSet // immutable after compilation''')
        replace(root, path, '''\tsort.Slice(c.Sets, func(i, j int) bool { return c.Sets[i].Key < c.Sets[j].Key })''', '''\tsort.Slice(c.Sets, func(i, j int) bool { return c.Sets[i].Key < c.Sets[j].Key })
\tc.setLookup = make(map[string]DiscoveredSet, len(c.Sets))
\tfor _, set := range c.Sets { c.setLookup[set.Key] = set }''')
    else:
        raise ValueError(f"Unknown preparation hypothesis: {name}")
