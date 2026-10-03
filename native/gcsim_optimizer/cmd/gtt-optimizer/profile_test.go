package main

import "testing"

func TestOptimizerCPUProfileIsExplicitAndManaged(t *testing.T) {
	t.Setenv("GTT_OPTIMIZER_PROFILE", "")
	t.Setenv("GTT_SCRATCH_DIR", "")
	stop, err := startManagedProfile([]string{"optimize-all-sets"})
	if err != nil {
		t.Fatal(err)
	}
	stop()
	t.Setenv("GTT_OPTIMIZER_PROFILE", "1")
	if _, err := startManagedProfile([]string{"optimize-all-sets"}); err == nil {
		t.Fatal("unmanaged profile accepted")
	}
	t.Setenv("GTT_SCRATCH_DIR", t.TempDir())
	if _, err := startManagedProfile([]string{"optimize-all-sets"}); err == nil {
		t.Fatal("arbitrary temporary folder accepted")
	}
	stop, err = startManagedProfile([]string{"validate-request"})
	if err != nil {
		t.Fatal(err)
	}
	stop()
}
