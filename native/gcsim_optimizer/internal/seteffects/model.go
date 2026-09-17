// Package seteffects discovers source-backed effect recipes without executing
// gameplay or granting setcontext.StaticProof certificates. This bounded AST
// layer is the first stage of the approved All Sets effect-informed guide.
// Unknown calls/branches remain explicit: discovery is not activation evidence,
// a damage prediction or permission to reuse another package's captured graph.
package seteffects

type Location struct {
	File string `json:"file"`
	Line int    `json:"line"`
}
type Expression struct {
	Kind   string       `json:"kind"`
	Text   string       `json:"text"`
	Symbol string       `json:"symbol,omitempty"`
	Inputs []Expression `json:"inputs,omitempty"`
}
type Write struct {
	Target   Expression `json:"target"`
	Operator string     `json:"operator"`
	Value    Expression `json:"value"`
	Function string     `json:"function"`
	Guards   []string   `json:"guards"`
	At       Location   `json:"at"`
}
type Return struct {
	Values []Expression `json:"values"`
	Guards []string     `json:"guards"`
	At     Location     `json:"at"`
}
type Function struct {
	ID      string   `json:"id"`
	Name    string   `json:"name"`
	Returns []Return `json:"returns"`
	At      Location `json:"at"`
}
type Edge struct {
	From    string     `json:"from"`
	To      string     `json:"to"`
	Kind    string     `json:"kind"`
	Trigger Expression `json:"trigger"`
	Guards  []string   `json:"guards"`
	At      Location   `json:"at"`
}
type Field struct {
	Name  string     `json:"name"`
	Value Expression `json:"value"`
}
type Effect struct {
	ID             string     `json:"id"`
	Kind           string     `json:"kind"`
	Operation      string     `json:"operation"`
	Receiver       Expression `json:"receiver"`
	Fields         []Field    `json:"fields"`
	AmountFunction string     `json:"amount_function,omitempty"`
	Function       string     `json:"function"`
	Guards         []string   `json:"guards"`
	At             Location   `json:"at"`
}
type Boundary struct {
	Reason     string   `json:"reason"`
	Function   string   `json:"function"`
	Expression string   `json:"expression"`
	At         Location `json:"at"`
}
type Description struct {
	SchemaVersion        int                   `json:"schema_version"`
	SourceSHA256         string                `json:"source_sha256"`
	Package              string                `json:"package"`
	Functions            []Function            `json:"functions"`
	Writes               []Write               `json:"writes"`
	Edges                []Edge                `json:"edges"`
	Effects              []Effect              `json:"effects"`
	Boundaries           []Boundary            `json:"boundaries"`
	Conditions           map[string]Expression `json:"conditions"`
	ReplacementCertified bool                  `json:"replacement_certified"`
}
