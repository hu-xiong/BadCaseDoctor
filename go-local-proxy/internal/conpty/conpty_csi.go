//go:build windows
// +build windows

package conpty

import (
	"fmt"
)

// CSI sequence constants for win32-input-mode protocol
// Reference: https://invisible-island.net/xterm/ctlseqs/ctlseqs.html#h3-Functions-using_CSI_-ordered_by_the_final_characters_s_
const (
	// CSI modifier key codes for win32-input-mode
	CSIModNone  = 0
	CSIModShift = 2
	CSIModAlt   = 3
	CSIModShiftAlt = 4
	CSIModCtrl  = 5
	CSIModShiftCtrl = 6
	CSIModAltCtrl = 7
	CSIModShiftAltCtrl = 8
)

// CSI key codes - these are used in the form CSI <key> [; <modifier>] ~
// For tilde (~) format, these are decimal numbers
// For letter (A/B/C/D) format, these are the ASCII codes
const (
	CSIKEY_Tab          = 0x09
	CSIKEY_Enter        = 0x0D
	CSIKEY_Enter2       = 0x0A // Also mapped to Enter in some contexts
	CSIKEY_Backspace    = 0x7F // DEL, but used as backspace in CSI

	// Tilde format keys (decimal numbers)
	CSIKEY_Home         = 1
	CSIKEY_Insert       = 2
	CSIKEY_Delete       = 3
	CSIKEY_End          = 4
	CSIKEY_PageUp       = 5
	CSIKEY_PageDown     = 6

	// F1-F4 use SS3 format (ESC O P/Q/R/S), F5-F12 use CSI ~ format
	CSIKEY_F1           = 11
	CSIKEY_F2           = 12
	CSIKEY_F3           = 13
	CSIKEY_F4           = 14
	CSIKEY_F5           = 15
	CSIKEY_F6           = 16
	CSIKEY_F7           = 17
	CSIKEY_F8           = 18
	CSIKEY_F9           = 19
	CSIKEY_F10          = 20
	CSIKEY_F11          = 21
	CSIKEY_F12          = 23

	// Arrow keys - these use letter format (A/B/C/D) in standard CSI
	CSIKEY_Up           = 'A' // 65
	CSIKEY_Down         = 'B' // 66
	CSIKEY_Right        = 'C' // 67
	CSIKEY_Left         = 'D' // 68
)

// CSI standard key codes (used in CSI <key> H/L format)
const (
	CSIKEY_StandardHome  = 'H' // Home
	CSIKEY_StandardEnd   = 'F' // End
	CSIKEY_StandardUp    = 'A'
	CSIKEY_StandardDown  = 'B'
	CSIKEY_StandardRight = 'C'
	CSIKEY_StandardLeft  = 'D'
)

// Virtual key codes from Windows API
// https://docs.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes
const (
	VK_BACK        = 0x08
	VK_TAB         = 0x09
	VK_SHIFT       = 0x10
	VK_CONTROL     = 0x11
	VK_MENU        = 0x12 // ALT key
	VK_ESCAPE      = 0x1B
	VK_SPACE       = 0x20
	VK_END         = 0x23
	VK_HOME        = 0x24
	VK_LEFT        = 0x25
	VK_UP          = 0x26
	VK_RIGHT       = 0x27
	VK_DOWN        = 0x28
	VK_DELETE      = 0x2E
	VK_INSERT      = 0x2D
	VK_PRIOR       = 0x21 // Page Up
	VK_NEXT        = 0x22 // Page Down
	VK_LWIN        = 0x5B
	VK_RWIN        = 0x5C
	VK_APPS        = 0x5D
	VK_F1          = 0x70
	VK_F2          = 0x71
	VK_F3          = 0x72
	VK_F4          = 0x73
	VK_F5          = 0x74
	VK_F6          = 0x75
	VK_F7          = 0x76
	VK_F8          = 0x77
	VK_F9          = 0x78
	VK_F10         = 0x79
	VK_F11         = 0x7A
	VK_F12         = 0x7B
	VK_NUMPAD0     = 0x60
	VK_NUMPAD1     = 0x61
	VK_NUMPAD2     = 0x62
	VK_NUMPAD3     = 0x63
	VK_NUMPAD4     = 0x64
	VK_NUMPAD5     = 0x65
	VK_NUMPAD6     = 0x66
	VK_NUMPAD7     = 0x67
	VK_NUMPAD8     = 0x68
	VK_NUMPAD9     = 0x69
	VK_MULTIPLY    = 0x6A
	VK_ADD         = 0x6B
	VK_SEPARATOR   = 0x6C
	VK_SUBTRACT    = 0x6D
	VK_DECIMAL     = 0x6E
	VK_DIVIDE      = 0x6F
)

// CSI escape sequence prefix
var (
	CSIPrefix     = []byte{0x1B, 0x5B}       // ESC [
	CSIEnd        = byte('~')                 // CSI...~ format
	CSIHFormatEnd = []byte{'H', 'L'}          // CSI...H/L format for Home/End
)

// CSI modifier table - maps control key state to CSI modifier value
var csiModifiers = []int{
	0,    // 0b000 = no modifiers
	0,    // 0b001 = undefined
	CSIModShift, // 0b010 = Shift
	0,    // 0b011 = undefined
	CSIModAlt,   // 0b100 = Alt
	0,    // 0b101 = undefined
	CSIModShiftAlt, // 0b110 = Shift+Alt
	0,    // 0b111 = undefined
	CSIModCtrl,  // 0b1000 = Ctrl
	0,    // 0b1001 = undefined
	CSIModShiftCtrl, // 0b1010 = Shift+Ctrl
	0,    // 0b1011 = undefined
	CSIModAltCtrl,  // 0b1100 = Alt+Ctrl
	0,    // 0b1101 = undefined
	CSIModShiftAltCtrl, // 0b1110 = Shift+Alt+Ctrl
	0,    // 0b1111 = undefined
}

// ParseModifierState converts Windows control key state to CSI modifier value.
func ParseCSIModifier(ctrlKeyState uint32) int {
	shift := (ctrlKeyState & (LEFT_SHIFT_PRESSED | RIGHT_SHIFT_PRESSED)) != 0
	alt := (ctrlKeyState & (LEFT_ALT_PRESSED | RIGHT_ALT_PRESSED)) != 0
	ctrl := (ctrlKeyState & (LEFT_CTRL_PRESSED | RIGHT_CTRL_PRESSED)) != 0

	// Calculate index for lookup table
	idx := 0
	if shift {
		idx |= 0x02
	}
	if alt {
		idx |= 0x04
	}
	if ctrl {
		idx |= 0x08
	}

	return csiModifiers[idx]
}

// VirtualKeyCodeToCSI converts a Windows virtual key code to CSI sequence parameters.
// Returns (keyCode, modifier, isCSIFormat) where isCSIFormat indicates CSI ~ format.
func VirtualKeyCodeToCSI(vk uint16, ctrlKeyState uint32) (keyCode int, modifier int, isCSIFormat bool) {
	modifier = ParseCSIModifier(ctrlKeyState)

	switch vk {
	case VK_BACK:
		return int(CSIKEY_Backspace), modifier, true // CSI 127~
	case VK_TAB:
		return int(CSIKEY_Tab), modifier, true
	case VK_ESCAPE:
		return 0x1B, modifier, false // Raw escape
	case VK_SPACE:
		return int(' '), modifier, false
	case VK_INSERT:
		return int(CSIKEY_Insert), modifier, true // CSI 2~
	case VK_HOME:
		return int(CSIKEY_Home), modifier, true // CSI 1~
	case VK_END:
		return int(CSIKEY_End), modifier, true // CSI 4~
	case VK_PRIOR: // Page Up
		return int(CSIKEY_PageUp), modifier, true // CSI 5~
	case VK_NEXT: // Page Down
		return int(CSIKEY_PageDown), modifier, true // CSI 6~
	case VK_LEFT:
		return int(CSIKEY_Left), modifier, false // CSI D or CSI 1;5D
	case VK_UP:
		return int(CSIKEY_Up), modifier, false // CSI A or CSI 1;5A
	case VK_RIGHT:
		return int(CSIKEY_Right), modifier, false // CSI C or CSI 1;5C
	case VK_DOWN:
		return int(CSIKEY_Down), modifier, false // CSI B or CSI 1;5B
	case VK_DELETE:
		return int(CSIKEY_Delete), modifier, true // CSI 3~
	case VK_F1:
		return int(CSIKEY_F1), modifier, true // CSI 11~
	case VK_F2:
		return int(CSIKEY_F2), modifier, true // CSI 12~
	case VK_F3:
		return int(CSIKEY_F3), modifier, true // CSI 13~
	case VK_F4:
		return int(CSIKEY_F4), modifier, true // CSI 14~
	case VK_F5:
		return int(CSIKEY_F5), modifier, true // CSI 15~
	case VK_F6:
		return int(CSIKEY_F6), modifier, true // CSI 16~
	case VK_F7:
		return int(CSIKEY_F7), modifier, true // CSI 17~
	case VK_F8:
		return int(CSIKEY_F8), modifier, true // CSI 18~
	case VK_F9:
		return int(CSIKEY_F9), modifier, true // CSI 19~
	case VK_F10:
		return int(CSIKEY_F10), modifier, true // CSI 20~
	case VK_F11:
		return int(CSIKEY_F11), modifier, true // CSI 21~
	case VK_F12:
		return int(CSIKEY_F12), modifier, true // CSI 23~
	default:
		return -1, modifier, false // Not handled
	}
}

// BuildCSISequence builds a CSI sequence from key code and modifier.
// For useTildeFormat=true: CSI {key}[;{modifier}]~  (e.g., CSI 1;5~)
// For useTildeFormat=false and modifier=0: SS3 {final}  (e.g., SS3 A = ESC O A)
// For useTildeFormat=false and modifier>0: CSI {param};{modifier}{final}  (e.g., CSI 1;5D)
func BuildCSISequence(keyCode int, modifier int, useTildeFormat bool) []byte {
	var result []byte

	if useTildeFormat {
		// CSI format: ESC [
		result = append(result, 0x1B, '[')
		// Format: CSI {key}[;{modifier}]~
		if modifier > 0 {
			result = append(result, []byte(fmt.Sprintf("%d;%d~", keyCode, modifier))...)
		} else {
			result = append(result, []byte(fmt.Sprintf("%d~", keyCode))...)
		}
	} else {
		// SS3 format: ESC O {final} (for simple arrow keys)
		// OR CSI format with modifier: CSI {param};{modifier}{final}
		if modifier > 0 {
			// CSI format with modifier
			result = append(result, 0x1B, '[')
			// For arrow keys with modifier: CSI 1;5D (where 1 is the param, 5 is modifier, D is final)
			param := 0
			switch keyCode {
			case 'A':
				param = 1
			case 'B':
				param = 2
			case 'C':
				param = 3
			case 'D':
				param = 4
			default:
				param = keyCode
			}
			result = append(result, []byte(fmt.Sprintf("%d;%d%c", param, modifier, byte(keyCode)))...)
		} else {
			// Simple SS3 format: ESC O {final}
			result = append(result, 0x1B, 'O')
			result = append(result, byte(keyCode))
		}
	}
	return result
}

// BuildCSIForKeyEvent builds a CSI sequence from a KEY_EVENT_RECORD.
// This is the main function for win32-input-mode output.
func BuildCSIForKeyEvent(event *KEY_EVENT_RECORD) ([]byte, error) {
	if event.bKeyDown == 0 {
		// Key release events are typically ignored
		return nil, nil
	}

	// Handle control characters
	if event.UnicodeChar != 0 && event.UnicodeChar < 0x20 {
		// Check for Ctrl+key combinations
		ctrl := (event.dwControlKeyState & (LEFT_CTRL_PRESSED | RIGHT_CTRL_PRESSED)) != 0
		if ctrl {
			// Ctrl+letter produces ASCII 1-26
			return []byte{byte(event.UnicodeChar)}, nil
		}
		// Other control characters pass through
		return []byte{byte(event.UnicodeChar)}, nil
	}

	// Handle printable characters
	if event.UnicodeChar >= 0x20 {
		return []byte{byte(event.UnicodeChar)}, nil
	}

	// Handle special keys via virtual key code
	keyCode, modifier, useTildeFormat := VirtualKeyCodeToCSI(event.wVirtualKeyCode, event.dwControlKeyState)
	if keyCode < 0 {
		return nil, fmt.Errorf("unhandled virtual key code: 0x%02X", event.wVirtualKeyCode)
	}

	return BuildCSISequence(keyCode, modifier, useTildeFormat), nil
}

// IsCSISequenceStart checks if the data starts with a CSI sequence.
func IsCSISequenceStart(data []byte) bool {
	return len(data) >= 2 && data[0] == 0x1B && data[1] == '['
}

// ParseCSISequence parses a CSI sequence from data.
// Returns (prefix, params, intermediate, final, consumed, error)
func ParseCSISequence(data []byte) (prefix string, params string, intermediate string, final byte, consumed int, err error) {
	if !IsCSISequenceStart(data) {
		return "", "", "", 0, 0, fmt.Errorf("not a CSI sequence")
	}

	consumed = 2 // ESC [
	data = data[2:]

	i := 0
	// Parse parameter bytes (0x30-0x3F)
	for i < len(data) && data[i] >= 0x30 && data[i] <= 0x3F {
		params += string(data[i])
		i++
	}

	// Parse intermediate bytes (0x20-0x2F)
	for i < len(data) && data[i] >= 0x20 && data[i] <= 0x2F {
		intermediate += string(data[i])
		i++
	}

	// Parse final byte (0x40-0x7E)
	if i < len(data) && data[i] >= 0x40 && data[i] <= 0x7E {
		final = data[i]
		consumed += i + 1
		return "CSI", params, intermediate, final, consumed, nil
	}

	return "", "", "", 0, 0, fmt.Errorf("incomplete CSI sequence")
}
