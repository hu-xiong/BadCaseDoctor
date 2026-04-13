//go:build !windows

package main

import (
	"io"
	"os"
	"os/exec"

	"github.com/creack/pty"
)

type interactiveShell struct {
	Stdin  io.WriteCloser
	Stdout io.ReadCloser
	tty    *os.File
	cmd    *exec.Cmd
	// 与 Windows 字段对齐；Unix 上始终为 false，pty_sessions 共用读循环。
	pipeStdoutUTF16 bool
}

func (s *interactiveShell) alive() bool {
	if s == nil || s.cmd == nil || s.cmd.Process == nil {
		return false
	}
	return s.cmd.ProcessState == nil
}

func (s *interactiveShell) resize(cols, rows int) error {
	if s == nil || s.tty == nil {
		return nil
	}
	if cols <= 0 {
		cols = 80
	}
	if rows <= 0 {
		rows = 24
	}
	return pty.Setsize(s.tty, &pty.Winsize{Rows: uint16(rows), Cols: uint16(cols)})
}

func (s *interactiveShell) stop() {
	if s == nil {
		return
	}
	if s.tty != nil {
		_ = s.tty.Close()
		s.tty = nil
	}
	if s.cmd != nil && s.cmd.Process != nil {
		_ = s.cmd.Process.Kill()
	}
}

func spawnInteractiveShell(cwd string, cols, rows int) (*interactiveShell, error) {
	if cols <= 0 {
		cols = 80
	}
	if rows <= 0 {
		rows = 24
	}
	cmd := exec.Command("bash", "-l")
	if cwd != "" {
		cmd.Dir = cwd
	}
	cmd.Env = os.Environ()
	ws, err := pty.StartWithSize(cmd, &pty.Winsize{Rows: uint16(rows), Cols: uint16(cols)})
	if err != nil {
		return nil, err
	}
	return &interactiveShell{
		Stdin:  ws,
		Stdout: ws,
		tty:    ws,
		cmd:    cmd,
	}, nil
}
