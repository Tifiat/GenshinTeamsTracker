package domain

import (
	"fmt"
	"strconv"
	"strings"
	"sync"
)

// This cache belongs to one Build result and all its ForPackages views. It
// retains at most 16 coordinate shapes and one million float words; oversized
// shapes are computed normally. Cached vectors are read-only to search callers.
const artifactVectorCacheEntries = 16
const artifactVectorCacheWords = 1_000_000

type artifactVectorKey struct {
	actor       int
	coordinates string
}
type artifactVectorEntry struct {
	vectors map[int64][]float64
	words   int
}
type artifactVectorCache struct {
	mu      sync.Mutex
	entries map[artifactVectorKey]artifactVectorEntry
	order   []artifactVectorKey
	words   int
}

func artifactVectorCoordinateKey(coordinates []string) string {
	var b strings.Builder
	for _, value := range coordinates {
		b.WriteString(strconv.Itoa(len(value)))
		b.WriteByte(':')
		b.WriteString(value)
	}
	return b.String()
}

// ArtifactVectors exposes complete JOINT real-item vectors in the requested
// coordinate order. Missing formula coordinates are zero, not an item filter.
func (index *Index) ArtifactVectors(actor int, coordinates []string) (map[int64][]float64, []float64, error) {
	if index == nil || actor < 0 || actor >= wearerCount {
		return nil, nil, fmt.Errorf("invalid vector wearer")
	}
	prefix := index.Wearers[actor].WearerKey + "."
	dims := map[string]int{}
	ref := make([]float64, len(coordinates))
	for i, key := range coordinates {
		if len(key) <= len(prefix) || key[:len(prefix)] != prefix {
			return nil, nil, fmt.Errorf("foreign artifact coordinate")
		}
		dims[key[len(prefix):]] = i
		ref[i] = index.Wearers[actor].incumbentStats[key[len(prefix):]]
	}
	cache := index.vectorCache
	key := artifactVectorKey{actor: actor, coordinates: artifactVectorCoordinateKey(coordinates)}
	if cache != nil {
		cache.mu.Lock()
		entry, ok := cache.entries[key]
		cache.mu.Unlock()
		if ok {
			return entry.vectors, ref, nil
		}
	}
	vectors := make(map[int64][]float64, len(index.Artifacts))
	for _, item := range index.Artifacts {
		v := make([]float64, len(coordinates))
		for _, stat := range item.stats {
			if d, ok := dims[stat.key]; ok {
				v[d] += stat.value
			}
		}
		vectors[item.ArtifactID] = v
	}
	// Exact actor/ordered-coordinate identity is required. A package view
	// changes constraints and seed, but neither raw inventory nor reference.
	words := len(index.Artifacts) * len(coordinates)
	if cache != nil && words <= artifactVectorCacheWords {
		cache.mu.Lock()
		if previous, ok := cache.entries[key]; ok {
			vectors = previous.vectors
		} else {
			for len(cache.order) >= artifactVectorCacheEntries || cache.words+words > artifactVectorCacheWords {
				old := cache.order[0]
				cache.order = cache.order[1:]
				cache.words -= cache.entries[old].words
				delete(cache.entries, old)
			}
			cache.entries[key] = artifactVectorEntry{vectors: vectors, words: words}
			cache.order = append(cache.order, key)
			cache.words += words
		}
		cache.mu.Unlock()
	}
	return vectors, ref, nil
}
