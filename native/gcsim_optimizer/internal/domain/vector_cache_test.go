package domain

import (
	"fmt"
	"reflect"
	"testing"
)

func TestInventoryViewsShareBoundedExactVectors(t *testing.T) {
	index, err := Build(requestFixture(t), []string{"actor_a.hp"})
	if err != nil {
		t.Fatal(err)
	}
	coordinates := []string{"actor_a.hp"}
	vectors, ref, err := index.ArtifactVectors(0, coordinates)
	if err != nil {
		t.Fatal(err)
	}
	uncached := *index
	uncached.vectorCache = nil
	wantVectors, wantRef, err := uncached.ArtifactVectors(0, coordinates)
	if err != nil || !reflect.DeepEqual(vectors, wantVectors) || !reflect.DeepEqual(ref, wantRef) {
		t.Fatalf("vector result changed: %v", err)
	}
	var packages [wearerCount]Package
	for i, wearer := range index.Wearers {
		packages[i] = Package{Sets: wearer.SelectedSets}
	}
	view, err := index.ForPackages(packages, index.Incumbent, coordinates)
	if err != nil {
		t.Fatal(err)
	}
	shared, nextRef, err := view.ArtifactVectors(0, coordinates)
	if err != nil || view.vectorCache != index.vectorCache || !reflect.DeepEqual(ref, nextRef) {
		t.Fatalf("view cache or reference changed: %v", err)
	}
	for id, vector := range vectors {
		if len(vector) > 0 && &vector[0] != &shared[id][0] {
			t.Fatal("view rebuilt vector", id)
		}
		break
	}
	ref[0]++
	_, intactRef, err := view.ArtifactVectors(0, coordinates)
	if err != nil || !reflect.DeepEqual(intactRef, wantRef) {
		t.Fatal("caller mutated cached reference")
	}
	if _, _, err := view.ArtifactVectors(0, []string{"actor_b.hp"}); err == nil {
		t.Fatal("foreign coordinate accepted")
	}
	for i := 0; i < artifactVectorCacheEntries+3; i++ {
		if _, _, err := view.ArtifactVectors(0, []string{fmt.Sprintf("actor_a.test%d", i)}); err != nil {
			t.Fatal(err)
		}
	}
	cache := index.vectorCache
	if len(cache.entries) > artifactVectorCacheEntries || cache.words > artifactVectorCacheWords || len(cache.order) != len(cache.entries) {
		t.Fatalf("cache exceeded budget: entries=%d words=%d", len(cache.entries), cache.words)
	}
}
