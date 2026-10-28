package seteffects

// Source-only neutral rule replay. It evaluates registrations and event guards
// once per effect package, not per artifact combination. Missing API/state or a
// stat-dependent query returns an explicit boundary, never a successful zero.
// Integration with neutral world snapshots and formula ports follows the same
// producer gate; this module alone is not All Sets acceptance.
import (
	"fmt"
	"go/ast"
	"go/token"
	"sort"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

type RuleChoice struct {
	Owner  int
	Key    string
	Pieces int
}
type RuleState struct {
	Owner  int
	Key    string
	Expiry int
}
type RuleQuery struct {
	HitID                        uint64
	Order                        uint64
	Frame, Active, Owner, Target int
	Kind, Mode, Stat             string
	StatKeys                     *[]string
	Attack                       contracts.EventValue
	TargetKeys                   []string
	TargetStateComplete          bool
	// Complete snapshots include ALL character modifiers/status keys, without
	// evaluating their amounts. Partial status-add logs cannot prove absence.
	StateComplete bool
	State         []RuleState
}
type RuleValue struct {
	Value      float64
	Expression *RuleScalar
	Known      bool
	Boundary   string
}
type RuleReplay struct {
	footprint   ruleFootprint
	Values      []RuleValue
	Uncertainty []string
	Boundary    string
	Steps       int
}
type ruleRef struct {
	kind              string
	index             int
	typ               string
	targetType        int
	targetTypeKnown   bool
	targetInterfaceOK bool
}
type ruleSubscription struct {
	vm     *ruleVM
	fn     any
	key    string
	choice RuleChoice
}
type replayMod struct {
	kind, key             string
	owner, target, expiry int
	hitlag, extra         bool
	extension             int
	affected              any
	object                *ruleObject
	vm                    *ruleVM
	choice                RuleChoice
}
type ruleModifierIdentity struct {
	owner, target int
	key           string
}
type ruleWorldView struct {
	world   *contracts.NeutralWorldLedger
	index   int
	facts   *contracts.EventValue
	state   []RuleState
	targets map[int]contracts.EventValue
	valid   bool
}
type ruleReplayHost struct {
	facts                   *contracts.EventValue
	coreStatus              map[string]int
	customFlags             *ruleMap
	energy                  map[int]float64
	flatByHit               map[uint64]any
	flatPorts               map[uint64]bool
	footprint               ruleFootprint
	context                 contracts.NeutralContext
	frame, active           int
	vm                      *ruleVM
	choice                  RuleChoice
	subs                    map[int][]ruleSubscription
	mods                    []replayMod
	state                   []RuleState
	stateComplete           bool
	targets                 map[int]contracts.EventValue
	uncertainty             map[string]bool
	statIndices             map[string]int
	elementLabels           map[int]string
	touched                 map[ruleModifierIdentity]bool
	worldView               ruleWorldView
	hitlagComplete          bool
	symbolic                bool
	order                   uint64
	statReads               map[RuleStatRead]bool
	visibleCharacters       int
	tasks                   []ruleTask
	nextTask, tasksExecuted int
	lifecycle, amountOrder  uint64
	amountCache             map[ruleAmountKey]ruleAmountValue
}

func (c *SourceCatalog) ReplayNeutralRules(neutral *contracts.NeutralInputs, choices []RuleChoice, queries []RuleQuery) RuleReplay {
	return c.replayNeutralRules(neutral, choices, queries, false)
}

// CompileNeutralRules retains stat-dependent scalar expressions. Consumers must
// resolve every neutral-stat leaf before evaluating or bounding this program.
func (c *SourceCatalog) CompileNeutralRules(neutral *contracts.NeutralInputs, choices []RuleChoice, queries []RuleQuery) RuleReplay {
	return c.replayNeutralRules(neutral, choices, queries, true)
}
func (c *SourceCatalog) replayNeutralRules(neutral *contracts.NeutralInputs, choices []RuleChoice, queries []RuleQuery, symbolic bool) (out RuleReplay) {
	return c.replayNeutralRulesPrepared(neutral, choices, queries, symbolic, nil)
}
func (c *SourceCatalog) replayNeutralRulesPrepared(neutral *contracts.NeutralInputs, choices []RuleChoice, queries []RuleQuery, symbolic bool, preparedOrder []int) (out RuleReplay) {
	out = RuleReplay{Values: make([]RuleValue, len(queries)), Uncertainty: []string{}}
	if neutral == nil || !neutral.Context.NoSets || neutral.Ledger.Truncated {
		out.Boundary = "complete neutral event tape required"
		return out
	}
	// Core.AddChar/Player.Init sort by the bound keys.Set enum, not by config
	// row order. Preserve wearer initialization order from the neutral context.
	choices = append([]RuleChoice(nil), choices...)
	perOwner := map[int]int{}
	for _, choice := range choices {
		perOwner[choice.Owner]++
	}
	for _, choice := range choices {
		if _, ok := c.ruleSetOrder[choice.Key]; perOwner[choice.Owner] > 1 && !ok {
			out.Boundary = "source set initialization order unavailable"
			return out
		}
	}
	sort.SliceStable(choices, func(i, j int) bool {
		if choices[i].Owner != choices[j].Owner {
			return choices[i].Owner < choices[j].Owner
		}
		return c.ruleSetOrder[choices[i].Key] < c.ruleSetOrder[choices[j].Key]
	})
	h := &ruleReplayHost{context: neutral.Context, active: neutral.Context.Active, subs: map[int][]ruleSubscription{}, uncertainty: map[string]bool{}, statIndices: map[string]int{}, elementLabels: map[int]string{}, touched: map[ruleModifierIdentity]bool{}, coreStatus: map[string]int{}, energy: map[int]float64{}, flatByHit: map[uint64]any{}}
	h.worldAt(neutral.World, 1)
	h.flatPorts = map[uint64]bool{}
	for _, q := range queries {
		if q.Kind == "flat_event" {
			h.flatPorts[q.HitID] = true
		}
	}
	defer func() { out.footprint = h.footprint }()
	h.symbolic, h.statReads = symbolic, map[RuleStatRead]bool{}
	h.hitlagComplete = neutral.Hitlag != nil && neutral.Hitlag.Complete
	setByKey := c.setLookup
	if setByKey == nil { // public replay also accepts ad-hoc test catalogs
		setByKey = make(map[string]DiscoveredSet, len(c.Sets))
		for _, s := range c.Sets {
			setByKey[s.Key] = s
		}
	}
	vms := []*ruleVM{}
	_, err := ruleTry(func() any {
		counts := map[int]int{}
		seen := map[string]bool{}
		constructors := []struct {
			vm     *ruleVM
			set    any
			choice RuleChoice
		}{}
		// The neutral context's indices retain the engine declaration order.
		last := -1
		for _, choice := range choices {
			if choice.Owner < last || choice.Owner < 0 || choice.Owner >= len(neutral.Context.Characters) || choice.Pieces < 2 || choice.Pieces > 5 {
				ruleFail("invalid neutral rule choice")
			}
			last = choice.Owner
			counts[choice.Owner] += choice.Pieces
			key := fmt.Sprintf("%d:%s", choice.Owner, choice.Key)
			if counts[choice.Owner] > 5 || seen[key] {
				ruleFail("illegal neutral rule package")
			}
			seen[key] = true
			s, ok := setByKey[choice.Key]
			if !ok || s.rule == nil {
				ruleFail("source rule unavailable: " + choice.Key)
			}
			vm := newRuleVM(s.rule, h, 2_000_000)
			vms = append(vms, vm)
			h.vm, h.choice = vm, choice
			// Core.AddChar appends this wearer BEFORE its set constructors;
			// later party members do not exist until their own AddChar calls.
			h.visibleCharacters = choice.Owner + 1
			m := vm.program.modules[vm.program.entry]
			env := m.envs[m.files[0]]
			// Read enum indices from the same bound source evaluator; no numeric
			// GCSIM stat/event/tag constants are copied into the optimizer.
			attributes := vm.program.modules[gcsimImport+"pkg/core/attributes"]
			if attributes == nil {
				ruleFail("rule stat vocabulary absent")
			}
			for symbol, label := range c.Stats {
				name := strings.TrimPrefix(symbol, attributes.name+".")
				h.statIndices[label] = ruleInteger(vm.lookup(attributes.envs[attributes.files[0]], name))
			}
			for symbol, label := range c.Elements {
				name := strings.TrimPrefix(symbol, attributes.name+".")
				h.elementLabels[ruleInteger(vm.lookup(attributes.envs[attributes.files[0]], name))] = label
			}
			var count any = float64(choice.Pieces)
			if symbolic {
				count = pieceTier(choice.Pieces)
			}
			r := vm.invoke(vm.lookup(env, "NewSet"), []any{ruleRef{kind: "core"}, ruleRef{kind: "char", index: choice.Owner}, count, &ruleMap{values: map[any]any{}, valueType: ast.NewIdent("int"), env: env}})
			tuple, ok := r.(ruleTuple)
			if !ok || len(tuple) != 2 || tuple[1] != nil {
				ruleFail("unsupported NewSet result")
			}
			constructors = append(constructors, struct {
				vm     *ruleVM
				set    any
				choice RuleChoice
			}{vm, tuple[0], choice})
		}
		h.visibleCharacters = len(neutral.Context.Characters)
		for _, item := range constructors {
			h.vm, h.choice = item.vm, item.choice
			result := item.vm.invoke(item.vm.selectValue(item.set, "Init"), nil)
			if result != nil {
				if tuple, ok := result.(ruleTuple); !ok || len(tuple) != 0 {
					ruleFail("rule Init failed")
				}
			}
		}
		return nil
	})
	if err != nil {
		out.Boundary = err.Error()
		return out
	}
	indices := preparedOrder
	if indices == nil {
		indices = make([]int, len(queries))
		for i := range indices {
			indices[i] = i
		}
		sort.SliceStable(indices, func(i, j int) bool { return queries[indices[i]].Order < queries[indices[j]].Order })
	}
	eventIndex := 0
	hitlagIndex := 0
	hitlag := []contracts.NeutralHitlagEvent{}
	if h.hitlagComplete {
		hitlag = neutral.Hitlag.Events
	}
	advance := func(order uint64, frame int) error {
		for {
			if hitlagIndex < len(hitlag) && hitlag[hitlagIndex].Order < order && (eventIndex >= len(neutral.Ledger.Events) || hitlag[hitlagIndex].Order < neutral.Ledger.Events[eventIndex].Order) {
				if err := h.tasksBefore(hitlag[hitlagIndex].Frame, neutral.World); err != nil {
					return err
				}
				h.applyHitlag(hitlag[hitlagIndex])
				hitlagIndex++
				continue
			}
			if eventIndex >= len(neutral.Ledger.Events) || neutral.Ledger.Events[eventIndex].Order >= order {
				break
			}
			event := neutral.Ledger.Events[eventIndex]
			eventIndex++
			if err := h.tasksBefore(event.Frame, neutral.World); err != nil {
				return err
			}
			h.frame, h.active = event.Frame, event.Active
			h.order = event.Order
			h.worldAt(neutral.World, event.Order)
			if err := h.emit(event); err != nil {
				return err
			}
		}
		return h.tasksBefore(frame, neutral.World)
	}
	for _, index := range indices {
		query := queries[index]
		if query.Order == 0 || query.Owner < 0 || query.Owner >= len(h.context.Characters) {
			out.Values[index].Boundary = "unbound neutral query"
			continue
		}
		if err := advance(query.Order, query.Frame); err != nil {
			out.Boundary = err.Error()
			return out
		}
		h.frame, h.active = query.Frame, query.Active
		h.order = query.Order
		h.worldAt(neutral.World, query.Order)
		if query.StateComplete {
			h.state, h.stateComplete = query.State, true
		}
		value, err := ruleTry(func() any { return h.query(query) })
		if err != nil {
			out.Values[index].Boundary = err.Error()
		} else {
			if expression, ok := value.(*RuleScalar); ok {
				out.Values[index] = RuleValue{Expression: expression, Known: true}
			} else {
				out.Values[index] = RuleValue{Value: ruleNumber(value), Known: true}
			}
		}
	}
	// The last neutral damage port is not the end of the rotation. A later heal,
	// callback or timer can create a new set hit even when no neutral hit follows.
	// Inspect the whole observed tail and source tasks through the final Tick;
	// never execute tasks beyond the engine-owned horizon.
	if h.context.DurationFrames <= 0 {
		out.Boundary = "neutral schedule horizon is unobserved"
		return out
	}
	if err := advance(^uint64(0), h.context.DurationFrames+1); err != nil {
		out.Boundary = err.Error()
		return out
	}
	for code := range h.uncertainty {
		out.Uncertainty = append(out.Uncertainty, code)
	}
	sort.Strings(out.Uncertainty)
	for _, vm := range vms {
		out.Steps += 2_000_000 - vm.remaining
	}
	return out
}

func (h *ruleReplayHost) emit(event contracts.CombatEvent) error {
	if err := h.observeResourceEvent(event); err != nil {
		return err
	}
	// Match Handler.Emit's range over the original slice header. Replacement/
	// deletion of a later hook is visible; newly appended hooks wait for the next
	// emission. Do not copy the slice or dynamically extend this iteration.
	for _, sub := range h.subs[event.Event] {
		if sub.fn == nil {
			continue
		}
		h.vm, h.choice = sub.vm, sub.choice
		h.lifecycle++
		_, err := ruleTry(func() any {
			args := make([]any, len(event.Arguments))
			for i, a := range event.Arguments {
				args[i] = h.wire(a)
			}
			return h.invokeEvent(sub, event, args)
		})
		if err != nil {
			return fmt.Errorf("%s event: %s", sub.choice.Key, err)
		}
		// The absent set callback's phase relative to neutral callbacks is still
		// an approximation; dispatcher parity is not a response certificate.
		h.uncertainty["counterfactual_callback_phase_observed_schedule"] = true
	}
	return nil
}

func (h *ruleReplayHost) worldAt(world *contracts.NeutralWorldLedger, order uint64) {
	// Queries may temporarily replace state with their own complete snapshot.
	// Rebind the selected world's baseline on every call, including cache hits.
	h.stateComplete = false
	h.state = nil
	h.targets = nil
	h.facts = nil
	if world == nil || !world.Complete {
		h.worldView = ruleWorldView{}
		return
	}
	i := sort.Search(len(world.States), func(i int) bool { return world.States[i].Order > order }) - 1
	if i < 0 {
		h.worldView = ruleWorldView{}
		return
	}
	if cached := h.worldView; cached.valid && cached.world == world && cached.index == i {
		h.facts, h.state, h.targets = cached.facts, cached.state, cached.targets
		h.stateComplete = true
		return
	}
	var state []RuleState
	if len(world.States[i].Modifiers) != 0 {
		state = make([]RuleState, 0, len(world.States[i].Modifiers))
	}
	for _, m := range world.States[i].Modifiers {
		state = append(state, RuleState{m.Owner, m.Key, m.Expiry})
	}
	targets := make(map[int]contracts.EventValue, len(world.States[i].Targets))
	for _, target := range world.States[i].Targets {
		if key, ok := target.Fields["Key"]; ok && key.Kind == "number" {
			targets[int(key.Number)] = target
		}
	}
	h.worldView = ruleWorldView{world: world, index: i, facts: world.States[i].Facts, state: state, targets: targets, valid: true}
	h.facts, h.state, h.targets = h.worldView.facts, h.worldView.state, h.worldView.targets
	h.stateComplete = true
}

func (h *ruleReplayHost) applyHitlag(e contracts.NeutralHitlagEvent) {
	if e.Owner >= 0 {
		for i := range h.tasks {
			if h.tasks[i].owner == e.Owner && h.tasks[i].frame >= e.Frame {
				h.tasks[i].frame = max(e.Frame, h.tasks[i].frame+e.Extension)
			}
		}
	}
	for i := range h.mods {
		m := &h.mods[i]
		if m.owner != e.Owner || m.target != e.Target || !m.hitlag || m.expiry == -1 || m.expiry <= e.Frame {
			continue
		}
		// modifier.Base.Extend clamps the cumulative extension at zero.
		next := max(0, m.extension+e.Extension)
		m.expiry += next - m.extension
		m.extension = next
	}
}

func (h *ruleReplayHost) wire(x contracts.EventValue) any {
	switch x.Kind {
	case "observation":
		return ruleObservation{x}
	case "nil":
		return nil
	case "bool":
		return x.Boolean
	case "number":
		if x.Type != "" {
			return ruleTypedNumber{x.Number, x.Type}
		}
		return x.Number
	case "string":
		return x.Text
	case "array":
		a := &ruleSlice{values: make([]any, len(x.Items)), observed: true}
		for i, v := range x.Items {
			a.values[i] = h.wire(v)
		}
		return a
	case "object":
		o := &ruleObject{typ: strings.TrimPrefix(x.Type, "*"), fields: map[string]any{}, observed: true}
		for name, v := range x.Fields {
			o.fields[name] = h.wire(v)
		}
		return o
	case "target":
		key, ok := x.Fields["Key"]
		if !ok || key.Kind != "number" {
			return ruleUnknown{"target identity missing"}
		}
		r := ruleRef{kind: "target", index: ruleInteger(key.Number), typ: strings.TrimPrefix(x.Type, "*"), targetInterfaceOK: true}
		// Kind=target is emitted only after the producer's info.Target assertion.
		// Retain just this immutable enum fact, not mutable event/snapshot data.
		if value, ok := x.Fields["Type"]; ok && value.Kind == "number" && isRuleFinite(value.Number) && value.Number >= -(1<<31) && value.Number <= 1<<31 && value.Number == float64(int(value.Number)) {
			r.targetType, r.targetTypeKnown = int(value.Number), true
		}
		return r
	case "character":
		index, ok := x.Fields["Index"]
		if !ok || index.Kind != "number" {
			return ruleUnknown{"character identity missing"}
		}
		return ruleRef{kind: "char", index: ruleInteger(index.Number)}
	}
	return ruleUnknown{"unobserved event value: " + x.Kind + ":" + x.Text}
}
func (h *ruleReplayHost) field(receiver any, name string) (any, bool) {
	if out, ok := h.resourceField(receiver, name); ok {
		return out, true
	}
	r, ok := receiver.(ruleRef)
	if !ok {
		return nil, false
	}
	switch r.kind {
	case "core":
		switch name {
		case "$address:F":
			return true, true
		case "F":
			return float64(h.frame), true
		case "Player":
			return ruleRef{kind: "player"}, true
		case "Events":
			return ruleRef{kind: "events"}, true
		case "Tasks":
			return ruleRef{kind: "tasks"}, true
		case "Combat":
			return ruleRef{kind: "combat"}, true
		case "Log":
			return ruleRef{kind: "log"}, true
		}
	case "player":
		if name == "Shields" {
			return ruleRef{kind: "shields"}, true
		}
	case "combat":
		if name == "Events" {
			return ruleRef{kind: "events"}, true
		}
	case "char":
		if r.index < 0 || r.index >= len(h.context.Characters) {
			ruleFail("unknown character reference")
		}
		if value, ok := h.context.Characters[r.index].Facts[name]; ok {
			return h.wire(value), true
		}
		switch name {
		case "$type":
			return gcsimImport + "pkg/core/player/character.CharWrapper", true
		case "Base":
			o, ok := h.wire(h.context.Characters[r.index].Base).(*ruleObject)
			if !ok {
				return ruleUnknown{"character base fields absent"}, true
			}
			o.fields["Key"] = ruleRef{kind: "character_key", index: r.index}
			return o, true
		case "BaseStats":
			return ruleUnknown{"artifact-dependent base stats require expressions"}, true
		}
	case "target":
		if strings.HasPrefix(name, "$implements:") {
			implemented := strings.TrimPrefix(name, "$implements:")
			if (implemented == gcsimImport+"pkg/core/info.Target" && r.targetInterfaceOK) || (r.typ != "" && r.typ == implemented) {
				return true, true
			}
			if target, ok := h.targets[r.index]; ok {
				if value, ok := target.Fields["Interfaces"].Fields[strings.TrimPrefix(name, "$implements:")]; ok {
					return h.wire(value), true
				}
			}
			return ruleUnknown{"target interface was not observed: " + name}, true
		}
		if name == "$type" {
			return r.typ, true
		}
	}
	return nil, false
}
func (h *ruleReplayHost) call(receiver any, name string, args []any) (any, bool) {
	if name == "QueueAttack" || name == "QueueAttackWithSnapShot" {
		if ref, ok := receiver.(ruleRef); ok && (ref.kind == "core" || ref.kind == "char") {
			ruleFail("schedule_change: source queued attack via " + name)
		}
	}
	registration := h.vm != nil && h.vm.registrationEvents != nil && name == "Subscribe"
	if h.vm != nil && h.vm.readOnly && !registration && (strings.HasPrefix(name, "Add") || strings.HasPrefix(name, "Delete") || strings.HasPrefix(name, "Queue") || name == "Subscribe" || name == "Unsubscribe") {
		ruleFail("modifier Amount mutates replay lifecycle: " + name)
	}
	if out, ok := h.resourceCall(receiver, name, args); ok {
		return out, true
	}
	if p, ok := receiver.(rulePackage); ok {
		switch string(p) + "." + name {
		case "fmt.Sprintf":
			if len(args) < 1 {
				ruleFail("format missing")
			}
			return h.vm.formatRule(ruleString(args[0]), args[1:]), true
		case "slices.Contains":
			if len(args) != 2 {
				ruleFail("Contains arity")
			}
			for _, item := range ruleArray(args[0]) {
				if ruleBoolean(ruleBinary(token.EQL, item, args[1])) {
					return true, true
				}
			}
			return false, true
		case gcsimImport + "pkg/core/hacks.NOCharIsSpecial":
			if len(args) != 1 {
				ruleFail("character source fact arity")
			}
			key, ok := args[0].(ruleRef)
			if !ok || key.kind != "character_key" || key.index < 0 || key.index >= len(h.context.Characters) {
				ruleFail("character source fact identity")
			}
			if value, ok := h.context.Characters[key.index].Facts["NOCharIsSpecial"]; ok {
				return h.wire(value), true
			}
			return ruleUnknown{"character initialization source fact absent"}, true
		}
		return nil, false
	}
	r, ok := receiver.(ruleRef)
	if !ok {
		if name == "String" && len(args) == 0 {
			if n, ok := receiver.(ruleTypedNumber); ok {
				if n.typ == gcsimImport+"pkg/core/attributes.Element" {
					if label, ok := h.elementLabels[int(n.value)]; ok {
						return label, true
					}
				}
				return nil, false
			}
			if n, ok := receiver.(float64); ok {
				if label, ok := h.elementLabels[int(n)]; ok {
					return label, true
				}
			}
		}
		return nil, false
	}
	switch r.kind {
	case "tasks":
		if name == "Add" {
			h.queueTask(-1, args)
			return nil, true
		}
	case "log":
		return ruleRef{kind: "log"}, true // Logging cannot change a combat value.
	case "character_key":
		if name == "String" {
			return h.context.Characters[r.index].Key, true
		}
	case "player":
		switch name {
		case "Active":
			return float64(h.active), true
		case "ActiveChar":
			if h.active < 0 || h.active >= h.visibleCharacters {
				ruleFail("active character unavailable")
			}
			return ruleRef{kind: "char", index: h.active}, true
		case "GetMoonsignLevel":
			return float64(h.context.Moonsign), true
		case "GetHexereiCount":
			count := 0
			for _, char := range h.context.Characters[:h.visibleCharacters] {
				value, ok := char.Facts["IsHexerei"]
				if !ok || value.Kind != "bool" {
					return ruleUnknown{"party identity fact absent"}, true
				}
				if value.Boolean {
					count++
				}
			}
			return float64(count), true
		case "Chars":
			a := &ruleSlice{}
			for i := 0; i < h.visibleCharacters; i++ {
				a.values = append(a.values, ruleRef{kind: "char", index: i})
			}
			return a, true
		}
	case "events":
		if name == "Subscribe" && len(args) == 3 {
			event, key := ruleInteger(args[0]), ruleString(args[2])
			if h.vm.registrationEvents != nil {
				if h.vm.registrationEvents[event] {
					ruleFail("map iteration orders callbacks of the same event")
				}
				h.vm.registrationEvents[event] = true
			}
			h.footprint.write(fmt.Sprintf("subscription:%d:%s", event, key))
			f, ok := args[1].(*ruleFunction)
			if !ok {
				ruleFail("unresolved event callback")
			}
			for i, s := range h.subs[event] {
				if s.key == key {
					h.subs[event][i] = ruleSubscription{h.vm, f, key, h.choice}
					return nil, true
				}
			}
			h.subs[event] = append(h.subs[event], ruleSubscription{h.vm, f, key, h.choice})
			return nil, true
		}
		if name == "Unsubscribe" && len(args) == 2 {
			event, key := ruleInteger(args[0]), ruleString(args[1])
			h.footprint.write(fmt.Sprintf("subscription:%d:%s", event, key))
			for i := range h.subs[event] {
				if h.subs[event][i].key == key {
					h.subs[event][i].fn = nil
				}
			}
			return nil, true
		}
	case "target":
		switch name {
		case "Key":
			return float64(r.index), true
		case "Type":
			if r.targetTypeKnown {
				return float64(r.targetType), true
			}
			// Older tapes can omit the event enum. A world observation for the
			// same stable key is still evidence for this immutable target type.
			if target, ok := h.targets[r.index]; ok {
				if value, exists := target.Fields["Type"]; exists && value.Kind == "number" {
					return h.wire(value), true
				}
			}
			return ruleUnknown{"target type was not observed"}, true
		case "AuraContains":
			target, ok := h.targets[r.index]
			if !ok || target.Fields["Auras"].Kind != "array" {
				return ruleUnknown{"target aura was not observed"}, true
			}
			for _, arg := range args {
				index := ruleInteger(arg)
				if index < 0 || index >= len(target.Fields["Auras"].Items) {
					ruleFail("target aura outside observed vocabulary")
				}
				if ruleBoolean(h.wire(target.Fields["Auras"].Items[index])) {
					return true, true
				}
			}
			return false, true
		case "AddResistMod":
			h.addMod("resistance", -1, r.index, args)
			return nil, true
		}
	case "char":
		switch name {
		case "QueueCharTask":
			h.queueTask(r.index, args)
			return nil, true
		case "Index":
			return float64(r.index), true
		case "AddStatMod":
			h.addMod("stat", r.index, -1, args)
			return nil, true
		case "AddAttackMod":
			h.addMod("attack", r.index, -1, args)
			return nil, true
		case "AddReactBonusMod":
			h.addMod("reaction", r.index, -1, args)
			return nil, true
		case "AddHealBonusMod":
			h.addMod("heal_bonus", r.index, -1, args)
			return nil, true
		case "StatusIsActive", "StatModIsActive":
			if len(args) != 1 {
				ruleFail("status arity")
			}
			return h.statusActive(r.index, ruleString(args[0])), true
		case "StatusDuration":
			if len(args) != 1 {
				ruleFail("status duration arity")
			}
			return float64(h.statusDuration(r.index, ruleString(args[0]))), true
		case "AddStatus":
			if len(args) != 3 {
				ruleFail("status add arity")
			}
			d := ruleInteger(args[1])
			expiry := -1
			if d >= 0 {
				expiry = h.frame + d
			}
			h.replaceMod(replayMod{kind: "status", key: ruleString(args[0]), owner: r.index, target: -1, expiry: expiry, hitlag: ruleBoolean(args[2]), vm: h.vm, choice: h.choice})
			return nil, true
		case "DeleteStatus", "DeleteStatMod", "DeleteAttackMod", "DeleteReactBonusMod":
			if len(args) != 1 {
				ruleFail("status delete arity")
			}
			key := ruleString(args[0])
			if name == "DeleteStatMod" {
				h.footprint.writeStat(r.index, "", false)
			}
			h.footprint.write(ruleModifierKey(r.index, -1, key))
			h.touched[ruleModifierIdentity{owner: r.index, target: -1, key: key}] = true
			for i := len(h.mods) - 1; i >= 0; i-- {
				if h.mods[i].owner == r.index && h.mods[i].key == key {
					h.mods = append(h.mods[:i], h.mods[i+1:]...)
				}
			}
			return nil, true
		case "Stat", "NonExtraStat":
			if h.symbolic && len(args) == 1 {
				return h.statExpression(r.index, name, ruleInteger(args[0])), true
			}
			return ruleUnknown{"stat-dependent set amount needs a bound expression: " + name}, true
		case "MaxHP", "TotalAtk", "TotalDef":
			return ruleUnknown{"stat-dependent set amount needs a bound expression: " + name}, true
		}
	case "shields":
		if name == "AddShieldBonusMod" {
			h.uncertainty["shield_absorption_feedback_unmodeled"] = true
			return nil, true
		}
	}
	return nil, false
}
func (h *ruleReplayHost) replaceMod(m replayMod) {
	h.footprint.write(ruleModifierKey(m.owner, m.target, m.key))
	if m.kind == "stat" {
		known := false
		if m.affected != nil {
			index := ruleInteger(m.affected)
			for label, value := range h.statIndices {
				if value == index && label != "n/a" {
					h.footprint.writeStat(m.owner, label, m.extra)
					known = true
				}
			}
		}
		if !known {
			h.footprint.writeStat(m.owner, "", m.extra)
		}
	}
	h.touched[ruleModifierIdentity{owner: m.owner, target: m.target, key: m.key}] = true
	for i, old := range h.mods {
		if old.owner == m.owner && old.target == m.target && old.key == m.key {
			h.mods[i] = m
			return
		}
	}
	h.mods = append(h.mods, m)
}
func (h *ruleReplayHost) addMod(kind string, owner, target int, args []any) {
	if len(args) != 1 {
		ruleFail("modifier arity")
	}
	o, ok := args[0].(*ruleObject)
	if !ok {
		ruleFail("unresolved modifier")
	}
	base, ok := o.fields["Base"].(*ruleObject)
	if !ok {
		ruleFail("modifier base is not source-backed")
	}
	key := ruleString(base.fields["ModKey"])
	duration := ruleInteger(base.fields["Dur"])
	expiry := -1
	if duration != -1 {
		expiry = h.frame + duration
	}
	hitlag := false
	if x, ok := base.fields["Hitlag"]; ok {
		hitlag = ruleBoolean(x)
	}
	extra := false
	if x, ok := o.fields["Extra"]; ok {
		extra = ruleBoolean(x)
	}
	m := replayMod{kind: kind, key: key, owner: owner, target: target, expiry: expiry, hitlag: hitlag, extra: extra, affected: o.fields["AffectedStat"], object: o, vm: h.vm, choice: h.choice}
	if kind != "resistance" {
		if _, ok := o.fields["Amount"].(*ruleFunction); !ok {
			ruleFail("modifier Amount is not an executable source closure")
		}
	}
	h.checkScheduleStat(m)
	h.replaceMod(m)
}
func (h *ruleReplayHost) statusActive(owner int, key string) bool {
	h.footprint.read(ruleModifierKey(owner, -1, key))
	for _, m := range h.mods {
		if m.owner == owner && m.target == -1 && m.key == key {
			if m.hitlag && !h.hitlagComplete {
				h.uncertainty["set_hitlag_expiry_approximate"] = true
			}
			return m.expiry == -1 || m.expiry >= h.frame
		}
	}
	// A deletion must not revive the old modifier from the neutral snapshot.
	if h.touched[ruleModifierIdentity{owner: owner, target: -1, key: key}] {
		return false
	}
	for _, s := range h.state {
		if s.Owner == owner && s.Key == key {
			return s.Expiry == -1 || s.Expiry >= h.frame
		}
	}
	if !h.stateComplete {
		ruleFail("modifier/status absence is not observed: " + key)
	}
	return false
}

// CharWrapper.getModDuration uses strict expiry > frame. In particular a
// permanent (-1) modifier is active but has duration zero, not infinity.
func (h *ruleReplayHost) statusDuration(owner int, key string) int {
	h.footprint.read(ruleModifierKey(owner, -1, key))
	remaining := func(expiry int) int { return max(0, expiry-h.frame) }
	for _, m := range h.mods {
		if m.owner == owner && m.target == -1 && m.key == key {
			if m.hitlag && !h.hitlagComplete {
				h.uncertainty["set_hitlag_expiry_approximate"] = true
			}
			return remaining(m.expiry)
		}
	}
	if h.touched[ruleModifierIdentity{owner: owner, target: -1, key: key}] {
		return 0
	}
	for _, s := range h.state {
		if s.Owner == owner && s.Key == key {
			return remaining(s.Expiry)
		}
	}
	if !h.stateComplete {
		ruleFail("modifier/status absence is not observed: " + key)
	}
	return 0
}

func (h *ruleReplayHost) query(q RuleQuery) any {
	previousVM, previousChoice := h.vm, h.choice
	defer func() { h.vm, h.choice = previousVM, previousChoice }()
	switch q.Kind {
	case "stat", "attack", "reaction", "resistance", "heal_bonus":
	case "flat_event":
		if value, ok := h.flatByHit[q.HitID]; ok {
			return value
		}
		return float64(0)
	default:
		ruleFail("effect input kind is not interpreted: " + q.Kind)
	}
	for _, old := range h.state {
		if old.Owner == q.Owner && (old.Expiry == -1 || old.Expiry > h.frame) && h.touched[ruleModifierIdentity{owner: old.Owner, target: -1, key: old.Key}] {
			ruleFail("set replaces a neutral modifier still present in the formula: " + old.Key)
		}
	}
	if q.Kind == "resistance" {
		for _, key := range q.TargetKeys {
			if h.touched[ruleModifierIdentity{owner: -1, target: q.Target, key: key}] {
				ruleFail("set replaces a neutral target modifier still present in the formula: " + key)
			}
		}
	}
	var sum any = 0.0
	for _, m := range h.mods {
		if m.kind != q.Kind || (q.Kind == "resistance" && m.target != q.Target) || (q.Kind != "resistance" && m.owner != q.Owner) || (m.expiry != -1 && m.expiry <= h.frame) {
			continue
		}
		if m.hitlag && !h.hitlagComplete {
			h.uncertainty["set_hitlag_expiry_approximate"] = true
		}
		if q.Kind == "stat" && q.Mode == "non_extra_stat" && m.extra {
			continue
		}
		if q.Kind == "stat" && q.Mode != "stat" && q.Mode != "snapshot" && q.Mode != "non_extra_stat" {
			ruleFail("query Extra filter unresolved")
		}
		if q.Kind == "stat" && q.StatKeys != nil && m.affected != nil {
			affected := ruleInteger(m.affected)
			// NoStat is read from the bound source's label vocabulary.
			if affected != h.statIndices["n/a"] {
				selected := false
				for _, key := range *q.StatKeys {
					if index, ok := h.statIndices[key]; ok && index == affected {
						selected = true
						break
					}
				}
				if !selected {
					continue
				}
			}
		}
		h.vm, h.choice = m.vm, m.choice
		if q.Kind == "resistance" {
			if !q.TargetStateComplete {
				ruleFail("neutral target modifier keys are not observed")
			}
			// enemy.resist uses expiry > frame, unlike character modifiers' -1.
			if m.expiry <= h.frame {
				continue
			}
			ele := ruleInteger(m.object.fields["Ele"])
			if h.elementLabels[ele] == q.Stat {
				sum = ruleBinary(token.ADD, sum, m.object.fields["Value"])
			}
			continue
		}
		args := []any{}
		switch q.Kind {
		case "attack":
			typ := strings.TrimPrefix(h.targets[q.Target].Type, "*")
			args = []any{h.wire(q.Attack), ruleRef{kind: "target", index: q.Target, typ: typ}}
		case "reaction":
			args = []any{h.wire(q.Attack)}
		}
		before := len(h.mods)
		value, err := h.amount(m, q, args)
		if err != nil {
			ruleFail(err.Error())
		}
		if len(h.mods) != before {
			ruleFail("modifier amount mutates lifecycle")
		}
		if value == nil {
			continue
		}
		if q.Kind == "reaction" || q.Kind == "heal_bonus" {
			sum = ruleBinary(token.ADD, sum, value)
			continue
		}
		index, ok := h.statIndices[q.Stat]
		if !ok {
			ruleFail("unknown output stat: " + q.Stat)
		}
		items := ruleArray(value)
		if index >= len(items) {
			ruleFail("short modifier stat vector")
		}
		sum = ruleBinary(token.ADD, sum, items[index])
	}
	return sum
}

func (h *ruleReplayHost) statExpression(owner int, name string, index int) *RuleScalar {
	h.footprint.statDependent = true
	stat := ""
	for label, i := range h.statIndices {
		if i == index {
			stat = label
			break
		}
	}
	if stat == "" {
		ruleFail("stat read outside bound vocabulary")
	}
	mode := "stat"
	if name == "NonExtraStat" {
		mode = "non_extra_stat"
	}
	h.footprint.readStat(owner, stat, mode)
	read := RuleStatRead{Owner: owner, Stat: stat, Mode: mode, Frame: h.frame, Order: h.order}
	if h.statReads[read] {
		ruleFail("cyclic set stat expression")
	}
	h.statReads[read] = true
	defer delete(h.statReads, read)
	keys := []string{stat}
	added := h.query(RuleQuery{Owner: owner, Frame: h.frame, Order: h.order, Active: h.active, Target: -1, Kind: "stat", Mode: mode, Stat: stat, StatKeys: &keys})
	return scalarOp("add", &RuleScalar{Operation: "neutral_stat", Read: &read}, added)
}
