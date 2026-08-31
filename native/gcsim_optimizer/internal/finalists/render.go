// Package finalists owns the exact boundary between formula finalists and
// ordinary common-context GCSIM verification.
package finalists

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
)

var optionLinePattern = regexp.MustCompile(`(?m)^[ \t]*options[ \t]+([^;]*);[ \t]*\r?$`)

var statOrder = []string{
	"hp", "atk", "def", "hp_percent", "atk_percent", "def_percent", "em",
	"energy_recharge", "crit_rate", "crit_damage", "healing_bonus",
	"pyro_damage_bonus", "hydro_damage_bonus", "electro_damage_bonus",
	"cryo_damage_bonus", "anemo_damage_bonus", "geo_damage_bonus",
	"dendro_damage_bonus", "physical_damage_bonus",
}

var gcsimStatKey = map[string]string{
	"hp": "hp", "atk": "atk", "def": "def",
	"hp_percent": "hp%", "atk_percent": "atk%", "def_percent": "def%",
	"em": "em", "energy_recharge": "er", "crit_rate": "cr",
	"crit_damage": "cd", "healing_bonus": "heal",
	"pyro_damage_bonus": "pyro%", "hydro_damage_bonus": "hydro%",
	"electro_damage_bonus": "electro%", "cryo_damage_bonus": "cryo%",
	"anemo_damage_bonus": "anemo%", "geo_damage_bonus": "geo%",
	"dendro_damage_bonus": "dendro%", "physical_damage_bonus": "phys%",
}

type RenderedConfig struct {
	Text   string
	SHA256 string
}

// RenderConfig replaces only the selected-set counts, artifact stat rows, and
// ordinary simulation budget. Character, weapon, rotation, target, and every
// other line remain byte-for-byte inherited from the bound request context.
func RenderConfig(request contracts.OptimizerRequest, index *domain.Index, assignment domain.Assignment, iterations, workers int) (RenderedConfig, error) {
	if iterations <= 0 || workers <= 0 {
		return RenderedConfig{}, fmt.Errorf("iterations and workers must be positive")
	}
	if index == nil {
		return RenderedConfig{}, fmt.Errorf("artifact index is nil")
	}
	stats, err := index.AssignmentStats(assignment)
	if err != nil {
		return RenderedConfig{}, err
	}
	setCounts, err := index.SelectedSetCounts(assignment)
	if err != nil {
		return RenderedConfig{}, err
	}
	text := request.Context.PreparedConfig.Text
	for wearerIndex, wearer := range request.Wearers {
		var replacements int
		text, replacements, err = replaceActorLine(
			text,
			wearer.WearerKey,
			"set",
			fmt.Sprintf(`%s add set=%q count=%d;`, wearer.WearerKey, wearer.SelectedSetUID, setCounts[wearerIndex]),
		)
		if err != nil || replacements != 1 {
			if err == nil {
				err = fmt.Errorf("expected exactly one set row, found %d", replacements)
			}
			return RenderedConfig{}, fmt.Errorf("render %s set: %w", wearer.WearerKey, err)
		}
		statText, err := formatStats(stats[wearerIndex])
		if err != nil {
			return RenderedConfig{}, fmt.Errorf("render %s stats: %w", wearer.WearerKey, err)
		}
		text, replacements, err = replaceActorLine(
			text,
			wearer.WearerKey,
			"stats",
			fmt.Sprintf("%s add stats %s;", wearer.WearerKey, statText),
		)
		if err != nil || replacements != 1 {
			if err == nil {
				err = fmt.Errorf("expected exactly one stats row, found %d", replacements)
			}
			return RenderedConfig{}, fmt.Errorf("render %s stats: %w", wearer.WearerKey, err)
		}
	}
	text, err = setSimulationOptions(text, iterations, workers)
	if err != nil {
		return RenderedConfig{}, err
	}
	digest := sha256.Sum256([]byte(text))
	return RenderedConfig{Text: text, SHA256: hex.EncodeToString(digest[:])}, nil
}

func replaceActorLine(text, actor, kind, replacement string) (string, int, error) {
	pattern, err := regexp.Compile(`(?m)^[ \t]*` + regexp.QuoteMeta(actor) + `[ \t]+add[ \t]+` + regexp.QuoteMeta(kind) + `\b[^\r\n]*;[ \t]*\r?$`)
	if err != nil {
		return "", 0, err
	}
	count := len(pattern.FindAllStringIndex(text, -1))
	return pattern.ReplaceAllString(text, replacement), count, nil
}

func formatStats(stats map[string]float64) (string, error) {
	unknown := make([]string, 0)
	for key := range stats {
		if _, ok := gcsimStatKey[key]; !ok {
			unknown = append(unknown, key)
		}
	}
	if len(unknown) > 0 {
		sort.Strings(unknown)
		return "", fmt.Errorf("unsupported artifact stat keys: %s", strings.Join(unknown, ", "))
	}
	parts := make([]string, 0, len(stats))
	for _, key := range statOrder {
		value, ok := stats[key]
		if !ok || value == 0 {
			continue
		}
		parts = append(parts, gcsimStatKey[key]+"="+formatNumber(value))
	}
	if len(parts) == 0 {
		return "", fmt.Errorf("artifact stat row is empty")
	}
	return strings.Join(parts, " "), nil
}

func formatNumber(value float64) string {
	return strconv.FormatFloat(value, 'f', 6, 64)
}

func setSimulationOptions(text string, iterations, workers int) (string, error) {
	matches := optionLinePattern.FindAllStringSubmatchIndex(text, -1)
	if len(matches) != 1 {
		return "", fmt.Errorf("expected exactly one options row, found %d", len(matches))
	}
	body := text[matches[0][2]:matches[0][3]]
	tokens := strings.Fields(body)
	filtered := make([]string, 0, len(tokens)+2)
	for _, token := range tokens {
		if strings.HasPrefix(token, "iteration=") || strings.HasPrefix(token, "workers=") {
			continue
		}
		filtered = append(filtered, token)
	}
	filtered = append(filtered, "iteration="+strconv.Itoa(iterations), "workers="+strconv.Itoa(workers))
	replacement := "options " + strings.Join(filtered, " ") + ";"
	return optionLinePattern.ReplaceAllString(text, replacement), nil
}
