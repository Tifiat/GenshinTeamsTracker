package main

// Explicit managed diagnostics only. Ordinary button runs never create profiles.
import (
	"fmt"
	"os"
	"path/filepath"
	"runtime/pprof"
	"strings"
)

func startManagedProfile(arguments []string) (func(), error) {
	if len(arguments) == 0 || arguments[0] != "optimize-all-sets" || os.Getenv("GTT_OPTIMIZER_PROFILE") != "1" {
		return func() {}, nil
	}
	root := os.Getenv("GTT_SCRATCH_DIR")
	if !filepath.IsAbs(root) || !strings.HasPrefix(filepath.Base(root), "job-") || filepath.Base(filepath.Dir(root)) != "managed-optimizer" {
		return nil, fmt.Errorf("optimizer profiling requires a managed absolute scratch root")
	}
	resolved, err := filepath.EvalSymlinks(root)
	if err != nil || !strings.EqualFold(filepath.Clean(resolved), filepath.Clean(root)) {
		return nil, fmt.Errorf("optimizer profiling refuses linked scratch")
	}
	f, err := os.OpenFile(filepath.Join(root, "optimizer-cpu.pprof"), os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return nil, err
	}
	if err := pprof.StartCPUProfile(f); err != nil {
		f.Close()
		return nil, err
	}
	return func() { pprof.StopCPUProfile(); f.Close() }, nil
}
