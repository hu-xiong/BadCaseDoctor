package main

import (
	"path/filepath"
	"regexp"
	"strings"
)

var (
	rePureCdLine   = regexp.MustCompile(`(?i)^cd\s*$`)
	rePureCdWithArg = regexp.MustCompile(`(?i)^cd\s+(.+)\s*$`)
)

func tryParsePureCdCommand(cmdline string) (arg string, ok bool) {
	s := strings.TrimSpace(cmdline)
	if s == "" {
		return "", false
	}
	if strings.ContainsAny(s, "&|;") || strings.Contains(s, "\n") {
		return "", false
	}
	if rePureCdLine.MatchString(s) {
		return "", true
	}
	if m := rePureCdWithArg.FindStringSubmatch(s); m != nil {
		return strings.TrimSpace(m[1]), true
	}
	return "", false
}

func sessionResolveCd(base, arg string) string {
	arg = strings.TrimSpace(arg)
	if len(arg) >= 2 && ((arg[0] == '"' && arg[len(arg)-1] == '"') || (arg[0] == '\'' && arg[len(arg)-1] == '\'')) {
		arg = strings.TrimSpace(arg[1 : len(arg)-1])
	}
	base = strings.TrimSpace(base)
	if arg == "" || arg == "." {
		return base
	}
	if filepath.IsAbs(arg) {
		return filepath.Clean(arg)
	}
	if base == "" {
		return filepath.Clean(arg)
	}
	return filepath.Clean(filepath.Join(base, arg))
}
