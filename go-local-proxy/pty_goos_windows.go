//go:build windows

package main

func newTermStartedWindowsPty() *windowsPtyOut {
	return &windowsPtyOut{Backend: "conpty"}
}
