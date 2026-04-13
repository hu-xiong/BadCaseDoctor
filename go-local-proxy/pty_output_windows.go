//go:build windows

package main

import (
	"unicode/utf16"
)

// Windows 下管道连 powershell.exe 时，标准输出常为 UTF-16 LE；浏览器 xterm 按 UTF-8 解码会乱码（如 Directory 行前出现杂字符）。
// *carry 保存未凑成一对的字节（跨 Read 边界）。

func transformPtyConsoleOutput(carry *[]byte, chunk []byte) []byte {
	data := make([]byte, 0, len(*carry)+len(chunk))
	data = append(data, *carry...)
	*carry = nil
	data = append(data, chunk...)
	if len(data) == 0 {
		return nil
	}
	if len(data) >= 2 && data[0] == 0xFF && data[1] == 0xFE {
		data = data[2:]
	}
	if !looksLikeUTF16LEPowerShellOutput(data) {
		return data
	}
	if len(data)%2 == 1 {
		*carry = append(*carry, data[len(data)-1])
		data = data[:len(data)-1]
	}
	if len(data) == 0 {
		return nil
	}
	return utf16LEBytesToUTF8(data)
}

func looksLikeUTF16LEPowerShellOutput(b []byte) bool {
	if len(b) < 4 {
		return false
	}
	lim := len(b)
	if lim%2 == 1 {
		lim--
	}
	asciiPairs := 0
	for i := 0; i+1 < lim && i < 48; i += 2 {
		lo, hi := b[i], b[i+1]
		if hi == 0 && lo >= 32 && lo < 127 {
			asciiPairs++
		}
	}
	return asciiPairs >= 3
}

func utf16LEBytesToUTF8(b []byte) []byte {
	if len(b)%2 != 0 {
		return b
	}
	u := make([]uint16, len(b)/2)
	for i := range u {
		u[i] = uint16(b[2*i]) | uint16(b[2*i+1])<<8
	}
	return []byte(string(utf16.Decode(u)))
}
