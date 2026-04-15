//go:build windows
// +build windows

package conpty

import (
	"bytes"
	"fmt"
	"io"
	"log"
	"strings"
)

// OutputHandler handles ConPTY output processing for win32-input-mode protocol.
// When win32-input-mode is enabled, ConPTY sends enhanced keyboard information
// via CSI sequences instead of simple characters.
//
// This handler processes the output stream to:
// 1. Detect win32-input-mode enable/disable sequences
// 2. Parse and validate CSI sequences
// 3. Ensure proper forwarding of keyboard events
type OutputHandler struct {
	win32InputMode bool
	enableBuffer   []byte    // Buffer for partial escape sequences
	logEnabled     bool
}

// NewOutputHandler creates a new output handler.
func NewOutputHandler() *OutputHandler {
	return &OutputHandler{
		win32InputMode: false,
		enableBuffer:   make([]byte, 0, 64),
		logEnabled:     false,
	}
}

// EnableLogging enables debug logging.
func (h *OutputHandler) EnableLogging(enable bool) {
	h.logEnabled = enable
}

// IsWin32InputModeEnabled returns whether win32-input-mode is enabled.
func (h *OutputHandler) IsWin32InputModeEnabled() bool {
	return h.win32InputMode
}

// Process processes ConPTY output data.
// It detects win32-input-mode sequences and handles them appropriately.
func (h *OutputHandler) Process(data []byte) ([]byte, error) {
	if len(data) == 0 {
		return data, nil
	}

	// Check for win32-input-mode sequences
	h.processSequences(data)

	// For now, pass through data unchanged
	// The actual INPUT_RECORD → CSI conversion would happen here
	// if we were intercepting at the ConPTY level
	return data, nil
}

// processSequences detects and processes win32-input-mode sequences.
func (h *OutputHandler) processSequences(data []byte) {
	// Check for enable sequence: ESC[>4;1m
	if bytes.Contains(data, EnableSequence) {
		h.win32InputMode = true
		if h.logEnabled {
			log.Println("[OutputHandler] win32-input-mode ENABLED")
		}
	}

	// Check for disable sequence: ESC[>4m
	if bytes.Contains(data, DisableSequence) {
		h.win32InputMode = false
		if h.logEnabled {
			log.Println("[OutputHandler] win32-input-mode DISABLED")
		}
	}
}

// Reset resets the handler state.
func (h *OutputHandler) Reset() {
	h.win32InputMode = false
	h.enableBuffer = h.enableBuffer[:0]
}

// OutputReader wraps an io.Reader and processes ConPTY output.
type OutputReader struct {
	reader     io.Reader
	handler    *OutputHandler
	readBuffer []byte
}

// NewOutputReader creates a new output reader.
func NewOutputReader(r io.Reader) *OutputReader {
	return &OutputReader{
		reader:     r,
		handler:    NewOutputHandler(),
		readBuffer: make([]byte, 4096),
	}
}

// Read reads and processes ConPTY output.
func (r *OutputReader) Read(p []byte) (n int, err error) {
	// Read from underlying reader
	n, err = r.reader.Read(p)

	if n > 0 {
		// Process the output
		processed, processErr := r.handler.Process(p[:n])
		if processErr != nil {
			return 0, processErr
		}

		// Copy processed data to output buffer
		copy(p, processed)
	}

	return n, err
}

// IsWin32InputModeEnabled returns whether win32-input-mode is enabled.
func (r *OutputReader) IsWin32InputModeEnabled() bool {
	return r.handler.IsWin32InputModeEnabled()
}

// Win32InputModeReader wraps ConPTY stdout and handles win32-input-mode protocol.
// This is the main entry point for integrating win32-input-mode support.
type Win32InputModeReader struct {
	conPty      *ConPty
	mode        bool // true when win32-input-mode is active
	logEnabled  bool
}

// NewWin32InputModeReader creates a new reader that handles win32-input-mode protocol.
func NewWin32InputModeReader(cpty *ConPty) *Win32InputModeReader {
	return &Win32InputModeReader{
		conPty:     cpty,
		mode:       false,
		logEnabled: false,
	}
}

// EnableLogging enables debug logging.
func (r *Win32InputModeReader) EnableLogging(enable bool) {
	r.logEnabled = enable
}

// IsModeEnabled returns whether win32-input-mode is currently enabled.
func (r *Win32InputModeReader) IsModeEnabled() bool {
	return r.mode
}

// Read reads output from ConPTY and processes win32-input-mode sequences.
func (r *Win32InputModeReader) Read(p []byte) (n int, err error) {
	// Read from ConPTY
	n, err = r.conPty.Read(p)

	if n > 0 && r.logEnabled {
		// Log output for debugging
		segment := string(p[:n])
		if len(segment) > 200 {
			segment = segment[:200] + "..."
		}
		// Don't log binary data
		if !strings.ContainsAny(segment[:min(len(segment), 50)], "\x00\x01\x02\x03\x04\x05\x06\x07") {
			log.Printf("[Win32InputMode] Output: %q", segment)
		}
	}

	// Check for mode change sequences
	r.checkModeChange(p[:n])

	return n, err
}

// checkModeChange checks for win32-input-mode enable/disable sequences.
func (r *Win32InputModeReader) checkModeChange(data []byte) {
	if bytes.Contains(data, EnableSequence) {
		r.mode = true
		if r.logEnabled {
			log.Println("[Win32InputMode] ENABLED - receiving enhanced keyboard input")
		}
	}
	if bytes.Contains(data, DisableSequence) {
		r.mode = false
		if r.logEnabled {
			log.Println("[Win32InputMode] DISABLED")
		}
	}
}

// Close closes the underlying ConPTY.
func (r *Win32InputModeReader) Close() error {
	return r.conPty.Close()
}

// Wait waits for the process to exit.
func (r *Win32InputModeReader) Wait(ctx interface{}) (uint32, error) {
	// This would need context.Context - simplified for now
	return 0, nil
}

// DetectCSIFromConPTYOutput analyzes ConPTY output to detect CSI sequences.
// This can be used for debugging to see what ConPTY is actually sending.
func DetectCSIFromConPTYOutput(data []byte) []string {
	var sequences []string
	var current bytes.Buffer

	for i := 0; i < len(data); i++ {
		b := data[i]

		if b == 0x1B {
			// Start of escape sequence
			if current.Len() > 0 {
				sequences = append(sequences, "DATA:"+current.String())
				current.Reset()
			}
			current.WriteByte(b)
		} else if current.Len() > 0 {
			current.WriteByte(b)
			// Check if this completes a CSI sequence
			if b >= 0x40 && b <= 0x7E {
				// Final byte reached - sequence complete
				seq := current.String()
				sequences = append(sequences, formatCSI(seq))
				current.Reset()
			}
			// Safety: if buffer gets too long, reset
			if current.Len() > 32 {
				sequences = append(sequences, "TRUNCATED:"+current.String())
				current.Reset()
			}
		}
	}

	if current.Len() > 0 {
		sequences = append(sequences, "DATA:"+current.String())
	}

	return sequences
}

// formatCSI formats a CSI sequence for readability.
func formatCSI(seq string) string {
	if len(seq) < 3 {
		return "UNKNOWN:" + seq
	}
	if seq[0] == 0x1B && seq[1] == '[' {
		// CSI sequence
		params := seq[2 : len(seq)-1]
		final := seq[len(seq)-1]
		return fmt.Sprintf("CSI[%s%c]", params, final)
	}
	if seq[0] == 0x1B {
		return fmt.Sprintf("ESC[%c]", seq[1])
	}
	return "UNKNOWN:" + seq
}
