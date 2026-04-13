//go:build !windows

package main

// transformPtyConsoleOutput 非 Windows：直通（真 PTY 多为 UTF-8）。
func transformPtyConsoleOutput(carry *[]byte, chunk []byte) []byte {
	_ = carry
	if len(chunk) == 0 {
		return nil
	}
	return chunk
}
