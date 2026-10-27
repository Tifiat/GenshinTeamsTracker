//go:build windows

package engineclient

import "syscall"

func r3ProcessCPU() (uint64, bool) {
	handle, err := syscall.GetCurrentProcess()
	if err != nil {
		return 0, false
	}
	var created, exited, kernel, user syscall.Filetime
	if err = syscall.GetProcessTimes(handle, &created, &exited, &kernel, &user); err != nil {
		return 0, false
	}
	ticks := func(t syscall.Filetime) uint64 { return uint64(t.HighDateTime)<<32 | uint64(t.LowDateTime) }
	return (ticks(kernel) + ticks(user)) * 100, true
}
