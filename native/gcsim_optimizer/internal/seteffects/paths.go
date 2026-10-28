package seteffects

// ActivationPath is source reachability, NOT proof the event/guard fires in a
// rotation. Paths retain enclosing registration conditions and nested tasks.
// Missing/cyclic paths stay explicit and never imply a useless set.
type ActivationPath struct {
	Entry  string   `json:"entry"`
	Edges  []Edge   `json:"edges"`
	Guards []string `json:"guards"`
}
type Reachability struct {
	Paths      []ActivationPath `json:"paths"`
	Incomplete bool             `json:"incomplete"`
}

func (d Description) EffectPaths(effect Effect) Reachability {
	out := Reachability{Paths: []ActivationPath{}}
	reverse := map[string][]Edge{}
	entries := map[string]string{}
	for _, f := range d.Functions {
		if f.Name == "NewSet" || f.Name == "Init" {
			entries[f.ID] = f.Name
		}
	}
	for _, e := range d.Edges {
		reverse[e.To] = append(reverse[e.To], e)
	}
	active := map[string]bool{}
	var visit func(string, []Edge, int)
	visit = func(id string, tail []Edge, depth int) {
		if active[id] || depth >= 12 || len(out.Paths) >= 64 {
			out.Incomplete = true
			return
		}
		if entry, ok := entries[id]; ok {
			p := ActivationPath{Entry: entry, Edges: []Edge{}, Guards: []string{}}
			for i := len(tail) - 1; i >= 0; i-- {
				p.Edges = append(p.Edges, tail[i])
				p.Guards = append(p.Guards, tail[i].Guards...)
			}
			p.Guards = append(p.Guards, effect.Guards...)
			out.Paths = append(out.Paths, p)
			return
		}
		parents := reverse[id]
		if len(parents) == 0 {
			out.Incomplete = true
			return
		}
		active[id] = true
		for _, e := range parents {
			visit(e.From, append(append([]Edge{}, tail...), e), depth+1)
		}
		delete(active, id)
	}
	visit(effect.Function, nil, 0)
	return out
}
