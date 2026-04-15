//go:build windows
// +build windows

package conpty

import (
	"bytes"
)

// EnableSequence is the escape sequence to enable win32-input-mode on ConPTY.
// When xterm.js sends this sequence, ConPTY switches to enhanced keyboard mode.
// Format: ESC [ > 4 ; 1 m
var EnableSequence = []byte{0x1B, '[', '>', '4', ';', '1', 'm'}

// DisableSequence is the escape sequence to disable win32-input-mode.
// Format: ESC [ > 4 m
var DisableSequence = []byte{0x1B, '[', '>', '4', 'm'}

// IsEnableSequence checks if the given data starts with the enable sequence.
func IsEnableSequence(data []byte) bool {
	return len(data) >= len(EnableSequence) &&
		bytes.Equal(data[:len(EnableSequence)], EnableSequence)
}

// IsDisableSequence checks if the given data starts with the disable sequence.
func IsDisableSequence(data []byte) bool {
	return len(data) >= len(DisableSequence) &&
		bytes.Equal(data[:len(DisableSequence)], DisableSequence)
}

// InputTransformer handles input transformation for ConPTY.
// Specifically handles DEL→BS conversion for Windows console applications.
type InputTransformer struct {
	enabled         bool
	pendingEnable   bool // buffering partial sequence
	enableBuffer    []byte
	disableBuffer   []byte
	transformCount  int64 // statistics: number of DEL→BS conversions
	byteCount       int64 // statistics: total bytes processed
}

// NewInputTransformer creates a new input transformer.
func NewInputTransformer() *InputTransformer {
	return &InputTransformer{
		enabled:      true, // Default to enabled for ConPTY
		enableBuffer: make([]byte, 0, len(EnableSequence)-1),
		disableBuffer: make([]byte, 0, len(DisableSequence)-1),
	}
}

// EnableWin32InputMode enables win32-input-mode handling.
func (t *InputTransformer) EnableWin32InputMode() {
	t.enabled = true
}

// DisableWin32InputMode disables win32-input-mode handling.
func (t *InputTransformer) DisableWin32InputMode() {
	t.enabled = false
}

// IsEnabled returns whether the transformer is enabled.
func (t *InputTransformer) IsEnabled() bool {
	return t.enabled
}

// Stats returns transformer statistics.
func (t *InputTransformer) Stats() (transformCount, byteCount int64) {
	return t.transformCount, t.byteCount
}

// ResetStats resets transformer statistics.
func (t *InputTransformer) ResetStats() {
	t.transformCount = 0
	t.byteCount = 0
}

// Transform processes input data and applies necessary transformations:
//  1. DEL (0x7F) → BS (0x08) for proper backspace handling in Windows console apps
//  2. Detects and handles win32-input-mode enable/disable sequences
//
// This is necessary because:
//   - Windows console uses BS (0x08) for backspace
//   - xterm.js sends DEL (0x7F) by default
//   - PowerShell/PSReadLine expects BS for proper backspace functionality
func (t *InputTransformer) Transform(data []byte) []byte {
	if len(data) == 0 {
		return data
	}

	t.byteCount += int64(len(data))

	// Fast path: if no DEL in data and no escape sequences, return as-is
	hasDEL := bytes.ContainsRune(data, 0x7F)
	hasEscape := bytes.ContainsRune(data, 0x1B)
	
	if !hasDEL && !hasEscape {
		return data
	}

	result := make([]byte, 0, len(data))

	for i := 0; i < len(data); i++ {
		b := data[i]

		// Check for escape sequence start
		if b == 0x1B {
			// Check if this could be the start of a mode sequence
			remaining := len(data) - i
			
			// Check for enable sequence (ESC[>4;1m)
			if remaining >= len(EnableSequence) && bytes.Equal(data[i:i+len(EnableSequence)], EnableSequence) {
				result = append(result, data[i:i+len(EnableSequence)]...)
				i += len(EnableSequence) - 1
				t.EnableWin32InputMode()
				continue
			}
			
			// Check for disable sequence (ESC[>4m)
			if remaining >= len(DisableSequence) && bytes.Equal(data[i:i+len(DisableSequence)], DisableSequence) {
				result = append(result, data[i:i+len(DisableSequence)]...)
				i += len(DisableSequence) - 1
				t.DisableWin32InputMode()
				continue
			}
		}

		// DEL (0x7F) → BS (0x08) conversion
		// This is the core fix for Windows console backspace issues
		if b == 0x7F {
			result = append(result, 0x08) // Convert DEL to BS
			t.transformCount++
			continue
		}

		result = append(result, b)
	}

	return result
}

// TransformString is a convenience wrapper for Transform with strings.
func (t *InputTransformer) TransformString(s string) string {
	return string(t.Transform([]byte(s)))
}

// Reset resets the transformer state.
func (t *InputTransformer) Reset() {
	t.enabled = true
	t.pendingEnable = false
	t.enableBuffer = t.enableBuffer[:0]
	t.disableBuffer = t.disableBuffer[:0]
	t.ResetStats()
}

// TransformStream is a helper for transforming streaming data.
// Returns a WriteCloser that transforms all written data.
func (t *InputTransformer) TransformStream(w interface {
	Write([]byte) (int, error)
	Close() error
}) interface {
	Write([]byte) (int, error)
	Close() error
} {
	return &transformWriter{t: t, w: w}
}

type transformWriter struct {
	t *InputTransformer
	w interface {
		Write([]byte) (int, error)
		Close() error
	}
}

func (tw *transformWriter) Write(p []byte) (int, error) {
	transformed := tw.t.Transform(p)
	n, err := tw.w.Write(transformed)
	if n > len(p) {
		n = len(p)
	}
	return n, err
}

func (tw *transformWriter) Close() error {
	return tw.w.Close()
}
