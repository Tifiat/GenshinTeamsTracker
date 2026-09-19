// Package setcontext owns the isolated All Sets formula-context boundary.
// It is not yet wired to the product search/UI. The Go design's All Sets pilot
// requires complete-context reuse or a trusted replacement proof; discovery
// signatures and matching hit schedules alone never authorize reuse.
package setcontext

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

var (
	token         = regexp.MustCompile(`^[a-z][a-z0-9_]*$`)
	digest        = regexp.MustCompile(`^[0-9a-f]{64}$`)
	characterLine = regexp.MustCompile(`^([a-z][a-z0-9_]*)[ \t]+char\b[^;]*;[ \t]*$`)
	setLine       = regexp.MustCompile(`^([a-z][a-z0-9_]*)[ \t]+add[ \t]+set="([a-z][a-z0-9_]*)"[ \t]+count=([1-5])([^;]*);[ \t]*$`)
	statsLine     = regexp.MustCompile(`^([a-z][a-z0-9_]*)[ \t]+add[ \t]+stats\b[^;]*;[ \t]*$`)
	setMention    = regexp.MustCompile(`\badd\s+set\s*=`)
	// GCSIM parseCharAddSet accepts optional +params=[...] after count. Keep
	// the body opaque, but never allow a second count or another statement.
	parameterSuffix = regexp.MustCompile(`^[ \t]*$|^[ \t]+\+params[ \t]*=[ \t]*\[[^\[\];\r\n]*\][ \t]*$`)
)

// Binding retains independent identities, not just an executable path or a
// topology hash. Config bytes bind weapons, rotation, target, energy settings
// and artifact reference stat rows. ReferenceStatsSHA256 binds their producer's
// numeric vector as well. Seeds retain order; the pilot never changes policy.
type Binding struct {
	Engine               contracts.EngineBinding `json:"engine"`
	CatalogSHA256        string                  `json:"catalog_sha256"`
	ReferenceStatsSHA256 string                  `json:"reference_stats_sha256"`
	Seeds                []uint64                `json:"seeds"`
}

// Parameters is the exact opaque suffix from a prepared set row. It is kept
// in identity/rendering, never interpreted as an active gameplay effect.
type Set struct {
	UID        string `json:"uid"`
	Count      int    `json:"count"`
	Parameters string `json:"parameters"`
}

type wearerPackage struct {
	actor      string
	start, end int
	insert     int
	sets       []Set
}

// Context is immutable outside this package. Only prepared declaration rows
// are parsed; we deliberately do not implement another rotation interpreter.
type Context struct {
	key, frameKey, configSHA string
	text                     string
	lines                    []string
	newline                  string
	binding                  Binding
	actors                   []string
	packages                 []wearerPackage
}

func New(binding Binding, prepared string) (*Context, error) {
	for _, value := range []string{binding.Engine.ArtifactSHA256, binding.Engine.BindingSHA256,
		binding.Engine.SourceManifestSHA256, binding.Engine.PatchManifestSHA256,
		binding.CatalogSHA256, binding.ReferenceStatsSHA256} {
		if !digest.MatchString(value) {
			return nil, fmt.Errorf("missing or invalid context identity")
		}
	}
	if len(binding.Seeds) == 0 {
		return nil, fmt.Errorf("context seed panel is empty")
	}
	seenSeeds := map[uint64]bool{}
	for _, seed := range binding.Seeds {
		if seenSeeds[seed] {
			return nil, fmt.Errorf("duplicate context seed")
		}
		seenSeeds[seed] = true
	}
	// Copy caller-owned slices: later request mutation cannot alter this context.
	binding.Seeds = append([]uint64(nil), binding.Seeds...)
	binding.Engine.Capabilities = append([]string(nil), binding.Engine.Capabilities...)
	c := &Context{text: prepared, configSHA: contracts.TextSHA256(prepared), binding: binding, newline: "\n"}
	if strings.Contains(prepared, "\r\n") {
		c.newline = "\r\n"
	}
	c.lines = strings.Split(prepared, c.newline)
	actorIndex := map[string]int{}
	for i, raw := range c.lines {
		line := strings.TrimSpace(raw)
		if strings.HasPrefix(line, "#") || strings.HasPrefix(line, "//") {
			continue
		}
		if m := characterLine.FindStringSubmatch(line); m != nil {
			if _, exists := actorIndex[m[1]]; exists {
				return nil, fmt.Errorf("duplicate character declaration: %s", m[1])
			}
			actorIndex[m[1]] = len(c.packages)
			c.actors = append(c.actors, m[1])
			c.packages = append(c.packages, wearerPackage{actor: m[1], start: -1, end: -1, insert: -1})
		}
		if m := statsLine.FindStringSubmatch(line); m != nil {
			owner, found := actorIndex[m[1]]
			if !found {
				return nil, fmt.Errorf("stats precede character declaration: %s", m[1])
			}
			p := &c.packages[owner]
			if p.insert >= 0 {
				return nil, fmt.Errorf("duplicate prepared stats row: %s", p.actor)
			}
			p.insert = i
		}
		if !setMention.MatchString(line) {
			continue
		}
		m := setLine.FindStringSubmatch(line)
		if m == nil {
			return nil, fmt.Errorf("unsupported prepared set row at line %d", i+1)
		}
		owner, found := actorIndex[m[1]]
		if !found {
			return nil, fmt.Errorf("set precedes character declaration: %s", m[1])
		}
		p := &c.packages[owner]
		if p.end >= 0 && p.end != i {
			return nil, fmt.Errorf("non-contiguous set rows: %s", p.actor)
		}
		if p.start < 0 {
			p.start = i
		}
		p.end = i + 1
		count, _ := strconv.Atoi(m[3])
		p.sets = append(p.sets, Set{UID: m[2], Count: count, Parameters: m[4]})
	}
	if len(c.actors) != 4 {
		return nil, fmt.Errorf("context requires four explicit character declarations")
	}
	for _, p := range c.packages {
		if p.start < 0 && p.insert < 0 {
			return nil, fmt.Errorf("missing prepared stats row: %s", p.actor)
		}
		if p.start >= 0 && p.insert >= 0 && p.end != p.insert {
			return nil, fmt.Errorf("prepared set rows must immediately precede stats: %s", p.actor)
		}
		if len(p.sets) > 0 {
			if err := validateSets(p.sets); err != nil {
				return nil, fmt.Errorf("%s: %w", p.actor, err)
			}
		}
	}
	// Normalize both a populated set block and the neutral no-set baseline to
	// one marker immediately before the actor's stats row.
	var fixed []string
	for i := 0; i < len(c.lines); i++ {
		handled := false
		for _, p := range c.packages {
			if p.start >= 0 && i == p.start {
				fixed = append(fixed, "<gtt-set-context:"+p.actor+">")
				i = p.end - 1
				handled = true
				break
			}
			if p.start < 0 && i == p.insert {
				fixed = append(fixed, "<gtt-set-context:"+p.actor+">")
				break
			}
		}
		if handled {
			continue
		}
		fixed = append(fixed, c.lines[i])
	}
	payload := struct {
		Kind    string
		Binding Binding
		Config  string
	}{"gtt.set_context.v1", binding, prepared}
	var err error
	c.key, err = contracts.CanonicalSHA256(payload)
	if err != nil {
		return nil, err
	}
	payload.Config = strings.Join(fixed, c.newline)
	c.frameKey, err = contracts.CanonicalSHA256(payload)
	return c, err
}

func validateSets(sets []Set) error {
	if len(sets) == 0 || len(sets) > 5 {
		return fmt.Errorf("invalid set row count")
	}
	seen, count := map[string]bool{}, 0
	for _, set := range sets {
		if !token.MatchString(set.UID) || seen[set.UID] || set.Count < 1 || set.Count > 5 {
			return fmt.Errorf("invalid or duplicate set")
		}
		if !parameterSuffix.MatchString(set.Parameters) {
			return fmt.Errorf("invalid opaque set parameters")
		}
		seen[set.UID] = true
		count += set.Count
	}
	if count > 5 {
		return fmt.Errorf("more than five set pieces")
	}
	return nil
}

// Replace renders a WHOLE wearer package at its old declaration position.
// Unchanged rows, raw artifact stats and all other context bytes are preserved.
// Package/item legality belongs to the domain, not this capture renderer (the
// research controls intentionally include incomplete packages).
func (c *Context) Replace(changes map[string][]Set) (*Context, error) {
	if c == nil {
		return nil, fmt.Errorf("nil source context")
	}
	known := map[string]bool{}
	for _, actor := range c.actors {
		known[actor] = true
	}
	for actor, sets := range changes {
		if !known[actor] {
			return nil, fmt.Errorf("unknown wearer %s", actor)
		}
		if err := validateSets(sets); err != nil {
			return nil, err
		}
	}
	var lines []string
	for i := 0; i < len(c.lines); i++ {
		replaced := false
		for _, p := range c.packages {
			sets, changed := changes[p.actor]
			atReplacement := (p.start >= 0 && i == p.start) || (p.start < 0 && i == p.insert)
			if !changed || !atReplacement {
				continue
			}
			for _, set := range sets {
				lines = append(lines, fmt.Sprintf(`%s add set="%s" count=%d%s;`, p.actor, set.UID, set.Count, set.Parameters))
			}
			if p.start >= 0 {
				i = p.end - 1
			}
			replaced = true
			break
		}
		if !replaced || func() bool {
			for _, p := range c.packages {
				if p.start < 0 && i == p.insert {
					if _, changed := changes[p.actor]; changed {
						return true
					}
				}
			}
			return false
		}() {
			lines = append(lines, c.lines[i])
		}
	}
	return New(c.binding, strings.Join(lines, c.newline))
}

func (c *Context) Key() string { return c.key }

// SameFrame includes engine/source/catalog, seeds and every non-set config byte.
// It does not authorize formula reuse; it scopes ordinary finalist comparison.
func (c *Context) SameFrame(other *Context) bool {
	return c != nil && other != nil && c.frameKey == other.frameKey
}
func (c *Context) ConfigSHA256() string { return c.configSHA }
func (c *Context) Config() string       { return c.text }
func (c *Context) Seeds() []uint64      { return append([]uint64(nil), c.binding.Seeds...) }
func (c *Context) Actors() []string     { return append([]string(nil), c.actors...) }
func (c *Context) Sets(actor string) []Set {
	for _, p := range c.packages {
		if p.actor == actor {
			return append([]Set(nil), p.sets...)
		}
	}
	return nil
}
