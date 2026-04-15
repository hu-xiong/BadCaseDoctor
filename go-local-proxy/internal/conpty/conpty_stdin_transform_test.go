//go:build windows
// +build windows

package conpty

import (
	"bytes"
	"testing"
)

func TestTransformDELToBS(t *testing.T) {
	transformer := NewInputTransformer()

	tests := []struct {
		name     string
		input    []byte
		expected []byte
	}{
		{
			name:     "single DEL converted to BS",
			input:    []byte{0x7F},
			expected: []byte{0x08},
		},
		{
			name:     "multiple DELs converted",
			input:    []byte{0x7F, 0x7F, 0x7F},
			expected: []byte{0x08, 0x08, 0x08},
		},
		{
			name:     "no DEL unchanged",
			input:    []byte("hello"),
			expected: []byte("hello"),
		},
		{
			name:     "mixed DEL and text",
			input:    []byte("hel\x7Flo"),
			expected: []byte("hel\x08lo"),
		},
		{
			name:     "empty input unchanged",
			input:    []byte{},
			expected: []byte{},
		},
		{
			name:     "BS unchanged",
			input:    []byte{0x08},
			expected: []byte{0x08},
		},
		{
			name:     "normal text unchanged",
			input:    []byte("Hello, World!"),
			expected: []byte("Hello, World!"),
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := transformer.Transform(tt.input)
			if !bytes.Equal(result, tt.expected) {
				t.Errorf("Transform() = %v, want %v", result, tt.expected)
			}
		})
	}
}

func TestTransformStats(t *testing.T) {
	transformer := NewInputTransformer()

	// Reset stats
	transformer.ResetStats()

	// Transform some data with DEL
	transformer.Transform([]byte{0x7F, 0x7F, 'a'})

	transformCount, byteCount := transformer.Stats()
	if transformCount != 2 {
		t.Errorf("transformCount = %d, want 2", transformCount)
	}
	if byteCount != 3 {
		t.Errorf("byteCount = %d, want 3", byteCount)
	}
}

func TestEnableDisableSequence(t *testing.T) {
	tests := []struct {
		name     string
		data     []byte
		want     bool
		checkFn  func([]byte) bool
	}{
		{
			name:    "enable sequence matches",
			data:    []byte{0x1B, '[', '>', '4', ';', '1', 'm'},
			want:    true,
			checkFn: IsEnableSequence,
		},
		{
			name:    "enable sequence with prefix",
			data:    []byte{0xFF, 0x1B, '[', '>', '4', ';', '1', 'm'},
			want:    false,
			checkFn: IsEnableSequence,
		},
		{
			name:    "disable sequence matches",
			data:    []byte{0x1B, '[', '>', '4', 'm'},
			want:    true,
			checkFn: IsDisableSequence,
		},
		{
			name:    "similar but not enable",
			data:    []byte{0x1B, '[', '>', '5', ';', '1', 'm'},
			want:    false,
			checkFn: IsEnableSequence,
		},
		{
			name:    "partial enable sequence",
			data:    []byte{0x1B, '[', '>', '4', ';'},
			want:    false,
			checkFn: IsEnableSequence,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := tt.checkFn(tt.data); got != tt.want {
				t.Errorf("%v = %v, want %v", tt.name, got, tt.want)
			}
		})
	}
}

func TestInputTransformerEnableDisable(t *testing.T) {
	transformer := NewInputTransformer()

	if !transformer.IsEnabled() {
		t.Error("NewInputTransformer should be enabled by default")
	}

	transformer.DisableWin32InputMode()
	if transformer.IsEnabled() {
		t.Error("DisableWin32InputMode should disable transformer")
	}

	transformer.EnableWin32InputMode()
	if !transformer.IsEnabled() {
		t.Error("EnableWin32InputMode should enable transformer")
	}
}

func TestTransformEnableSequenceDetection(t *testing.T) {
	transformer := NewInputTransformer()

	// Send enable sequence
	data := []byte{0x1B, '[', '>', '4', ';', '1', 'm', 'a'}
	result := transformer.Transform(data)

	// Should pass through unchanged and enable mode
	if !bytes.Equal(result, data) {
		t.Errorf("Enable sequence should pass through unchanged")
	}
	if !transformer.IsEnabled() {
		t.Error("Transformer should be enabled after receiving enable sequence")
	}
}

func TestTransformDisableSequenceDetection(t *testing.T) {
	transformer := NewInputTransformer()
	transformer.EnableWin32InputMode() // Ensure enabled first

	// Send disable sequence
	data := []byte{0x1B, '[', '>', '4', 'm', 'a'}
	result := transformer.Transform(data)

	// Should pass through unchanged and disable mode
	if !bytes.Equal(result, data) {
		t.Errorf("Disable sequence should pass through unchanged")
	}
	if transformer.IsEnabled() {
		t.Error("Transformer should be disabled after receiving disable sequence")
	}
}

func TestTransformString(t *testing.T) {
	transformer := NewInputTransformer()

	input := "hel\x7Flo"
	expected := "hel\x08lo"

	result := transformer.TransformString(input)
	if result != expected {
		t.Errorf("TransformString() = %v, want %v", result, expected)
	}
}

func TestTransformReset(t *testing.T) {
	transformer := NewInputTransformer()

	transformer.DisableWin32InputMode()
	transformer.ResetStats()

	// Transform data to set stats
	transformer.Transform([]byte{0x7F, 0x7F})

	transformer.Reset()

	if !transformer.IsEnabled() {
		t.Error("Reset should enable transformer")
	}

	transformCount, _ := transformer.Stats()
	if transformCount != 0 {
		t.Error("Reset should clear stats")
	}
}

func TestFastPathNoDEL(t *testing.T) {
	transformer := NewInputTransformer()

	// Large input without DEL - should be very fast
	largeInput := bytes.Repeat([]byte("Hello, World! This is a test.\n"), 1000)
	
	result := transformer.Transform(largeInput)
	if !bytes.Equal(result, largeInput) {
		t.Error("Input without DEL should pass through unchanged")
	}
}

func TestFastPathNoEscape(t *testing.T) {
	transformer := NewInputTransformer()

	// Input with DEL but no escape
	input := bytes.Repeat([]byte{0x7F}, 100)
	expected := bytes.Repeat([]byte{0x08}, 100)

	result := transformer.Transform(input)
	if !bytes.Equal(result, expected) {
		t.Error("DELs should be converted to BS")
	}
}
