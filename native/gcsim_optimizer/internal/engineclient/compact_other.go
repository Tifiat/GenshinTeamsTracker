//go:build !windows

package engineclient

import "os/exec"

func hideCaptureWindow(command *exec.Cmd) {}
