//go:build windows

package engineclient

import (
	"os/exec"
	"syscall"
)

func hideCaptureWindow(command *exec.Cmd) {
	command.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
}
