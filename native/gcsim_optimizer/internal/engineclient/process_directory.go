package engineclient

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"unicode/utf16"
)

const windowsCurrentDirectoryLimit = 260

// childProcessDirectory keeps the run's absolute input and output paths intact.
// Windows CreateProcessW cannot use a current directory whose path plus the
// automatically appended separator and terminating NUL exceeds MAX_PATH.
func childProcessDirectory(runDirectory string) (string, error) {
	if runtime.GOOS != "windows" {
		return runDirectory, nil
	}
	dir, err := filepath.Abs(runDirectory)
	if err != nil {
		return "", fmt.Errorf("resolve engine child directory %q: %w", runDirectory, err)
	}
	info, err := os.Stat(dir)
	if err != nil {
		return "", fmt.Errorf("engine child directory is unavailable: %w", err)
	}
	if !info.IsDir() {
		return "", fmt.Errorf("engine child directory is not a directory: %q", dir)
	}
	for candidate := dir; ; candidate = filepath.Dir(candidate) {
		if windowsCurrentDirectoryUnits(candidate) <= windowsCurrentDirectoryLimit {
			info, statErr := os.Stat(candidate)
			if statErr == nil && info.IsDir() {
				return candidate, nil
			}
		}
		parent := filepath.Dir(candidate)
		if parent == candidate {
			break
		}
	}
	return "", fmt.Errorf("no existing Windows engine child directory fits %d UTF-16 units for run directory %q", windowsCurrentDirectoryLimit, dir)
}

func windowsCurrentDirectoryUnits(dir string) int {
	units := len(utf16.Encode([]rune(dir))) + 1 // terminating NUL
	if !strings.HasSuffix(dir, `\`) && !strings.HasSuffix(dir, "/") {
		units++ // SetCurrentDirectory appends a separator to non-root paths.
	}
	return units
}
