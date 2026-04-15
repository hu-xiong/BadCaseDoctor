//go:build windows
// +build windows

// Package conpty provides Windows ConPTY support with win32-input-mode protocol.
//
// This file handles INPUT_RECORD parsing for win32-input-mode output processing.
// For stdin input transformation (DEL→BS), see conpty_stdin_transform.go.
package conpty

import (
	"fmt"
)

// VK to scan code mapping helper - most common mappings
var vkToScanCode = map[uint16]uint16{
	VK_BACK:     0x0E, // Backspace
	VK_TAB:      0x0F, // Tab
	VK_SHIFT:    0x2A, // Left Shift
	VK_CONTROL:  0x1D, // Left Control
	VK_MENU:     0x38, // Left Alt
	VK_ESCAPE:   0x01, // Escape
	VK_SPACE:    0x39, // Space
	VK_END:      0x4F, // End
	VK_HOME:     0x47, // Home
	VK_LEFT:     0x4B, // Left Arrow
	VK_UP:       0x48, // Up Arrow
	VK_RIGHT:    0x4D, // Right Arrow
	VK_DOWN:     0x50, // Down Arrow
	VK_INSERT:   0x52, // Insert
	VK_DELETE:   0x53, // Delete
	VK_PRIOR:    0x49, // Page Up
	VK_NEXT:     0x51, // Page Down
	VK_F1:       0x3B,
	VK_F2:       0x3C,
	VK_F3:       0x3D,
	VK_F4:       0x3E,
	VK_F5:       0x3F,
	VK_F6:       0x40,
	VK_F7:       0x41,
	VK_F8:       0x42,
	VK_F9:       0x43,
	VK_F10:      0x44,
	VK_F11:      0x57,
	VK_F12:      0x58,
}

// CSI key code to Virtual Key Code mapping for win32-input-mode input processing
// CSI ~ format: ESC [ <num> [;<modifier>] ~
// Reference: xterm.js win32-input-mode CSI codes
// F1-F4 use SS3 format (ESC O P/Q/R/S), F5-F12 use CSI ~ format
var csiTildeToVK = map[int]uint16{
	1:  VK_HOME,       // Home
	2:  VK_INSERT,     // Insert
	3:  VK_DELETE,     // Delete
	4:  VK_END,        // End
	5:  VK_PRIOR,      // Page Up
	6:  VK_NEXT,       // Page Down
	9:  VK_TAB,        // Tab
	11: VK_F1,         // F1
	12: VK_F2,         // F2
	13: VK_F3,         // F3
	14: VK_F4,         // F4
	15: VK_F5,         // F5
	17: VK_F6,         // F6
	18: VK_F7,         // F7
	19: VK_F8,         // F8
	20: VK_F9,         // F9
	21: VK_F10,        // F10
	23: VK_F11,        // F11
	24: VK_F12,        // F12
	127: VK_BACK,      // Backspace
}

// CSI letter key codes to Virtual Key Code mapping
// CSI letter format: ESC [ <num> [;<modifier>] <letter>
var csiLetterToVK = map[byte]uint16{
	'A': VK_UP,    // Up Arrow
	'B': VK_DOWN,  // Down Arrow
	'C': VK_RIGHT, // Right Arrow
	'D': VK_LEFT,  // Left Arrow
	'H': VK_HOME,  // Home
	'F': VK_END,   // End
}

// Modifier value to control key state mapping
var modifierToCtrlState = map[int]uint32{
	CSIModNone:          0,
	CSIModShift:        LEFT_SHIFT_PRESSED | RIGHT_SHIFT_PRESSED,
	CSIModAlt:          LEFT_ALT_PRESSED | RIGHT_ALT_PRESSED,
	CSIModShiftAlt:     LEFT_SHIFT_PRESSED | RIGHT_SHIFT_PRESSED | LEFT_ALT_PRESSED | RIGHT_ALT_PRESSED,
	CSIModCtrl:         LEFT_CTRL_PRESSED | RIGHT_CTRL_PRESSED,
	CSIModShiftCtrl:    LEFT_SHIFT_PRESSED | RIGHT_SHIFT_PRESSED | LEFT_CTRL_PRESSED | RIGHT_CTRL_PRESSED,
	CSIModAltCtrl:      LEFT_ALT_PRESSED | RIGHT_ALT_PRESSED | LEFT_CTRL_PRESSED | RIGHT_CTRL_PRESSED,
	CSIModShiftAltCtrl: LEFT_SHIFT_PRESSED | RIGHT_SHIFT_PRESSED | LEFT_ALT_PRESSED | RIGHT_ALT_PRESSED | LEFT_CTRL_PRESSED | RIGHT_CTRL_PRESSED,
}

// CSIParamToModifier converts CSI modifier parameter to control key state
func CSIParamToModifier(modifier int) uint32 {
	if state, ok := modifierToCtrlState[modifier]; ok {
		return state
	}
	return 0
}

// CSIParamToVirtualKey converts a CSI parameter to virtual key code
// Supports both ~ format (e.g., 3~ for Delete) and letter format (e.g., D for Left)
func CSIParamToVirtualKey(param int, final byte) (vk uint16, ok bool) {
	// Check tilde format first (param is the key number)
	if vk, ok := csiTildeToVK[param]; ok {
		return vk, true
	}

	// Check letter format (final byte is the key)
	if vk, ok := csiLetterToVK[final]; ok {
		return vk, true
	}

	return 0, false
}

// NewKeyEventRecord creates a KEY_EVENT_RECORD for a virtual key with modifiers
func NewKeyEventRecord(vk uint16, ctrlState uint32, keyDown bool) KEY_EVENT_RECORD {
	scanCode := vkToScanCode[vk]
	if scanCode == 0 {
		// Default scan code calculation if not in table
		scanCode = uint16(vk & 0xFF)
	}

	event := KEY_EVENT_RECORD{
		bKeyDown:          1,
		wRepeatCount:      1,
		wVirtualKeyCode:   vk,
		wVirtualScanCode:  scanCode,
		UnicodeChar:       0,
		dwControlKeyState: ctrlState | ENHANCED_KEY,
	}
	if !keyDown {
		event.bKeyDown = 0
	}
	return event
}

// NewKeyEventRecordWithChar creates a KEY_EVENT_RECORD for a character
func NewKeyEventRecordWithChar(ch uint16, ctrlState uint32, keyDown bool) KEY_EVENT_RECORD {
	event := KEY_EVENT_RECORD{
		bKeyDown:          1,
		wRepeatCount:      1,
		wVirtualKeyCode:   0,
		wVirtualScanCode:  0,
		UnicodeChar:       ch,
		dwControlKeyState: ctrlState,
	}
	if !keyDown {
		event.bKeyDown = 0
	}
	return event
}

// ToINPUTRecord converts a KEY_EVENT_RECORD to an INPUT_RECORD
func (k *KEY_EVENT_RECORD) ToINPUTRecord() INPUT_RECORD {
	rec := INPUT_RECORD{
		EventType: KEY_EVENT,
	}
	// Pack the event data into the 16-byte array
	rec.Event[0] = byte(k.bKeyDown)
	rec.Event[1] = byte(k.bKeyDown >> 8)
	rec.Event[2] = byte(k.wRepeatCount)
	rec.Event[3] = byte(k.wRepeatCount >> 8)
	rec.Event[4] = byte(k.wVirtualKeyCode)
	rec.Event[5] = byte(k.wVirtualKeyCode >> 8)
	rec.Event[6] = byte(k.wVirtualScanCode)
	rec.Event[7] = byte(k.wVirtualScanCode >> 8)
	rec.Event[8] = byte(k.UnicodeChar)
	rec.Event[9] = byte(k.UnicodeChar >> 8)
	rec.Event[10] = byte(k.dwControlKeyState)
	rec.Event[11] = byte(k.dwControlKeyState >> 8)
	rec.Event[12] = byte(k.dwControlKeyState >> 16)
	rec.Event[13] = byte(k.dwControlKeyState >> 24)
	// Event[14] and Event[15] are padding
	return rec
}

// Windows Console API constants for INPUT_RECORD parsing
const (
	KEY_EVENT                = 0x0001
	WINDOW_BUFFER_SIZE_EVENT = 0x0004
)

// INPUT_RECORD structure size in bytes
// https://docs.microsoft.com/en-us/windows/console/input-record-str
const INPUT_RECORD_SIZE = 20 // 2 (EventType) + 16 (Event data) + 2 padding

// INPUT_RECORD represents a Windows console input record.
type INPUT_RECORD struct {
	EventType uint16
	Event     [16]byte // KEY_EVENT_RECORD or other event data
}

// KEY_EVENT_RECORD - Key event record structure
// https://docs.microsoft.com/en-us/windows/console/key-event-record-str
type KEY_EVENT_RECORD struct {
	bKeyDown          int32   // 1 if key pressed, 0 if released
	wRepeatCount      uint16  // Number of times key pressed
	wVirtualKeyCode   uint16  // Virtual key code
	wVirtualScanCode  uint16  // Virtual scan code
	UnicodeChar       uint16  // Unicode character
	dwControlKeyState uint32  // Control key state
}

// Control key state flags
const (
	CAPSLOCK_ON         = 0x0080
	ENHANCED_KEY        = 0x0100
	LEFT_ALT_PRESSED    = 0x0200
	LEFT_CTRL_PRESSED   = 0x0400
	LEFT_SHIFT_PRESSED  = 0x0800
	RIGHT_ALT_PRESSED   = 0x1000
	RIGHT_CTRL_PRESSED  = 0x2000
	RIGHT_SHIFT_PRESSED = 0x4000
	SCROLLLOCK_ON       = 0x8000
)

// ParseInputRecord parses an INPUT_RECORD from a byte buffer.
// Returns the parsed record and the number of bytes consumed.
func ParseInputRecord(data []byte) (*INPUT_RECORD, int, error) {
	if len(data) < INPUT_RECORD_SIZE {
		return nil, 0, fmt.Errorf("buffer too small for INPUT_RECORD: need %d, got %d", INPUT_RECORD_SIZE, len(data))
	}

	record := &INPUT_RECORD{}
	record.EventType = uint16(data[0]) | (uint16(data[1]) << 8)
	copy(record.Event[:], data[2:18])

	return record, INPUT_RECORD_SIZE, nil
}

// ExtractKeyEvent extracts a KEY_EVENT_RECORD from an INPUT_RECORD.
func ExtractKeyEvent(record *INPUT_RECORD) (*KEY_EVENT_RECORD, error) {
	if record.EventType != KEY_EVENT {
		return nil, fmt.Errorf("not a KEY_EVENT, got type %d", record.EventType)
	}

	event := &KEY_EVENT_RECORD{}
	// Unpack the event data from the 16-byte array
	event.bKeyDown = int32(record.Event[0]) | (int32(record.Event[1]) << 8)
	event.wRepeatCount = uint16(record.Event[2]) | (uint16(record.Event[3]) << 8)
	event.wVirtualKeyCode = uint16(record.Event[4]) | (uint16(record.Event[5]) << 8)
	event.wVirtualScanCode = uint16(record.Event[6]) | (uint16(record.Event[7]) << 8)
	event.UnicodeChar = uint16(record.Event[8]) | (uint16(record.Event[9]) << 8)
	event.dwControlKeyState = uint32(record.Event[10]) |
		(uint32(record.Event[11]) << 8) |
		(uint32(record.Event[12]) << 16) |
		(uint32(record.Event[13]) << 24)

	return event, nil
}

// ParseModifierState extracts modifier information from control key state.
func ParseModifierState(ctrlKeyState uint32) int {
	shift := (ctrlKeyState & (LEFT_SHIFT_PRESSED | RIGHT_SHIFT_PRESSED)) != 0
	alt := (ctrlKeyState & (LEFT_ALT_PRESSED | RIGHT_ALT_PRESSED)) != 0
	ctrl := (ctrlKeyState & (LEFT_CTRL_PRESSED | RIGHT_CTRL_PRESSED)) != 0

	switch {
	case shift && alt:
		return 4
	case shift && ctrl:
		return 6
	case alt && ctrl:
		return 7
	case shift:
		return 2
	case alt:
		return 3
	case ctrl:
		return 5
	default:
		return 0
	}
}
