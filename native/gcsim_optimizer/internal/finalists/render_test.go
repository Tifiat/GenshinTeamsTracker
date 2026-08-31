package finalists

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
)

func TestRenderConfigReplacesOnlyPhysicalBuildAndBudget(t *testing.T) {
	request := requestFixture(t)
	for index := range request.Artifacts {
		if request.Artifacts[index].MainStat.Key == "damage_bonus" {
			request.Artifacts[index].MainStat.Key = "pyro_damage_bonus"
		}
	}
	artifactIndex, err := domain.Build(request, nil)
	if err != nil {
		t.Fatal(err)
	}
	request.Context.PreparedConfig.Text = configTemplate(request)
	rendered, err := RenderConfig(request, artifactIndex, artifactIndex.Incumbent, 1000, 8)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Count(rendered.Text, "iteration=1000") != 1 || strings.Count(rendered.Text, "workers=8") != 1 {
		t.Fatalf("simulation options were not frozen:\n%s", rendered.Text)
	}
	for _, wearer := range request.Wearers {
		if !strings.Contains(rendered.Text, wearer.WearerKey+` add set="`+wearer.SelectedSetUID+`" count=5;`) {
			t.Fatalf("missing exact set count for %s", wearer.WearerKey)
		}
		if strings.Count(rendered.Text, wearer.WearerKey+" add stats ") != 1 {
			t.Fatalf("expected one rendered stat row for %s", wearer.WearerKey)
		}
	}
	if !strings.Contains(rendered.Text, "# rotation sentinel\n") || !strings.HasSuffix(rendered.Text, "active actor_a;\n") {
		t.Fatal("rotation content changed")
	}
	second, err := RenderConfig(request, artifactIndex, artifactIndex.Incumbent, 1000, 8)
	if err != nil || second != rendered {
		t.Fatalf("render is not deterministic: %v", err)
	}
}

func TestRenderConfigRejectsFormulaOnlyGenericStat(t *testing.T) {
	request := requestFixture(t)
	artifactIndex, err := domain.Build(request, nil)
	if err != nil {
		t.Fatal(err)
	}
	request.Context.PreparedConfig.Text = configTemplate(request)
	_, err = RenderConfig(request, artifactIndex, artifactIndex.Incumbent, 1000, 8)
	if err == nil || !strings.Contains(err.Error(), "unsupported artifact stat keys: damage_bonus") {
		t.Fatalf("generic stat must fail closed, got %v", err)
	}
}

func configTemplate(request contracts.OptimizerRequest) string {
	var builder strings.Builder
	for _, wearer := range request.Wearers {
		builder.WriteString(wearer.WearerKey + " char lvl=90/90;\n")
		builder.WriteString(wearer.WearerKey + ` add set="` + wearer.SelectedSetUID + `" count=4;` + "\n")
		builder.WriteString(wearer.WearerKey + " add stats hp=1;\n")
	}
	builder.WriteString("# rotation sentinel\noptions swap_delay=12 iteration=7 ignore_burst_energy=true;\nactive actor_a;\n")
	return builder.String()
}

func requestFixture(t *testing.T) contracts.OptimizerRequest {
	t.Helper()
	_, filename, _, _ := runtime.Caller(0)
	path := filepath.Join(filepath.Dir(filename), "..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1", "request_v1.json")
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	request, err := contracts.DecodeRequest(payload)
	if err != nil {
		t.Fatal(err)
	}
	return request
}
