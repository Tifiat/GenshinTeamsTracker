package engineclient

import (
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestWindowsCurrentDirectoryUnits(t *testing.T) {
	if got := windowsCurrentDirectoryUnits(strings.Repeat("a", 258)); got != 260 {
		t.Fatalf("258 ASCII units with separator and NUL: got %d", got)
	}
	if got := windowsCurrentDirectoryUnits(strings.Repeat("a", 259)); got != 261 {
		t.Fatalf("259 ASCII units with separator and NUL: got %d", got)
	}
	if got := windowsCurrentDirectoryUnits(strings.Repeat("é", 258)); got != 260 {
		t.Fatalf("BMP characters must use one UTF-16 unit each: got %d", got)
	}
	if got := windowsCurrentDirectoryUnits(strings.Repeat("a", 256) + "😀"); got != 260 {
		t.Fatalf("supplementary rune must use two UTF-16 units: got %d", got)
	}
	if got := windowsCurrentDirectoryUnits(strings.Repeat("a", 257) + "😀"); got != 261 {
		t.Fatalf("supplementary rune over boundary: got %d", got)
	}
	if got := windowsCurrentDirectoryUnits(`C:\`); got != 4 {
		t.Fatalf("root with existing trailing separator: got %d", got)
	}
}

func TestChildProcessDirectoryKeepsShortDirectory(t *testing.T) {
	dir := t.TempDir()
	if runtime.GOOS == "windows" && windowsCurrentDirectoryUnits(dir) > windowsCurrentDirectoryLimit {
		t.Skip("test temporary root is already longer than the Windows cwd limit")
	}
	got, err := childProcessDirectory(dir)
	if err != nil {
		t.Fatal(err)
	}
	if got != dir {
		t.Fatalf("short existing directory changed: got %q, want %q", got, dir)
	}
}

func TestChildProcessDirectoryLongWindowsPath(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows CreateProcessW current-directory limit")
	}
	runDirectory := filepath.Join(t.TempDir(), strings.Repeat("a", 80), strings.Repeat("b", 80), strings.Repeat("c", 80))
	if err := os.MkdirAll(runDirectory, 0o700); err != nil {
		t.Fatal(err)
	}
	if got := windowsCurrentDirectoryUnits(runDirectory); got <= windowsCurrentDirectoryLimit {
		t.Fatalf("test run directory has only %d UTF-16 units", got)
	}
	configPath := filepath.Join(runDirectory, "config.txt")
	resultPath := filepath.Join(runDirectory, "result.txt")
	if err := os.WriteFile(configPath, []byte("deep-output-location"), 0o600); err != nil {
		t.Fatal(err)
	}
	child := func(cwd string) *exec.Cmd {
		command := exec.Command(os.Args[0], "-test.run=^TestChildProcessDirectoryHelper$")
		command.Dir = cwd
		command.Env = append(os.Environ(),
			"GTT_ENGINECLIENT_CWD_HELPER=1",
			"GTT_ENGINECLIENT_CWD_INPUT="+configPath,
			"GTT_ENGINECLIENT_CWD_OUTPUT="+resultPath,
		)
		return command
	}
	if output, err := child(runDirectory).CombinedOutput(); err == nil {
		t.Fatalf("raw long cwd unexpectedly launched (output %q)", output)
	}
	if _, err := os.Stat(resultPath); !os.IsNotExist(err) {
		t.Fatalf("raw cwd child wrote output or stat failed: %v", err)
	}
	processDir, err := childProcessDirectory(runDirectory)
	if err != nil {
		t.Fatal(err)
	}
	relative, err := filepath.Rel(processDir, runDirectory)
	if err != nil || relative == "." || relative == ".." || strings.HasPrefix(relative, ".."+string(os.PathSeparator)) {
		t.Fatalf("chosen cwd %q is not a shorter ancestor of %q: %v", processDir, runDirectory, err)
	}
	if got := windowsCurrentDirectoryUnits(processDir); got > windowsCurrentDirectoryLimit {
		t.Fatalf("chosen cwd still exceeds limit: %d", got)
	}
	for candidate := filepath.Dir(runDirectory); candidate != processDir; candidate = filepath.Dir(candidate) {
		if windowsCurrentDirectoryUnits(candidate) <= windowsCurrentDirectoryLimit {
			t.Fatalf("closer fitting ancestor %q was skipped for %q", candidate, processDir)
		}
	}
	if output, err := child(processDir).CombinedOutput(); err != nil {
		t.Fatalf("corrected cwd child failed: %v: %s", err, output)
	}
	result, err := os.ReadFile(resultPath)
	if err != nil {
		t.Fatal(err)
	}
	if string(result) != "deep-output-location" {
		t.Fatalf("deep result content changed: %q", result)
	}
}

func TestChildProcessDirectoryRejectsUnavailableWindowsDirectory(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows-specific ancestor fallback")
	}
	missing := filepath.Join(t.TempDir(), "missing")
	if _, err := childProcessDirectory(missing); err == nil {
		t.Fatal("missing requested directory must not fall back to its parent")
	}
	file := filepath.Join(t.TempDir(), "not-a-directory")
	if err := os.WriteFile(file, []byte("file"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := childProcessDirectory(file); err == nil {
		t.Fatal("requested file must not fall back to its parent")
	}
}

func TestChildProcessDirectoryHelper(t *testing.T) {
	if os.Getenv("GTT_ENGINECLIENT_CWD_HELPER") != "1" {
		return
	}
	content, err := os.ReadFile(os.Getenv("GTT_ENGINECLIENT_CWD_INPUT"))
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(os.Getenv("GTT_ENGINECLIENT_CWD_OUTPUT"), content, 0o600); err != nil {
		t.Fatal(err)
	}
}
