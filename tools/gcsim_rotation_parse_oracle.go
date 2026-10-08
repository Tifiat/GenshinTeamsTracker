// Read-only parser oracle for the isolated rotation editor. No evaluator/sim.
// Run against the explicitly selected GCSIM source module, with GOPROXY=off.
package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"

	"github.com/genshinsim/gcsim/pkg/gcs/ast"
	"github.com/genshinsim/gcsim/pkg/gcs/parser"
)

type request struct {
	Source string `json:"source"`
}

type response struct {
	Error    string          `json:"error,omitempty"`
	Tree     any             `json:"tree,omitempty"`
	Config   json.RawMessage `json:"config,omitempty"`
	Warnings []string        `json:"warnings,omitempty"`
}

func inspect(source string) (result response) {
	defer func() {
		if recovered := recover(); recovered != nil {
			result = response{Error: fmt.Sprint(recovered)}
		}
	}()
	config, program, err := parser.New(ast.NewFile(), source).Parse()
	if err != nil {
		return response{Error: err.Error()}
	}
	encoded, err := json.Marshal(program)
	if err != nil {
		return response{Error: err.Error()}
	}
	if err = json.Unmarshal(encoded, &result.Tree); err != nil {
		return response{Error: err.Error()}
	}
	stripPositions(result.Tree)
	for _, warning := range config.Errors {
		result.Warnings = append(result.Warnings, warning.Error())
	}
	result.Config, err = json.Marshal(config)
	if err != nil {
		result.Error = err.Error()
	}
	return result
}

func stripPositions(value any) {
	switch node := value.(type) {
	case map[string]any:
		delete(node, "Pos")
		delete(node, "Line")
		for _, child := range node {
			stripPositions(child)
		}
	case []any:
		for _, child := range node {
			stripPositions(child)
		}
	}
}

func main() {
	scanner := bufio.NewScanner(os.Stdin)
	scanner.Buffer(make([]byte, 4096), 3*1024*1024)
	encoder := json.NewEncoder(os.Stdout)
	for scanner.Scan() {
		var input request
		if err := json.Unmarshal(scanner.Bytes(), &input); err != nil {
			encoder.Encode(response{Error: err.Error()})
			continue
		}
		encoder.Encode(inspect(input.Source))
	}
	if err := scanner.Err(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
