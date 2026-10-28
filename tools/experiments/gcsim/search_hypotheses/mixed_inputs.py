"""Isolated sparse mixed-effect transport; no product imports or installation."""


def apply_mixed(root, replace):
    path = "internal/seteffects/neutral_expressions.go"
    replace(root, path, "Constants   []float64", "SparseEffects map[int]*formula.InputExpression // private compact consumer path\n\tConstants   []float64")
    path = "internal/seteffects/neutral_composition.go"
    replace(root, path, "b.compilePackages(choices, false)", "b.compilePackages(choices, false, false)")
    replace(root, path, "b.compilePackages(choices, true)", "b.compilePackages(choices, true, false)")
    replace(root, path, "func (b *NeutralBinding) compilePackages(choices []RuleChoice, compact bool) NeutralExpressions {", """// Only the owned optimizer consumer opts into dense constants plus sparse
// expressions. Public map/compact APIs retain their existing output shape.
func (b *NeutralBinding) CompilePackagesSparse(choices []RuleChoice) NeutralExpressions {
    return b.compilePackages(choices, true, true)
}

func (b *NeutralBinding) compilePackages(choices []RuleChoice, compact, sparse bool) NeutralExpressions {""")
    replace(root, path, "if compact && len(combined.expressions) == 0 {", """if sparse && len(combined.expressions) != 0 {
        out.Constants = make([]float64, len(b.keys))
        out.SparseEffects = make(map[int]*formula.InputExpression, len(combined.expressions))
    } else if compact && len(combined.expressions) == 0 {""")
    replace(root, path, "out.Effects[b.keys[port.dimension]] = expression", """if out.SparseEffects != nil {
                    out.SparseEffects[port.dimension] = expression
                } else { out.Effects[b.keys[port.dimension]] = expression }""")
    # Sparse indices are capture order; the binder explicitly translates them
    # to formula order using the same verified mapping as the scalar route.
    path = "internal/setcontext/neutral.go"
    replace(root, path, "m.binding.CompilePackagesCompact(choices)", "m.binding.CompilePackagesSparse(choices)")
    replace(root, path, "if effects.Constants != nil {", """if effects.SparseEffects != nil {
        m.stats.ExpressionMapBindings++
        program, err = m.bindMixed(effects.Constants, effects.SparseEffects)
    } else if effects.Constants != nil {""")
    path = "internal/setcontext/neutral_program_cache.go"
    # Extract existing bijection builder without altering the original path.
    replace(root, path, "\t// Binding order is capture order; formula order is deliberately independent.", """    if err := m.prepareEffectDimensions(); err != nil { return nil, err }
    return m.bindConstantDimensions(values)
}

func (m *NeutralModel) prepareEffectDimensions() error {
    m.prepareEffectKeys()
    // Binding order is capture order; formula order is deliberately independent.""")
    for message in ["neutral effect port identity differs from formula", "duplicate neutral effect port"]:
        replace(root, path, f'return nil, fmt.Errorf("{message}")', f'return fmt.Errorf("{message}")')
    for message in ["missing neutral effect port: %s", "missing damage effect port: %s"]:
        replace(root, path, f'return nil, fmt.Errorf("{message}", key)', f'return fmt.Errorf("{message}", key)')
    replace(root, path, "\t// Validate ALL ports, including latent roots, before damage projection.", """    return nil
}

func (m *NeutralModel) bindConstantDimensions(values []float64) (*formula.ParametricProgram, error) {
    // Validate ALL ports, including latent roots, before damage projection.""")
    path = "internal/formula/effect_expression.go"
    replace(root, path, "func (p *ParametricProgram) bindEffectExpressionsGeneral(effects map[string]*InputExpression) (*ParametricProgram, error) {", """func (p *ParametricProgram) bindEffectExpressionsGeneral(effects map[string]*InputExpression) (*ParametricProgram, error) {
    return p.bindEffectExpressionsInputs(effects, nil, nil)
}

func (p *ParametricProgram) bindEffectExpressionsInputs(effects map[string]*InputExpression, constants []float64, sparse map[int]*InputExpression) (*ParametricProgram, error) {""")
    replace(root, path, "\tcoords := p.Coordinates()", """    effectIndex := map[string]int{}
    if constants != nil { for i, key := range p.effects { effectIndex[key] = i } }
    coords := p.Coordinates()""")
    replace(root, path, "\t\tx, ok := effects[key]\n\t\tif !ok {", """        x, ok := effects[key]
        if constants != nil {
            dimension, exists := effectIndex[key]
            if !exists { return 0, fmt.Errorf("unknown mixed effect input: %s", key) }
            x, ok = sparse[dimension]
            if !ok {
                // Keep the original literal-expression traversal budget even
                // though the allocated expression wrapper is now unnecessary.
                visits++
                if depth+1 > 4096 || visits > 2_000_000 { return 0, fmt.Errorf("effect expression budget") }
                id, err := b.add(compiledNode{op: opConstant, coordinate: -1, value: constants[dimension]})
                if err == nil { effectMemo[key] = id }
                return id, err
            }
        }
        if !ok {""")
