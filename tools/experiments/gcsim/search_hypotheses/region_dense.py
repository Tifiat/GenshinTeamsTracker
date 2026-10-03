"""Research-only dense bookkeeping for the immutable-region export."""


def apply_dense(root, replace):
    path = "internal/formula/hypothesis_region_binding.go"
    replace(root, path, "nodeLimit   int", "nodeLimit   int\n\tliveStamp, exportedStamp, exportMap []uint32\n\tgeneration uint32")
    replace(root, path, "live := map[uint32]bool{root: true}", """size := len(r.arena.program.nodes)
    grow := func(buffer []uint32) []uint32 {
        if cap(buffer) < size {
            next := make([]uint32, size, size+1024)
            copy(next, buffer)
            return next
        }
        return buffer[:size]
    }
    r.liveStamp, r.exportedStamp, r.exportMap = grow(r.liveStamp), grow(r.exportedStamp), grow(r.exportMap)
    r.generation++
    if r.generation == 0 {
        clear(r.liveStamp); clear(r.exportedStamp)
        r.generation = 1
    }
    r.liveStamp[root] = r.generation
    liveCount := 1""")
    replace(root, path, "if !live[in] {\n\t\t\t\tlive[in] = true", "if r.liveStamp[in] != r.generation {\n\t\t\t\tr.liveStamp[in] = r.generation\n\t\t\t\tliveCount++")
    # These exact repetitions all refer to the same live-node count.
    for before, after in [
        ("nodes: make([]compiledNode, 0, len(live)), values: make([]float64, 0, len(live)),", "nodes: make([]compiledNode, 0, liveCount), values: make([]float64, 0, liveCount),"),
        ("active: make([]uint32, 0, len(live))}", "active: make([]uint32, 0, liveCount)}"),
        ("indices := make(map[uint32]uint32, len(live))", "indices := r.exportMap"),
        ("if !live[id] {", "if r.liveStamp[id] != r.generation {"),
        ("if _, seen := indices[id]; seen {", "if r.exportedStamp[id] == r.generation {"),
        ("mapped, ok := indices[input]\n\t\t\t\tif !ok {", "mapped := indices[input]\n\t\t\t\tif r.exportedStamp[input] != r.generation {"),
        ("indices[id] = mapped", "indices[id] = mapped\n\t\tr.exportedStamp[id] = r.generation"),
        ("len(program.nodes) != len(live)", "len(program.nodes) != liveCount"),
    ]:
        replace(root, path, before, after)
