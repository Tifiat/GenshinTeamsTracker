package seteffects

// Schedule metadata is a source-derived hint, not proof that an effect is
// active for a context. Runtime routing first asks the neutral replay; its
// schedule_change boundary is the authority for whether a separate capture is
// needed.
import (
	"fmt"
	"go/ast"
	"go/token"
	"sort"
	"strconv"
	"strings"
)

const scheduleAnalysisWorkLimit = 12000

type ScheduleCaptureTier struct {
	Pieces           int      `json:"pieces"`
	Potential        bool     `json:"potential"`
	AnalysisComplete bool     `json:"analysis_complete"`
	Reasons          []string `json:"reasons,omitempty"`
}

// ScheduleCaptureMetadata contains no team or run state and can be serialized
// beside parsed rules. Reasons describe potential source hazards only.
type ScheduleCaptureMetadata struct {
	SetUID string                `json:"set_uid"`
	Tiers  []ScheduleCaptureTier `json:"tiers"`
}

type scheduleTierMetadata struct {
	reasons   []string
	complete  bool
	potential bool
}

type scheduleRuleMetadata struct {
	tiers map[int]scheduleTierMetadata
}

// ScheduleCaptureMetadata reports source-only potential hazards for every
// catalog row. An incomplete row is explicit; it is never serialized as a
// clean bill of health.
func (c *SourceCatalog) ScheduleCaptureMetadata() []ScheduleCaptureMetadata {
	if c == nil {
		return nil
	}
	rows := make([]ScheduleCaptureMetadata, 0, len(c.Sets))
	for _, set := range c.Sets {
		metadata := c.scheduleMetadataFor(set.rule)
		row := ScheduleCaptureMetadata{SetUID: set.Key, Tiers: make([]ScheduleCaptureTier, 0, 2)}
		for _, pieces := range []int{2, 4} {
			tier := metadata.tiers[pieces]
			row.Tiers = append(row.Tiers, ScheduleCaptureTier{
				Pieces: pieces, Potential: tier.potential,
				AnalysisComplete: tier.complete,
				Reasons:          append([]string(nil), tier.reasons...),
			})
		}
		rows = append(rows, row)
	}
	return rows
}

// RequiresScheduleCapture returns potential source reasons for selected sets.
// The boolean is not a routing decision: a runtime schedule_change boundary
// must still be observed before an exact-context capture is made.
func (c *SourceCatalog) RequiresScheduleCapture(choices []RuleChoice) (bool, []string) {
	if c == nil {
		return false, nil
	}
	byKey := make(map[string]DiscoveredSet, len(c.Sets))
	for _, set := range c.Sets {
		byKey[set.Key] = set
	}
	reasons := map[string]bool{}
	for _, choice := range choices {
		set, ok := byKey[choice.Key]
		if !ok || choice.Pieces < 2 || choice.Pieces > 5 {
			continue
		}
		pieces := 2
		if choice.Pieces >= 4 {
			pieces = 4
		}
		tier := c.scheduleMetadataFor(set.rule).tiers[pieces]
		if !tier.potential {
			continue
		}
		for _, reason := range tier.reasons {
			reasons[fmt.Sprintf("schedule_capture_potential:owner_%d:set_%s:pieces_%d:%s", choice.Owner, choice.Key, pieces, reason)] = true
		}
	}
	out := make([]string, 0, len(reasons))
	for reason := range reasons {
		out = append(out, reason)
	}
	sort.Strings(out)
	return len(out) != 0, out
}

func (c *SourceCatalog) scheduleMetadataFor(program *ruleProgram) scheduleRuleMetadata {
	c.scheduleMetadataMu.Lock()
	defer c.scheduleMetadataMu.Unlock()
	if c.scheduleMetadata == nil {
		c.scheduleMetadata = map[*ruleProgram]scheduleRuleMetadata{}
	}
	if metadata, ok := c.scheduleMetadata[program]; ok {
		return metadata
	}
	metadata := analyzeScheduleProgram(program, c.Stats)
	c.scheduleMetadata[program] = metadata
	return metadata
}

type scheduleFunctionVisit struct {
	function     *ruleFunction
	values       map[string]float64
	countNames   map[string]bool
	conservative bool
}

type scheduleAnalyzer struct {
	program      *ruleProgram
	module       *ruleModule
	count        int
	speedSymbols map[string]bool
	hazards      map[string]bool
	visited      map[string]bool
	queue        []scheduleFunctionVisit
	work         int
	incomplete   bool
}

func analyzeScheduleProgram(program *ruleProgram, stats map[string]string) scheduleRuleMetadata {
	out := scheduleRuleMetadata{tiers: map[int]scheduleTierMetadata{}}
	if program == nil || program.modules[program.entry] == nil || program.modules[program.entry].functions["NewSet"] == nil {
		for _, pieces := range []int{2, 4} {
			out.tiers[pieces] = scheduleTierMetadata{reasons: []string{"analysis_unavailable_rule_or_constructor"}, complete: false}
		}
		return out
	}
	for _, pieces := range []int{2, 4} {
		out.tiers[pieces] = analyzeScheduleTier(program, stats, pieces)
	}
	return out
}

func analyzeScheduleTier(program *ruleProgram, stats map[string]string, pieces int) scheduleTierMetadata {
	module := program.modules[program.entry]
	constructor := module.functions["NewSet"]
	a := &scheduleAnalyzer{
		program: program, module: module, count: pieces,
		speedSymbols: map[string]bool{}, hazards: map[string]bool{}, visited: map[string]bool{},
	}
	for symbol, label := range stats {
		if label == "atkspd%" {
			a.speedSymbols[symbol] = true
		}
	}
	values, countNames := map[string]float64{}, map[string]bool{}
	parameters := scheduleParameterNames(constructor.typ)
	if len(parameters) >= 3 && parameters[2] != "" {
		values[parameters[2]] = float64(pieces)
		countNames[parameters[2]] = true
	}
	a.queue = append(a.queue, scheduleFunctionVisit{function: constructor, values: values, countNames: countNames})
	if init := scheduleInitFor(constructor); init != nil {
		// Init executes after construction. Its receiver state is not modeled
		// here, so count guards inside it remain potential for either tier.
		a.queue = append(a.queue, scheduleFunctionVisit{function: init, values: map[string]float64{}, countNames: map[string]bool{}, conservative: true})
	}
	for len(a.queue) > 0 && !a.incomplete {
		visit := a.queue[0]
		a.queue = a.queue[1:]
		key := scheduleVisitKey(visit)
		if a.visited[key] {
			continue
		}
		a.visited[key] = true
		a.walkBlock(visit, visit.function.body)
	}
	if a.incomplete {
		a.hazards["analysis_work_limit"] = true
	}
	reasons := make([]string, 0, len(a.hazards))
	for reason := range a.hazards {
		reasons = append(reasons, reason)
	}
	sort.Strings(reasons)
	return scheduleTierMetadata{reasons: reasons, complete: !a.incomplete, potential: hasScheduleHazard(reasons)}
}

func hasScheduleHazard(reasons []string) bool {
	for _, reason := range reasons {
		if strings.HasPrefix(reason, "attack_speed_source") || strings.HasPrefix(reason, "queued_attack_source") {
			return true
		}
	}
	return false
}

func scheduleParameterNames(typ *ast.FuncType) []string {
	var names []string
	if typ == nil || typ.Params == nil {
		return nil
	}
	for _, field := range typ.Params.List {
		if len(field.Names) == 0 {
			names = append(names, "")
			continue
		}
		for _, name := range field.Names {
			names = append(names, name.Name)
		}
	}
	return names
}

func scheduleInitFor(constructor *ruleFunction) *ruleFunction {
	if constructor == nil || constructor.env == nil || constructor.typ == nil || constructor.typ.Results == nil || len(constructor.typ.Results.List) == 0 {
		return nil
	}
	typeName := ruleTypeName(constructor.typ.Results.List[0].Type, constructor.env)
	if typeName == "" {
		return nil
	}
	return constructor.env.module.functions[typeName+".Init"]
}

func scheduleVisitKey(visit scheduleFunctionVisit) string {
	keys := make([]string, 0, len(visit.values))
	for key := range visit.values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	var b strings.Builder
	fmt.Fprintf(&b, "%p:%t", visit.function, visit.conservative)
	for _, key := range keys {
		fmt.Fprintf(&b, ":%s=%g", key, visit.values[key])
	}
	keys = keys[:0]
	for key := range visit.countNames {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for _, key := range keys {
		fmt.Fprintf(&b, ":count=%s", key)
	}
	return b.String()
}

// walkBlock follows only straightforward count branches. It stops a path at a
// definite return, which keeps a 2-piece early-return guard from leaking a
// later 4-piece schedule effect into the 2-piece metadata.
func (a *scheduleAnalyzer) walkBlock(visit scheduleFunctionVisit, block *ast.BlockStmt) bool {
	if block == nil {
		return false
	}
	values, countNames := cloneScheduleNumbers(visit.values), cloneScheduleNames(visit.countNames)
	for _, statement := range block.List {
		if a.work >= scheduleAnalysisWorkLimit {
			a.incomplete = true
			return false
		}
		visit.values, visit.countNames = values, countNames
		if a.walkStatement(visit, statement) {
			return true
		}
		if assignment, ok := statement.(*ast.AssignStmt); ok {
			a.applyScheduleAssignment(visit, assignment)
		}
		if declaration, ok := statement.(*ast.DeclStmt); ok {
			a.applyScheduleDeclaration(visit, declaration)
		}
	}
	return false
}

func (a *scheduleAnalyzer) walkStatement(visit scheduleFunctionVisit, statement ast.Stmt) bool {
	a.work++
	switch row := statement.(type) {
	case *ast.BlockStmt:
		return a.walkBlock(visit, row)
	case *ast.IfStmt:
		if row.Init != nil {
			a.walkStatement(visit, row.Init)
		}
		a.scanNode(visit, row.Cond)
		condition := a.scheduleBool(row.Cond, visit.values)
		if condition.known {
			if condition.value {
				return a.walkBlock(visit, row.Body)
			}
			if row.Else != nil {
				return a.walkStatement(visit, row.Else)
			}
			return false
		}
		yesVisit, noVisit := cloneScheduleVisit(visit), cloneScheduleVisit(visit)
		if scheduleUsesName(row.Cond, visit.countNames) {
			yesVisit.conservative, noVisit.conservative = true, true
		}
		yesReturns := a.walkBlock(yesVisit, row.Body)
		noReturns := false
		if row.Else != nil {
			noReturns = a.walkStatement(noVisit, row.Else)
		}
		return row.Else != nil && yesReturns && noReturns
	case *ast.ReturnStmt:
		for _, result := range row.Results {
			a.scanNode(visit, result)
		}
		return true
	case *ast.AssignStmt:
		for _, expression := range row.Rhs {
			a.scanNode(visit, expression)
		}
		for _, expression := range row.Lhs {
			a.scanNode(visit, expression)
		}
	case *ast.DeclStmt:
		if declaration, ok := row.Decl.(*ast.GenDecl); ok {
			for _, spec := range declaration.Specs {
				if value, ok := spec.(*ast.ValueSpec); ok {
					for _, expression := range value.Values {
						a.scanNode(visit, expression)
					}
				}
			}
		}
	case *ast.ExprStmt:
		a.scanNode(visit, row.X)
	case *ast.GoStmt:
		a.scanNode(visit, row.Call)
	case *ast.DeferStmt:
		a.scanNode(visit, row.Call)
	case *ast.LabeledStmt:
		return a.walkStatement(visit, row.Stmt)
	default:
		// Loops, switches, and uncommon forms are potential-only: inspect their
		// nested source conservatively, without interpreting arbitrary Go.
		visit.conservative = true
		a.scanNode(visit, statement)
	}
	return false
}

func (a *scheduleAnalyzer) scanNode(visit scheduleFunctionVisit, node ast.Node) {
	if node == nil || a.incomplete {
		return
	}
	ast.Inspect(node, func(node ast.Node) bool {
		if node == nil || a.incomplete {
			return false
		}
		a.work++
		if a.work > scheduleAnalysisWorkLimit {
			a.incomplete = true
			return false
		}
		switch row := node.(type) {
		case *ast.SelectorExpr:
			if a.isAttackSpeed(row, visit.function.env) {
				a.addHazard(visit, "attack_speed_source")
			}
		case *ast.FuncLit:
			closure := cloneScheduleVisit(visit)
			a.walkBlock(closure, row.Body)
			return false
		case *ast.CallExpr:
			selector, ok := row.Fun.(*ast.SelectorExpr)
			if !ok {
				if id, ok := row.Fun.(*ast.Ident); ok {
					if target := a.module.functions[id.Name]; target != nil {
						a.enqueueCall(visit, target, row.Args)
					}
				}
				return true
			}
			method := selector.Sel.Name
			switch method {
			case "QueueAttack", "QueueAttackWithSnapShot":
				a.addHazard(visit, "queued_attack_source")
			}
			for _, target := range a.localTargets(visit.function, selector) {
				a.enqueueCall(visit, target, row.Args)
			}
		}
		return true
	})
}

func (a *scheduleAnalyzer) localTargets(current *ruleFunction, selector *ast.SelectorExpr) []*ruleFunction {
	if selector == nil || selector.Sel == nil {
		return nil
	}
	if id, ok := selector.X.(*ast.Ident); ok && current != nil && current.env != nil {
		if _, imported := current.env.imports[id.Name]; imported {
			return nil
		}
	}
	suffix := "." + selector.Sel.Name
	var targets []*ruleFunction
	for name, function := range a.module.functions {
		if strings.HasSuffix(name, suffix) {
			targets = append(targets, function)
		}
	}
	return targets
}

func (a *scheduleAnalyzer) enqueueCall(parent scheduleFunctionVisit, target *ruleFunction, args []ast.Expr) {
	parameters := scheduleParameterNames(target.typ)
	values, countNames := map[string]float64{}, map[string]bool{}
	for index, parameter := range parameters {
		if parameter == "" || index >= len(args) {
			continue
		}
		if value, known := scheduleNumber(args[index], parent.values); known {
			values[parameter] = value
		}
		if scheduleUsesName(args[index], parent.countNames) {
			countNames[parameter] = true
		}
	}
	a.queue = append(a.queue, scheduleFunctionVisit{function: target, values: values, countNames: countNames, conservative: parent.conservative})
}

func (a *scheduleAnalyzer) isAttackSpeed(selector *ast.SelectorExpr, env *ruleEnv) bool {
	id, ok := selector.X.(*ast.Ident)
	if !ok || len(a.speedSymbols) == 0 {
		return false
	}
	for current := env; current != nil; current = current.parent {
		if imported, ok := current.imports[id.Name]; ok {
			return a.speedSymbols[imported+"."+selector.Sel.Name]
		}
	}
	return false
}

func (a *scheduleAnalyzer) addHazard(visit scheduleFunctionVisit, reason string) {
	a.hazards[reason] = true
	if visit.conservative {
		a.hazards[reason+"_count_path_conservative"] = true
	}
}

func (a *scheduleAnalyzer) applyScheduleAssignment(visit scheduleFunctionVisit, assignment *ast.AssignStmt) {
	for i, lhs := range assignment.Lhs {
		id, ok := lhs.(*ast.Ident)
		if !ok || id.Name == "_" || i >= len(assignment.Rhs) {
			continue
		}
		rhs := assignment.Rhs[i]
		if value, known := scheduleNumber(rhs, visit.values); known {
			visit.values[id.Name] = value
		} else {
			delete(visit.values, id.Name)
		}
		if scheduleUsesName(rhs, visit.countNames) {
			visit.countNames[id.Name] = true
		} else {
			delete(visit.countNames, id.Name)
		}
	}
}

func (a *scheduleAnalyzer) applyScheduleDeclaration(visit scheduleFunctionVisit, declaration *ast.DeclStmt) {
	gen, ok := declaration.Decl.(*ast.GenDecl)
	if !ok {
		return
	}
	for _, spec := range gen.Specs {
		row, ok := spec.(*ast.ValueSpec)
		if !ok {
			continue
		}
		for index, name := range row.Names {
			if index >= len(row.Values) || name.Name == "_" {
				continue
			}
			expression := row.Values[index]
			if value, known := scheduleNumber(expression, visit.values); known {
				visit.values[name.Name] = value
			} else {
				delete(visit.values, name.Name)
			}
			if scheduleUsesName(expression, visit.countNames) {
				visit.countNames[name.Name] = true
			} else {
				delete(visit.countNames, name.Name)
			}
		}
	}
}

type scheduleTruth struct {
	known bool
	value bool
}

func (a *scheduleAnalyzer) scheduleBool(expression ast.Expr, values map[string]float64) scheduleTruth {
	switch row := expression.(type) {
	case *ast.ParenExpr:
		return a.scheduleBool(row.X, values)
	case *ast.Ident:
		if row.Name == "true" {
			return scheduleTruth{true, true}
		}
		if row.Name == "false" {
			return scheduleTruth{true, false}
		}
	case *ast.UnaryExpr:
		if row.Op == token.NOT {
			inner := a.scheduleBool(row.X, values)
			if inner.known {
				inner.value = !inner.value
			}
			return inner
		}
	case *ast.BinaryExpr:
		left, leftOK := scheduleNumber(row.X, values)
		right, rightOK := scheduleNumber(row.Y, values)
		if !leftOK || !rightOK {
			return scheduleTruth{}
		}
		switch row.Op {
		case token.EQL:
			return scheduleTruth{true, left == right}
		case token.NEQ:
			return scheduleTruth{true, left != right}
		case token.LSS:
			return scheduleTruth{true, left < right}
		case token.LEQ:
			return scheduleTruth{true, left <= right}
		case token.GTR:
			return scheduleTruth{true, left > right}
		case token.GEQ:
			return scheduleTruth{true, left >= right}
		}
	}
	return scheduleTruth{}
}

func scheduleNumber(expression ast.Expr, values map[string]float64) (float64, bool) {
	switch row := expression.(type) {
	case *ast.ParenExpr:
		return scheduleNumber(row.X, values)
	case *ast.Ident:
		value, ok := values[row.Name]
		return value, ok
	case *ast.BasicLit:
		if row.Kind != token.INT && row.Kind != token.FLOAT {
			return 0, false
		}
		value, err := strconv.ParseFloat(row.Value, 64)
		return value, err == nil
	case *ast.UnaryExpr:
		value, ok := scheduleNumber(row.X, values)
		if !ok {
			return 0, false
		}
		if row.Op == token.SUB {
			return -value, true
		}
		if row.Op == token.ADD {
			return value, true
		}
	case *ast.BinaryExpr:
		left, leftOK := scheduleNumber(row.X, values)
		right, rightOK := scheduleNumber(row.Y, values)
		if leftOK && rightOK {
			switch row.Op {
			case token.ADD:
				return left + right, true
			case token.SUB:
				return left - right, true
			case token.MUL:
				return left * right, true
			case token.QUO:
				if right != 0 {
					return left / right, true
				}
			}
		}
	}
	return 0, false
}

func scheduleUsesName(expression ast.Node, names map[string]bool) bool {
	if len(names) == 0 || expression == nil {
		return false
	}
	found := false
	ast.Inspect(expression, func(node ast.Node) bool {
		if id, ok := node.(*ast.Ident); ok && names[id.Name] {
			found = true
			return false
		}
		return !found
	})
	return found
}

func cloneScheduleNumbers(values map[string]float64) map[string]float64 {
	result := make(map[string]float64, len(values))
	for name, value := range values {
		result[name] = value
	}
	return result
}

func cloneScheduleNames(names map[string]bool) map[string]bool {
	result := make(map[string]bool, len(names))
	for name, value := range names {
		result[name] = value
	}
	return result
}

func cloneScheduleVisit(visit scheduleFunctionVisit) scheduleFunctionVisit {
	visit.values = cloneScheduleNumbers(visit.values)
	visit.countNames = cloneScheduleNames(visit.countNames)
	return visit
}
