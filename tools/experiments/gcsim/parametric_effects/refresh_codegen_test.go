package gttsourcegen

// Temporary managed-job adapter for the selected-source response gate. It
// regenerates observations, not gameplay sources or installed engine state.
// Consolidate into the normal producer build when this candidate is installed.
import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestNeutralSelectedSourceOverlay(t *testing.T) {
	job := os.Getenv("GTT_NEUTRAL_CAPTURE_DIR")
	if job == "" { t.Skip("managed capture gate only") }
	if job != os.Getenv("GTT_SCRATCH_DIR") { t.Fatal("unowned output scope") }
	root, err := filepath.Abs(filepath.Join("..", ".."))
	if err != nil { t.Fatal(err) }
	input, err := os.ReadFile(filepath.Join(root, "build", "gtt-source-manifest-input.json"))
	if err != nil { t.Fatal(err) }
	var binding BindingInput
	if err = json.Unmarshal(input, &binding); err != nil { t.Fatal(err) }
	manifest, err := Generate(Options{ModuleRoot: root, Binding: binding})
	if err != nil { t.Fatal(err) }
	installed, err := os.ReadFile(filepath.Join(root, "build", "gtt-source-manifest-body.json"))
	if err != nil { t.Fatal(err) }
	body, err := RenderManifestBody(manifest)
	if err != nil { t.Fatal(err) }
	var installedObject, newObject any
	if err = json.Unmarshal(installed, &installedObject); err != nil { t.Fatal(err) }
	if err = json.Unmarshal(body, &newObject); err != nil { t.Fatal(err) }
	oldCanonical, _ := CanonicalJSON(installedObject)
	newCanonical, _ := CanonicalJSON(newObject)
	if !bytes.Equal(oldCanonical, newCanonical) {
		oldFields, newFields := installedObject.(map[string]any), newObject.(map[string]any)
		if len(oldFields) != len(newFields) { t.Fatal("manifest shape changed") }
		for key, value := range oldFields {
			a, _ := CanonicalJSON(value)
			b, _ := CanonicalJSON(newFields[key])
			if !bytes.Equal(a,b) {
				// Installed directories contain post-build receipts/binaries.
				// The pre-build whole-directory hash consequently differs; it
				// is NOT rewritten in this source-only overlay. Every source
				// entry/template and the immutable input binding must match.
				if key != "patched_source_tree_sha256" { t.Fatalf("source identity changed: %s", key) }
				t.Logf("installed whole-directory hash differs from pre-build hash; source entries/binding must match")
			}
		}
	}
	generated, err := BuildOverlay(OverlayOptions{ModuleRoot: root, OverlayDir: filepath.Join(job, "selected-generated")}, manifest)
	if err != nil { t.Fatal(err) }
	index := filepath.Join(job, "query-overlay.json")
	data, err := os.ReadFile(index)
	if err != nil { t.Fatal(err) }
	var overlay goOverlay
	if err = json.Unmarshal(data, &overlay); err != nil { t.Fatal(err) }
	changed := []string{}
	for _, file := range generated.Files {
		// The helper must not overwrite the separately patched central seams.
		if !strings.HasPrefix(file.RelativeFile, "internal/") { continue }
		oldPath := overlay.Replace[file.OriginalPath]
		if oldPath == "" { oldPath = file.OriginalPath }
		old, err := os.ReadFile(oldPath)
		if err != nil { t.Fatal(err) }
		if bytes.Equal(bytes.ReplaceAll(old, []byte("\r\n"), []byte("\n")), bytes.ReplaceAll(file.Contents, []byte("\r\n"), []byte("\n"))) { continue }
		// Template Snapshot has its own observer patch; never silently replace it.
		if strings.HasPrefix(file.RelativeFile, "internal/template/") { t.Fatalf("unexpected central rewrite: %s", file.RelativeFile) }
		if err = os.MkdirAll(filepath.Dir(file.ReplacementPath), 0700); err != nil { t.Fatal(err) }
		if err = os.WriteFile(file.ReplacementPath, file.Contents, 0600); err != nil { t.Fatal(err) }
		overlay.Replace[file.OriginalPath] = file.ReplacementPath
		changed = append(changed, file.RelativeFile)
	}
	data, err = json.Marshal(overlay)
	if err != nil { t.Fatal(err) }
	if err = os.WriteFile(index, data, 0600); err != nil { t.Fatal(err) }
	t.Logf("same source entries/binding; refreshed observation files=%v", changed)
}
