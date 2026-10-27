//go:build !windows

package engineclient

func r3ProcessCPU() (uint64, bool) { return 0, false }
