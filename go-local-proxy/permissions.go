package main

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

// ErrConfirmBashMaxSubcommands 子段数超过 bash_max_subcommands 且未带 confirmed，需前端确认后重试。
var ErrConfirmBashMaxSubcommands = errors.New("confirm_bash_max_subcommands")

type permissionsFile struct {
	Permissions struct {
		Allow                  []string `json:"allow"`
		Deny                   []string `json:"deny"`
		WorkspaceRoot          string   `json:"workspace_root"`
		BashMaxSubcommands     int      `json:"bash_max_subcommands"`
		NetworkAllowedDomains  []string `json:"network_allowed_domains"`
		AutoConfirmTrusted     bool     `json:"auto_confirm_trusted"`
	} `json:"permissions"`
}

func agentTerminalPermissionsPath() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, ".config", "agent-terminal", "permissions.json"), nil
}

func normalizePermissionPattern(p string) string {
	p = strings.TrimSpace(p)
	low := strings.ToLower(p)
	if strings.HasPrefix(low, "bash(") && strings.HasSuffix(p, ")") {
		p = strings.TrimSpace(p[5 : len(p)-1])
	}
	return p
}

func globPatternToRegexp(pattern string) (*regexp.Regexp, error) {
	pattern = normalizePermissionPattern(pattern)
	if pattern == "" {
		return nil, nil
	}
	var b strings.Builder
	b.WriteString("^")
	for _, r := range pattern {
		switch r {
		case '*':
			b.WriteString(".*")
		case '?':
			b.WriteString(".")
		default:
			if strings.ContainsRune(".^$+()[]{}|\\", r) {
				b.WriteRune('\\')
			}
			b.WriteRune(r)
		}
	}
	b.WriteString("$")
	return regexp.Compile(b.String())
}

// checkAgentTerminalWorkspaceCwd 仅校验 cwd 是否在 workspace_root 内（供纯 cd 更新会话前使用）。
func checkAgentTerminalWorkspaceCwd(cwd string) error {
	p, err := agentTerminalPermissionsPath()
	if err != nil || p == "" {
		return nil
	}
	data, err := os.ReadFile(p)
	if err != nil {
		return nil
	}
	var f permissionsFile
	if json.Unmarshal(data, &f) != nil {
		return nil
	}
	if !cwdAllowedByWorkspaceRoot(cwd, f.Permissions.WorkspaceRoot) {
		return errors.New("cwd 不在 permissions.workspace_root 允许范围内")
	}
	return nil
}

func cwdAllowedByWorkspaceRoot(cwd, workspaceRoot string) bool {
	wr := strings.TrimSpace(workspaceRoot)
	if wr == "" {
		return true
	}
	c := strings.TrimSpace(cwd)
	if c == "" {
		return true
	}
	wc, e1 := filepath.Abs(c)
	wrAbs, e2 := filepath.Abs(wr)
	if e1 != nil || e2 != nil {
		return true
	}
	sep := string(os.PathSeparator)
	wc = filepath.Clean(wc) + sep
	wrAbs = filepath.Clean(wrAbs) + sep
	return strings.HasPrefix(strings.ToLower(wc), strings.ToLower(wrAbs))
}

// countShellSegments 管道/分号/与或链粗算段数（与文档 bash_max_subcommands 对齐的近似）。
func countShellSegments(line string) int {
	line = strings.TrimSpace(line)
	if line == "" {
		return 0
	}
	s := line
	s = strings.ReplaceAll(s, "&&", "\x01")
	s = strings.ReplaceAll(s, "||", "\x01")
	n := 1
	for _, ch := range s {
		if ch == '|' || ch == ';' || ch == '\x01' {
			n++
		}
	}
	return n
}

var reURLHost = regexp.MustCompile(`(?i)https?://([a-zA-Z0-9][-a-zA-Z0-9.]*[a-zA-Z0-9]|[a-zA-Z0-9])`)

func domainAllowed(host string, allowed []string) bool {
	h := strings.ToLower(strings.TrimSpace(host))
	if h == "" {
		return false
	}
	for _, a := range allowed {
		d := strings.ToLower(strings.TrimSpace(a))
		if d == "" {
			continue
		}
		if h == d || strings.HasSuffix(h, "."+d) {
			return true
		}
	}
	return false
}

var reNetToolLead = regexp.MustCompile(`(?i)\b(curl|wget|fetch|Invoke-WebRequest|iwr)\b`)

// 无 scheme 时，在 curl/wget 之后取首个「域名 + /path 或行尾」片段（跳过行首若干 - 开关参数）。
var reBareHostAfterCurl = regexp.MustCompile(`(?i)(?:^|\s)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9]){1,}))(?:/|\?|#|:\d{1,5}|$)`)

func firstBareHostnameAfterNetTool(line string) string {
	trim := strings.TrimSpace(line)
	loc := reNetToolLead.FindStringIndex(trim)
	if loc == nil {
		return ""
	}
	tail := strings.TrimSpace(trim[loc[1]:])
	fields := strings.Fields(tail)
	argvExtra := map[string]struct{}{
		"-X": {}, "--request": {}, "-d": {}, "--data": {}, "--data-binary": {},
		"-H": {}, "--header": {}, "-o": {}, "--output": {}, "-T": {}, "--upload-file": {},
	}
	i := 0
	for i < len(fields) && strings.HasPrefix(fields[i], "-") {
		fl := fields[i]
		base := strings.SplitN(fl, "=", 2)[0]
		i++
		if _, ok := argvExtra[base]; ok {
			if i >= len(fields) {
				return ""
			}
			i++
		}
	}
	if i >= len(fields) {
		return ""
	}
	remainder := strings.Join(fields[i:], " ")
	if m := reBareHostAfterCurl.FindStringSubmatch(remainder); len(m) > 1 && m[1] != "" {
		return m[1]
	}
	return ""
}

// 若配置了 network_allowed_domains 且命令像 curl/wget 等：校验 URL 内域名，或（无 scheme 时）首个类域名参数。
func checkNetworkDomains(cmdline string, allowed []string) error {
	if len(allowed) == 0 {
		return nil
	}
	line := strings.TrimSpace(cmdline)
	if line == "" {
		return nil
	}
	if !reNetToolLead.MatchString(line) {
		return nil
	}
	low := strings.ToLower(line)
	hasHTTP := strings.Contains(low, "http://") || strings.Contains(low, "https://")
	if hasHTTP {
		for _, m := range reURLHost.FindAllStringSubmatch(line, -1) {
			if len(m) < 2 {
				continue
			}
			if !domainAllowed(m[1], allowed) {
				return errors.New("URL 域名不在 permissions.network_allowed_domains")
			}
		}
		return nil
	}
	host := firstBareHostnameAfterNetTool(line)
	if host == "" {
		return nil
	}
	if !domainAllowed(host, allowed) {
		return errors.New("URL 域名不在 permissions.network_allowed_domains")
	}
	return nil
}

func commandMatchesAnyAllow(line string, allow []string) bool {
	for _, a := range allow {
		re, err := globPatternToRegexp(a)
		if err != nil || re == nil {
			continue
		}
		if re.MatchString(line) {
			return true
		}
	}
	return false
}

// checkAgentTerminalPermissions 读取 ~/.config/agent-terminal/permissions.json（可选）。
// 无文件或解析失败则不限制。deny 优先；若 allow 非空则命令须命中至少一条 allow。
// confirmed=true 时跳过 bash_max_subcommands 超限检查（用户已二次确认，仍受 deny 等约束）。
// auto_confirm_trusted=true 且命令已命中 allow 时，跳过 bash 段数超限的 confirm（仍受 deny/workspace/网络约束）。
func checkAgentTerminalPermissions(cmdline, cwd string, confirmed bool) error {
	p, err := agentTerminalPermissionsPath()
	if err != nil || p == "" {
		return nil
	}
	data, err := os.ReadFile(p)
	if err != nil {
		return nil
	}
	var f permissionsFile
	if json.Unmarshal(data, &f) != nil {
		return nil
	}
	if !cwdAllowedByWorkspaceRoot(cwd, f.Permissions.WorkspaceRoot) {
		return errors.New("cwd 不在 permissions.workspace_root 允许范围内")
	}
	line := strings.TrimSpace(cmdline)
	maxSeg := f.Permissions.BashMaxSubcommands
	skipBashMaxTrust := f.Permissions.AutoConfirmTrusted &&
		len(f.Permissions.Allow) > 0 &&
		commandMatchesAnyAllow(line, f.Permissions.Allow)
	if maxSeg > 0 && !confirmed && !skipBashMaxTrust {
		if n := countShellSegments(line); n > maxSeg {
			return ErrConfirmBashMaxSubcommands
		}
	}
	if err := checkNetworkDomains(line, f.Permissions.NetworkAllowedDomains); err != nil {
		return err
	}
	for _, d := range f.Permissions.Deny {
		re, err := globPatternToRegexp(d)
		if err != nil || re == nil {
			continue
		}
		if re.MatchString(line) {
			return errors.New("命令命中 permissions.deny")
		}
	}
	if len(f.Permissions.Allow) == 0 {
		return nil
	}
	for _, a := range f.Permissions.Allow {
		re, err := globPatternToRegexp(a)
		if err != nil || re == nil {
			continue
		}
		if re.MatchString(line) {
			return nil
		}
	}
	return errors.New("命令未匹配 permissions.allow")
}
