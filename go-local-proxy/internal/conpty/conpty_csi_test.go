//go:build windows
// +build windows

package conpty

import (
	"bytes"
	"testing"
)

func TestParseCSIModifier(t *testing.T) {
	tests := []struct {
		name     string
		state    uint32
		expected int
	}{
		{"no modifier", 0, CSIModNone},
		{"shift only", LEFT_SHIFT_PRESSED, CSIModShift},
		{"alt only", LEFT_ALT_PRESSED, CSIModAlt},
		{"ctrl only", LEFT_CTRL_PRESSED, CSIModCtrl},
		{"shift+alt", LEFT_SHIFT_PRESSED | LEFT_ALT_PRESSED, CSIModShiftAlt},
		{"shift+ctrl", LEFT_SHIFT_PRESSED | LEFT_CTRL_PRESSED, CSIModShiftCtrl},
		{"alt+ctrl", LEFT_ALT_PRESSED | LEFT_CTRL_PRESSED, CSIModAltCtrl},
		{"all modifiers", LEFT_SHIFT_PRESSED | LEFT_ALT_PRESSED | LEFT_CTRL_PRESSED, CSIModShiftAltCtrl},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := ParseCSIModifier(tt.state)
			if result != tt.expected {
				t.Errorf("ParseCSIModifier(0x%X) = %d, want %d", tt.state, result, tt.expected)
			}
		})
	}
}

func TestVirtualKeyCodeToCSI(t *testing.T) {
	tests := []struct {
		name     string
		vk       uint16
		modifier uint32
		wantKey  int
		wantMod  int
	}{
		{"backspace", VK_BACK, 0, int(CSIKEY_Backspace), CSIModNone},
		{"tab", VK_TAB, 0, int(CSIKEY_Tab), CSIModNone},
		{"left arrow", VK_LEFT, 0, int(CSIKEY_Left), CSIModNone},
		{"up arrow", VK_UP, 0, int(CSIKEY_Up), CSIModNone},
		{"right arrow", VK_RIGHT, 0, int(CSIKEY_Right), CSIModNone},
		{"down arrow", VK_DOWN, 0, int(CSIKEY_Down), CSIModNone},
		{"delete", VK_DELETE, 0, int(CSIKEY_Delete), CSIModNone},
		{"home", VK_HOME, 0, int(CSIKEY_Home), CSIModNone},
		{"end", VK_END, 0, int(CSIKEY_End), CSIModNone},
		{"insert", VK_INSERT, 0, int(CSIKEY_Insert), CSIModNone},
		{"page up", VK_PRIOR, 0, int(CSIKEY_PageUp), CSIModNone},
		{"page down", VK_NEXT, 0, int(CSIKEY_PageDown), CSIModNone},
		{"F1", VK_F1, 0, int(CSIKEY_F1), CSIModNone},
		{"F12", VK_F12, 0, int(CSIKEY_F12), CSIModNone},
		{"left with ctrl", VK_LEFT, LEFT_CTRL_PRESSED, int(CSIKEY_Left), CSIModCtrl},
		{"right with ctrl", VK_RIGHT, LEFT_CTRL_PRESSED, int(CSIKEY_Right), CSIModCtrl},
		{"left with shift", VK_LEFT, LEFT_SHIFT_PRESSED, int(CSIKEY_Left), CSIModShift},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			key, mod, _ := VirtualKeyCodeToCSI(tt.vk, tt.modifier)
			if key != tt.wantKey {
				t.Errorf("VirtualKeyCodeToCSI key = %d, want %d", key, tt.wantKey)
			}
			if mod != tt.wantMod {
				t.Errorf("VirtualKeyCodeToCSI modifier = %d, want %d", mod, tt.wantMod)
			}
		})
	}
}

func TestBuildCSISequence(t *testing.T) {
	tests := []struct {
		name           string
		keyCode        int
		modifier       int
		useTildeFormat bool
		expected       []byte
	}{
		// Arrow keys use SS3 format (ESC O {final}) - 3 bytes
		{"simple arrow up", 'A', 0, false, []byte{0x1B, 'O', 'A'}},
		{"simple arrow down", 'B', 0, false, []byte{0x1B, 'O', 'B'}},
		{"simple arrow right", 'C', 0, false, []byte{0x1B, 'O', 'C'}},
		{"simple arrow left", 'D', 0, false, []byte{0x1B, 'O', 'D'}},
		// Arrow with modifier uses CSI format with params - 6 bytes
		{"arrow up with ctrl", 'A', CSIModCtrl, false, []byte{0x1B, '[', '1', ';', '5', 'A'}},
		{"arrow left with ctrl", 'D', CSIModCtrl, false, []byte{0x1B, '[', '4', ';', '5', 'D'}},
		// Tilde format keys - CSI format
		{"simple home", CSIKEY_Home, 0, true, []byte{0x1B, '[', '1', '~'}},
		{"home with modifier", CSIKEY_Home, CSIModShift, true, []byte{0x1B, '[', '1', ';', '2', '~'}},
		{"simple delete", CSIKEY_Delete, 0, true, []byte{0x1B, '[', '3', '~'}},
		{"delete with ctrl", CSIKEY_Delete, CSIModCtrl, true, []byte{0x1B, '[', '3', ';', '5', '~'}},
		{"F1", CSIKEY_F1, 0, true, []byte{0x1B, '[', '1', '1', '~'}},
		{"F12", CSIKEY_F12, 0, true, []byte{0x1B, '[', '2', '3', '~'}},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := BuildCSISequence(tt.keyCode, tt.modifier, tt.useTildeFormat)
			if !bytes.Equal(result, tt.expected) {
				t.Errorf("BuildCSISequence() = %v, want %v", result, tt.expected)
			}
		})
	}
}

func TestBuildCSIForKeyEvent(t *testing.T) {
	tests := []struct {
		name        string
		event       *KEY_EVENT_RECORD
		expectedLen int // 0 means expect nil (key release)
	}{
		{
			name: "printable character 'a'",
			event: &KEY_EVENT_RECORD{
				bKeyDown:         1,
				wVirtualKeyCode:   0,
				UnicodeChar:       'a',
				dwControlKeyState: 0,
			},
			expectedLen: 1,
		},
		{
			name: "key release ignored",
			event: &KEY_EVENT_RECORD{
				bKeyDown:   0,
				UnicodeChar: 'a',
			},
			expectedLen: 0,
		},
		{
			name: "left arrow (SS3 format)",
			event: &KEY_EVENT_RECORD{
				bKeyDown:         1,
				wVirtualKeyCode:   VK_LEFT,
				UnicodeChar:       0,
				dwControlKeyState: 0,
			},
			expectedLen: 3, // \x1B O D (ESC O D)
		},
		{
			name: "ctrl+left arrow (CSI format)",
			event: &KEY_EVENT_RECORD{
				bKeyDown:         1,
				wVirtualKeyCode:   VK_LEFT,
				UnicodeChar:       0,
				dwControlKeyState: LEFT_CTRL_PRESSED,
			},
			expectedLen: 6, // \x1B [ 4 ; 5 D
		},
		{
			name: "delete key",
			event: &KEY_EVENT_RECORD{
				bKeyDown:         1,
				wVirtualKeyCode:   VK_DELETE,
				UnicodeChar:       0,
				dwControlKeyState: 0,
			},
			expectedLen: 4, // \x1B [ 3 ~
		},
		{
			name: "F1",
			event: &KEY_EVENT_RECORD{
				bKeyDown:         1,
				wVirtualKeyCode:   VK_F1,
				UnicodeChar:       0,
				dwControlKeyState: 0,
			},
			expectedLen: 5, // \x1B [ 1 1 ~
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result, err := BuildCSIForKeyEvent(tt.event)
			if err != nil {
				t.Errorf("BuildCSIForKeyEvent() error = %v", err)
				return
			}
			if tt.expectedLen == 0 {
				if result != nil {
					t.Errorf("BuildCSIForKeyEvent() = %v, want nil", result)
				}
			} else {
				if len(result) != tt.expectedLen {
					t.Errorf("BuildCSIForKeyEvent() len = %d, want %d, got %v", len(result), tt.expectedLen, result)
				}
			}
		})
	}
}

func TestIsCSISequenceStart(t *testing.T) {
	tests := []struct {
		name     string
		data     []byte
		expected bool
	}{
		{"CSI start", []byte("\x1B[1;5D"), true},
		{"plain ESC", []byte("\x1B"), false},
		{"regular text", []byte("hello"), false},
		{"empty", []byte{}, false},
		{"CSI extended", []byte("\x1B[>4;1m"), true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := IsCSISequenceStart(tt.data)
			if result != tt.expected {
				t.Errorf("IsCSISequenceStart(%v) = %v, want %v", tt.data, result, tt.expected)
			}
		})
	}
}

func TestParseCSISequence(t *testing.T) {
	tests := []struct {
		name          string
		data          []byte
		wantPrefix    string
		wantParams    string
		wantFinal     byte
		wantConsume   int
		wantErr       bool
	}{
		{"CSI 1;5D", []byte("\x1B[1;5D"), "CSI", "1;5", 'D', 6, false},
		{"CSI A", []byte("\x1B[A"), "CSI", "", 'A', 3, false},
		{"CSI 3~", []byte("\x1B[3~"), "CSI", "3", '~', 4, false},
		{"plain text", []byte("hello"), "", "", 0, 0, true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			prefix, params, _, final, consumed, err := ParseCSISequence(tt.data)
			if (err != nil) != tt.wantErr {
				t.Errorf("ParseCSISequence() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if prefix != tt.wantPrefix {
				t.Errorf("ParseCSISequence() prefix = %v, want %v", prefix, tt.wantPrefix)
			}
			if params != tt.wantParams {
				t.Errorf("ParseCSISequence() params = %v, want %v", params, tt.wantParams)
			}
			if final != tt.wantFinal {
				t.Errorf("ParseCSISequence() final = %v, want %v", final, tt.wantFinal)
			}
			if consumed != tt.wantConsume {
				t.Errorf("ParseCSISequence() consumed = %v, want %v", consumed, tt.wantConsume)
			}
		})
	}
}

func TestDetectCSIFromConPTYOutput(t *testing.T) {
	// Test that CSI sequences are detected correctly
	data := []byte("\x1B[>4;1mhello\x1B[Cworld\x1B[D")
	sequences := DetectCSIFromConPTYOutput(data)

	// Should find at least 2 CSI sequences
	if len(sequences) < 2 {
		t.Errorf("DetectCSIFromConPTYOutput() found %d sequences, want at least 2", len(sequences))
	}
}
