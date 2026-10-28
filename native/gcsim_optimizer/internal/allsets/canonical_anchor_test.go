package allsets

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

func TestCanonicalReferenceIgnoresEquippedStatsAndItems(t *testing.T) {
	_, fixtureBase, _, _, _ := coordinatorFixture(t)
	raw, err := os.ReadFile(filepath.Join("..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1", "request_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	req, err := contracts.DecodeRequest(raw)
	if err != nil {
		t.Fatal(err)
	}
	for i := range req.Artifacts {
		if req.Artifacts[i].MainStat.Key == "damage_bonus" {
			req.Artifacts[i].MainStat.Key = "pyro_damage_bonus"
		}
	}
	original := append([]contracts.Artifact(nil), req.Artifacts...)
	maxID := original[len(original)-1].ArtifactID
	ids := map[int64]int64{}
	for _, item := range original {
		maxID++
		ids[item.ArtifactID] = maxID
		item.ArtifactID = maxID
		item.MainStat.Value = "0.17"
		req.Artifacts = append(req.Artifacts, item)
	}
	index, err := domain.Build(req, nil)
	if err != nil {
		t.Fatal(err)
	}
	binding := setcontext.Binding{Engine: req.Engine, CatalogSHA256: strings.Repeat("c", 64), ReferenceStatsSHA256: strings.Repeat("d", 64), Seeds: fixtureBase.Seeds()}
	_, firstIndex, first, err := CanonicalReference(req, index, fixtureBase, binding)
	if err != nil {
		t.Fatal(err)
	}
	for i := range req.Wearers {
		for j := range req.Wearers[i].CurrentArtifacts {
			old := req.Wearers[i].CurrentArtifacts[j].ArtifactID
			req.Wearers[i].CurrentArtifacts[j].ArtifactID = ids[old]
		}
	}
	changedIndex, err := domain.Build(req, nil)
	if err != nil {
		t.Fatal(err)
	}
	changedBase, err := setcontext.New(binding, strings.ReplaceAll(fixtureBase.Config(), "add stats hp=1;", "add stats hp=9999;"))
	if err != nil {
		t.Fatal(err)
	}
	_, secondIndex, second, err := CanonicalReference(req, changedIndex, changedBase, binding)
	if err != nil {
		t.Fatal(err)
	}
	if first.Config() != second.Config() || firstIndex.Incumbent != secondIndex.Incumbent {
		t.Fatal("equipped items/stats leaked into canonical capture/search")
	}
	if !strings.Contains(second.Config(), "# rotation sentinel") {
		t.Fatal("rotation lost")
	}
}
