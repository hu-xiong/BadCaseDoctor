//go:build windows

package main

import (
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"strings"

	"golang.org/x/sys/windows"

	"badcasedoctor/go-local-proxy/internal/conpty"
)

const _exitStillActive = 259

// interactiveShell：优先 Windows ConPTY + PowerShell（与真终端一致）；不可用或启动失败时回退管道（体验降级）。
type interactiveShell struct {
	Stdin  io.WriteCloser
	Stdout io.ReadCloser
	cmd    *exec.Cmd
	cpty   *conpty.ConPty
	// 仅管道回退：powershell 对管道 stdout 常为 UTF-16 LE。ConPTY 侧为 UTF-8，若仍走 UTF-16 启发式会误判吞光输出（Web xterm 无提示符）。
	pipeStdoutUTF16 bool
}

type conptyStdin struct{ c *conpty.ConPty }

func (w *conptyStdin) Write(p []byte) (int, error) {
	if w.c == nil {
		return 0, io.ErrClosedPipe
	}
	return w.c.Write(p)
}

func (w *conptyStdin) Close() error { return nil }

type conptyStdout struct{ c *conpty.ConPty }

func (r *conptyStdout) Read(p []byte) (int, error) {
	if r.c == nil {
		return 0, io.EOF
	}
	return r.c.Read(p)
}

func (r *conptyStdout) Close() error { return nil }

func processStillAlive(pid int) bool {
	if pid <= 0 {
		return false
	}
	h, err := windows.OpenProcess(windows.PROCESS_QUERY_LIMITED_INFORMATION, false, uint32(pid))
	if err != nil {
		return false
	}
	defer windows.CloseHandle(h)
	var code uint32
	if err := windows.GetExitCodeProcess(h, &code); err != nil {
		return false
	}
	return code == _exitStillActive
}

func (s *interactiveShell) resize(cols, rows int) error {
	if s == nil || s.cpty == nil {
		return nil
	}
	if cols <= 0 {
		cols = 80
	}
	if rows <= 0 {
		rows = 24
	}
	return s.cpty.Resize(cols, rows)
}

func (s *interactiveShell) alive() bool {
	if s == nil {
		return false
	}
	if s.cpty != nil {
		return processStillAlive(s.cpty.Pid())
	}
	if s.cmd == nil || s.cmd.Process == nil {
		return false
	}
	return s.cmd.ProcessState == nil
}

func (s *interactiveShell) stop() {
	if s == nil {
		return
	}
	if s.cpty != nil {
		_ = s.cpty.Close()
		s.cpty = nil
		s.Stdin = nil
		s.Stdout = nil
		return
	}
	if s.cmd != nil && s.cmd.Process != nil {
		_ = s.cmd.Process.Kill()
	}
	if s.Stdin != nil {
		_ = s.Stdin.Close()
	}
	if s.Stdout != nil {
		_ = s.Stdout.Close()
	}
	s.Stdin = nil
	s.Stdout = nil
	s.cmd = nil
}

// UTF-16LE：NormalView + PSReadLine Prediction Off + PS7 PlainText；「\r 盖行」由前端 EmbeddedPty 对 lone CR+报错包插 LF 缓解；供 -EncodedCommand。
const windowsPsInitEncodedCommand = "JgAgAHsAIAAkAEUAcgByAG8AcgBWAGkAZQB3ACAAPQAgACcATgBvAHIAbQBhAGwAVgBpAGUAdwAnADsAIAB0AHIAeQAgAHsAIABpAGYAIAAoAEcAZQB0AC0ATQBvAGQAdQBsAGUAIABQAFMAUgBlAGEAZABMAGkAbgBlACAALQBFAHIAcgBvAHIAQQBjAHQAaQBvAG4AIABTAGkAbABlAG4AdABsAHkAQwBvAG4AdABpAG4AdQBlACkAIAB7ACAAUwBlAHQALQBQAFMAUgBlAGEAZABMAGkAbgBlAE8AcAB0AGkAbwBuACAALQBQAHIAZQBkAGkAYwB0AGkAbwBuAFMAbwB1AHIAYwBlACAATgBvAG4AZQAgAC0ARQByAHIAbwByAEEAYwB0AGkAbwBuACAAUwBpAGwAZQBuAHQAbAB5AEMAbwBuAHQAaQBuAHUAZQAgAH0AIAB9ACAAYwBhAHQAYwBoACAAewAgAH0AOwAgAHQAcgB5ACAAewAgAGkAZgAgACgAJABQAFMAUwB0AHkAbABlACkAIAB7ACAAJABQAFMAUwB0AHkAbABlAC4ATwB1AHQAcAB1AHQAUgBlAG4AZABlAHIAaQBuAGcAIAA9ACAAJwBQAGwAYQBpAG4AVABlAHgAdAAnACAAfQAgAH0AIABjAGEAdABjAGgAIAB7ACAAfQAgAH0A"

// buildPowerShellCommandLine 供 CreateProcess 整条命令行；含空格的路径必须加引号。
// EncodedCommand：NormalView、PSReadLine Prediction Off、PS7 PlainText（\r 盖提示符行由前端插 LF 缓解）。
func buildPowerShellCommandLine() string {
	if p, err := exec.LookPath("pwsh.exe"); err == nil && p != "" {
		return fmt.Sprintf(`"%s" -NoLogo -NoProfile -NoExit -EncodedCommand %s`, p, windowsPsInitEncodedCommand)
	}
	p, err := exec.LookPath("powershell.exe")
	if err != nil || p == "" {
		p = `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`
	}
	return fmt.Sprintf(`"%s" -NoLogo -NoProfile -NoExit -EncodedCommand %s`, p, windowsPsInitEncodedCommand)
}

func newConptyInteractive(c *conpty.ConPty) *interactiveShell {
	return &interactiveShell{
		cpty:   c,
		Stdin:  &conptyStdin{c: c},
		Stdout: &conptyStdout{c: c},
	}
}

func spawnInteractiveShellPipe(cwd string) (*interactiveShell, error) {
	exe := "powershell.exe"
	if p, err := exec.LookPath("pwsh.exe"); err == nil && p != "" {
		exe = p
	} else if p2, err2 := exec.LookPath("powershell.exe"); err2 == nil && p2 != "" {
		exe = p2
	}
	cmd := exec.Command(exe, "-NoLogo", "-NoProfile", "-NoExit", "-EncodedCommand", windowsPsInitEncodedCommand)
	if cwd != "" {
		cmd.Dir = cwd
	}
	cmd.Env = os.Environ()
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return nil, err
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	cmd.Stderr = cmd.Stdout
	if err := cmd.Start(); err != nil {
		return nil, err
	}
	return &interactiveShell{Stdin: stdin, Stdout: stdout, cmd: cmd, pipeStdoutUTF16: true}, nil
}

func spawnInteractiveShell(cwd string, cols, rows int) (*interactiveShell, error) {
	if cols <= 0 {
		cols = 80
	}
	if rows <= 0 {
		rows = 24
	}
	cwd = strings.TrimSpace(cwd)

	cmdLine := buildPowerShellCommandLine()

	c, err := conpty.Start(cmdLine,
		conpty.ConPtyDimensions(cols, rows),
		conpty.ConPtyWorkDir(cwd),
		conpty.ConPtyEnv(os.Environ()),
	)
	if err == nil {
		if ptyDebugEnabled() {
			cl := cmdLine
			if len(cl) > 160 {
				cl = cl[:160] + "..."
			}
			log.Printf("[pty-debug] ConPTY ok pid=%d cols=%d rows=%d cwd=%q cmd=%q",
				c.Pid(), cols, rows, cwd, cl)
		}
		return newConptyInteractive(c), nil
	}

	if errors.Is(err, conpty.ErrConPtyUnsupported) {
		log.Printf("[pty] ConPTY API missing (old Windows?), using pipe fallback")
	} else {
		log.Printf("[pty] ConPTY start error: %v — using pipe fallback (no real console)", err)
	}
	sh, err2 := spawnInteractiveShellPipe(cwd)
	if err2 != nil {
		return nil, fmt.Errorf("conpty failed (%w); pipe fallback failed (%v)", err, err2)
	}
	if ptyDebugEnabled() && sh != nil && sh.cmd != nil && sh.cmd.Process != nil {
		log.Printf("[pty-debug] pipe fallback pid=%d cwd=%q", sh.cmd.Process.Pid, cwd)
	}
	return sh, nil
}
