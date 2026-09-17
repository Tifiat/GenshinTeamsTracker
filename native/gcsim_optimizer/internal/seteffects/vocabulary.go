package seteffects

import (
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"strconv"
)

// StatVocabulary reads the engine's own enum + StatTypeString pairing, not a
// list of gameplay coefficients. Unknown declarations fail instead of shifting
// indices. This is a source protocol seam and must be audited on engine updates.
func StatVocabulary(source []byte) (map[string]string, error) {
	return enumStringVocabulary(source, "Stat", "StatTypeString")
}

func ElementVocabulary(source []byte) (map[string]string, error) {
	return enumStringVocabulary(source, "Element", "ElementString")
}

func enumStringVocabulary(source []byte, enumType, labelName string) (map[string]string, error) {
	f, err := parser.ParseFile(token.NewFileSet(), "stats.go", source, 0)
	if err != nil {
		return nil, err
	}
	byIndex := map[int]string{}
	var labels []string
	for _, decl := range f.Decls {
		g, ok := decl.(*ast.GenDecl)
		if !ok {
			continue
		}
		if g.Tok == token.CONST {
			statBlock := false
			for i, spec := range g.Specs {
				v, ok := spec.(*ast.ValueSpec)
				if !ok {
					continue
				}
				if i == 0 && len(v.Values) == 1 {
					if ident, ok := v.Values[0].(*ast.Ident); ok && ident.Name == "iota" {
						if typ, ok := v.Type.(*ast.Ident); ok && typ.Name == enumType {
							statBlock = true
						}
					}
				}
				if !statBlock {
					continue
				}
				if len(v.Names) != 1 || (i > 0 && len(v.Values) > 0) {
					return nil, fmt.Errorf("unsupported Stat enum shape")
				}
				byIndex[i] = v.Names[0].Name
			}
		}
		if g.Tok == token.VAR {
			for _, spec := range g.Specs {
				v, ok := spec.(*ast.ValueSpec)
				if !ok {
					continue
				}
				for i, name := range v.Names {
					if name.Name != labelName {
						continue
					}
					if i >= len(v.Values) {
						return nil, fmt.Errorf("missing stat labels")
					}
					a, ok := v.Values[i].(*ast.CompositeLit)
					if !ok {
						return nil, fmt.Errorf("unsupported stat label expression")
					}
					for _, item := range a.Elts {
						literal, ok := item.(*ast.BasicLit)
						if !ok || literal.Kind != token.STRING {
							return nil, fmt.Errorf("unsupported indexed stat label")
						}
						text, e := strconv.Unquote(literal.Value)
						if e != nil {
							return nil, e
						}
						labels = append(labels, text)
					}
				}
			}
		}
	}
	if len(labels) == 0 || len(byIndex) < len(labels) {
		return nil, fmt.Errorf("incomplete stat vocabulary")
	}
	out := map[string]string{}
	for i, label := range labels {
		name, ok := byIndex[i]
		if !ok {
			return nil, fmt.Errorf("stat label index gap")
		}
		out["github.com/genshinsim/gcsim/pkg/core/attributes."+name] = label
	}
	return out, nil
}

// OwnerStatKey maps the existing stat wire vocabulary to raw formula-coordinate
// names. Unrepresented mechanics (all-damage, speed, base-stat changes) stay
// unsupported here; do not invent equivalence to artifact coordinates.
func OwnerStatKey(engineKey string) (string, bool) {
	aliases := map[string]string{"hp": "hp", "atk": "atk", "def": "def", "hp%": "hp_percent", "atk%": "atk_percent", "def%": "def_percent", "em": "em", "er": "energy_recharge", "cr": "crit_rate", "cd": "crit_damage", "heal": "healing_bonus", "pyro%": "pyro_damage_bonus", "hydro%": "hydro_damage_bonus", "cryo%": "cryo_damage_bonus", "electro%": "electro_damage_bonus", "anemo%": "anemo_damage_bonus", "geo%": "geo_damage_bonus", "dendro%": "dendro_damage_bonus", "phys%": "physical_damage_bonus"}
	key, ok := aliases[engineKey]
	return key, ok
}
