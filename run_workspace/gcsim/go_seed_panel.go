// Command go_seed_panel prints the sorted Int63 panel used by gcsim's
// optstats.RunWithConfigCustomStats.  It is intentionally tiny: the RNG
// implementation remains the Go standard library used by the pinned engine.
package main

import (
	"encoding/json"
	"fmt"
	"math/rand"
	"os"
	"sort"
	"strconv"
)

func main() {
	if len(os.Args) != 3 {
		panic("usage: go_seed_panel MASTER_SEED ITERATIONS")
	}
	seed, err := strconv.ParseInt(os.Args[1], 10, 64)
	if err != nil || seed <= 0 {
		panic("invalid master seed")
	}
	n, err := strconv.Atoi(os.Args[2])
	if err != nil || n <= 0 {
		panic("invalid iteration count")
	}
	source := rand.NewSource(seed)
	values := make([]int64, n)
	for i := range values {
		values[i] = source.Int63()
	}
	sort.Slice(values, func(i, j int) bool { return values[i] < values[j] })
	encoded, err := json.Marshal(values)
	if err != nil {
		panic(err)
	}
	fmt.Println(string(encoded))
}
