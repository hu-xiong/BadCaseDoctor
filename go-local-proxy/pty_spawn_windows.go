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

type conptyStdin struct {
	c *conpty.ConPty
	t *conpty.InputTransformer
}

// CSI sequence buffer for handling partial sequences
type csiBuffer struct {
	data []byte
}

func (cb *csiBuffer) append(b byte) {
	cb.data = append(cb.data, b)
}

func (cb *csiBuffer) reset() {
	cb.data = cb.data[:0]
}

func (cb *csiBuffer) isCSI() bool {
	return len(cb.data) >= 2 && cb.data[0] == 0x1B && cb.data[1] == '['
}

// parseCSIParams parses a CSI sequence and extracts parameters.
// Returns (params, final byte, success)
func parseCSIParams(data []byte) (params []int, final byte, ok bool) {
	if len(data) < 3 || data[0] != 0x1B || data[1] != '[' {
		return nil, 0, false
	}
	data = data[2:] // Skip ESC [

	paramStr := ""
	for i := 0; i < len(data); i++ {
		c := data[i]
		if c >= '0' && c <= '9' || c == ';' {
			paramStr += string(c)
		} else if c >= 0x40 && c <= 0x7E {
			final = c
			ok = true
			break
		}
	}

	if !ok {
		return nil, 0, false
	}

	// Parse parameters separated by semicolons
	parts := strings.Split(paramStr, ";")
	for _, part := range parts {
		if part == "" {
			params = append(params, 0)
		} else {
			var p int
			fmt.Sscanf(part, "%d", &p)
			params = append(params, p)
		}
	}

	return params, final, true
}

// CSI modifiers from xterm (same as conpty_csi.go)
const (
	CSIParamNone = 0
)

// HandleCSIInput handles a complete CSI sequence and sends appropriate INPUT_RECORD.
// Returns the number of INPUT_RECORDs processed.
func (w *conptyStdin) HandleCSIInput(csiData []byte) (int, error) {
	params, final, ok := parseCSIParams(csiData)
	if !ok {
		return 0, nil
	}

	// Extract key parameter and modifier
	keyParam := 0
	modifier := 0
	if len(params) > 0 {
		keyParam = params[0]
	}
	if len(params) > 1 {
		modifier = params[1]
	}

	// Handle ~ format (CSI <num> [;<mod>] ~)
	if final == '~' {
		vk, ok := csiTildeToVK[keyParam]
		if !ok {
			return 0, nil
		}
		ctrlState := CSIParamToModifier(modifier)
		keyEvent := conpty.NewKeyEventRecord(vk, ctrlState, true)
		rec := keyEvent.ToINPUTRecord()

		var records []conpty.INPUT_RECORD
		records = append(records, rec)

		// For special keys like Delete, we send both key down and key up
		// Some applications expect both events
		if vk == conpty.VK_DELETE || vk == conpty.VK_HOME || vk == conpty.VK_END ||
			vk == conpty.VK_INSERT || vk == conpty.VK_PRIOR || vk == conpty.VK_NEXT ||
			vk >= conpty.VK_F1 && vk <= conpty.VK_F12 {
			keyUp := conpty.NewKeyEventRecord(vk, ctrlState, false)
			records = append(records, keyUp.ToINPUTRecord())
		}

		n, err := w.c.WriteConsoleInput(records)
		return int(n), err
	}

	// Handle letter format (CSI <num> [;<mod>] <letter>)
	// Arrow keys: CSI A/B/C/D with optional modifiers
	vk, ok := csiLetterToVK[final]
	if !ok {
		return 0, nil
	}
	ctrlState := CSIParamToModifier(modifier)
	keyEvent := conpty.NewKeyEventRecord(vk, ctrlState, true)
	rec := keyEvent.ToINPUTRecord()

	var records []conpty.INPUT_RECORD
	records = append(records, rec)

	// Send key up event
	keyUp := conpty.NewKeyEventRecord(vk, ctrlState, false)
	records = append(records, keyUp.ToINPUTRecord())

	n, err := w.c.WriteConsoleInput(records)
	return int(n), err
}

// CSI tilde to VK mapping
var csiTildeToVK = map[int]uint16{
	1:  conpty.VK_HOME,    // Home
	2:  conpty.VK_INSERT,   // Insert
	3:  conpty.VK_DELETE,  // Delete
	4:  conpty.VK_END,     // End
	5:  conpty.VK_PRIOR,   // Page Up
	6:  conpty.VK_NEXT,    // Page Down
	11: conpty.VK_F1,
	12: conpty.VK_F2,
	13: conpty.VK_F3,
	14: conpty.VK_F4,
	15: conpty.VK_F5,
	16: conpty.VK_F6,
	17: conpty.VK_F7,
	18: conpty.VK_F8,
	19: conpty.VK_F9,
	20: conpty.VK_F10,
	21: conpty.VK_F11,
	23: conpty.VK_F12,
}

// CSI letter to VK mapping
var csiLetterToVK = map[byte]uint16{
	'A': conpty.VK_UP,     // Up
	'B': conpty.VK_DOWN,   // Down
	'C': conpty.VK_RIGHT,  // Right
	'D': conpty.VK_LEFT,   // Left
	'H': conpty.VK_HOME,  // Home
	'F': conpty.VK_END,   // End
}

// CSI modifier to control key state
var csiModifierToCtrlState = map[int]uint32{
	0: 0,
	2: conpty.LEFT_SHIFT_PRESSED | conpty.RIGHT_SHIFT_PRESSED,
	3: conpty.LEFT_ALT_PRESSED | conpty.RIGHT_ALT_PRESSED,
	4: conpty.LEFT_SHIFT_PRESSED | conpty.RIGHT_SHIFT_PRESSED | conpty.LEFT_ALT_PRESSED | conpty.RIGHT_ALT_PRESSED,
	5: conpty.LEFT_CTRL_PRESSED | conpty.RIGHT_CTRL_PRESSED,
	6: conpty.LEFT_SHIFT_PRESSED | conpty.RIGHT_SHIFT_PRESSED | conpty.LEFT_CTRL_PRESSED | conpty.RIGHT_CTRL_PRESSED,
	7: conpty.LEFT_ALT_PRESSED | conpty.RIGHT_ALT_PRESSED | conpty.LEFT_CTRL_PRESSED | conpty.RIGHT_CTRL_PRESSED,
	8: conpty.LEFT_SHIFT_PRESSED | conpty.RIGHT_SHIFT_PRESSED | conpty.LEFT_ALT_PRESSED | conpty.RIGHT_ALT_PRESSED | conpty.LEFT_CTRL_PRESSED | conpty.RIGHT_CTRL_PRESSED,
}

func CSIParamToModifier(modifier int) uint32 {
	if state, ok := csiModifierToCtrlState[modifier]; ok {
		return state
	}
	return 0
}

func (w *conptyStdin) Write(p []byte) (int, error) {
	if w.c == nil {
		return 0, io.ErrClosedPipe
	}

	// Process the input
	result := make([]byte, 0, len(p))
	i := 0
	for i < len(p) {
		b := p[i]

		// Check for CSI sequence start
		if b == 0x1B && i+1 < len(p) && p[i+1] == '[' {
			// Try to find the complete CSI sequence
			j := i + 2
			for j < len(p) && j < i+20 { // Limit search to prevent runaway
				c := p[j]
				if c >= 0x40 && c <= 0x7E {
					// Found final byte
					csiSeq := p[i : j+1]

					// Tilde format: CSI <num> [;<mod>] ~ (Home, End, Delete, F1-F12, etc.)
					if csiSeq[len(csiSeq)-1] == '~' {
						n, err := w.HandleCSIInput(csiSeq)
						if err == nil && n > 0 {
							i = j + 1
							continue
						}
					}

					// Letter format: CSI A/B/C/D (arrow keys)
					if vk, ok := csiLetterToVK[c]; ok {
						ctrlState := CSIParamToModifier(0)
						keyEvent := conpty.NewKeyEventRecord(vk, ctrlState, true)
						records := []conpty.INPUT_RECORD{keyEvent.ToINPUTRecord()}
						// Send key up
						keyUp := conpty.NewKeyEventRecord(vk, ctrlState, false)
						records = append(records, keyUp.ToINPUTRecord())

						n, err := w.c.WriteConsoleInput(records)
						if err == nil && n > 0 {
							i = j + 1
							continue
						}
					}

					break
				}
				j++
			}
		}

		// DEL (0x7F) → BS (0x08) conversion for Windows console compatibility
		if b == 0x7F {
			result = append(result, 0x08)
			i++
			continue
		}

		// Regular character - pass through
		result = append(result, b)
		i++
	}

	if len(result) > 0 {
		return w.c.Write(result)
	}
	return len(p), nil
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
	transformer := conpty.NewInputTransformer()
	return &interactiveShell{
		cpty:   c,
		Stdin:  &conptyStdin{c: c, t: transformer},
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
