// 出站隧道：本机代理 → 云端桥服务（默认 wss /api/local-proxy/tunnel）。
//
// 用途：云端 Agent / midscene 经「反连隧道 + 云端 CDP 网关」操作本机 Chrome（内网页面云端不可达）。
// 安全边界：
//   - 仅转发「本代理自己拉起的 Chrome」DevTools 的 browser-level CDP 流（端口白名单校验）；
//   - 不做任意 host/port 转发；未知 op 一律忽略；
//   - 非环回目标强制 wss 且严格校验证书（BADCASE_TUNNEL_CA 可注入企业根证书；--tunnel-insecure 仅环回调试）。
//
// 配置来源（优先级 命令行 > 环境变量 > 持久化文件）：
//   --tunnel-url / --tunnel-token / --tunnel-insecure
//   BADCASE_TUNNEL_URL / BADCASE_TUNNEL_TOKEN / BADCASE_TUNNEL_CA / BADCASE_TUNNEL_INSECURE
//   持久化文件：UserConfigDir/badcase-local-proxy/tunnel.json（自启无参实例读取；
//   运行中实例每 30s 重读，token 更新后自动重建连接）。
//
// 协议见 docs/技术设计_本机浏览器CDP通道.md §5：
//   控制帧 text JSON（hello/hello_ack/cdp_open/cdp_open_ack/cdp_close/error）
//   数据帧 binary = [4B sid 大端][CDP ws 消息字节]
package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

const (
	tunnelProtocolVersion = "1"
	tunnelReadWait        = 90 * time.Second  // 云端 heartbeat=30s，×3 容错
	tunnelHelloWait       = 15 * time.Second  // 等待 hello_ack
	tunnelMinBackoff      = 1 * time.Second
	tunnelMaxBackoff      = 60 * time.Second
	tunnelConfigPollSec   = 30 // 配置重读间隔
	tunnelMaxFrame        = 8 * 1024 * 1024
)

var errTunnelAuth = errors.New("tunnel auth failed")

// ---------------------------------------------------------------- 配置

type tunnelConfig struct {
	URL      string
	Token    string
	CAFile   string
	Insecure bool
}

type persistedTunnelConfig struct {
	URL      string `json:"url"`
	Token    string `json:"token"`
	CAFile   string `json:"ca_file,omitempty"`
	Insecure bool   `json:"insecure,omitempty"`
}

func tunnelEnvTruthy(k string) bool {
	v := strings.ToLower(strings.TrimSpace(os.Getenv(k)))
	return v == "1" || v == "true" || v == "yes" || v == "on"
}

func tunnelConfigFilePath() (string, error) {
	dir, err := os.UserConfigDir()
	if err != nil || strings.TrimSpace(dir) == "" {
		dir = os.Getenv("TEMP")
		if strings.TrimSpace(dir) == "" {
			return "", errors.New("cannot resolve user config dir")
		}
	}
	return filepath.Join(dir, "badcase-local-proxy", "tunnel.json"), nil
}

// persistTunnelConfig 把命令行/环境变量给出的配置落盘，供自启无参实例与运行中实例重读。
func persistTunnelConfig(cfg tunnelConfig) error {
	path, err := tunnelConfigFilePath()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	row := persistedTunnelConfig{
		URL:      strings.TrimSpace(cfg.URL),
		Token:    strings.TrimSpace(cfg.Token),
		CAFile:   strings.TrimSpace(cfg.CAFile),
		Insecure: cfg.Insecure,
	}
	raw, err := json.MarshalIndent(row, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, raw, 0o600)
}

// loadTunnelConfig 读取持久化文件并以环境变量覆盖（env 视为部署级配置）。
func loadTunnelConfig() tunnelConfig {
	cfg := tunnelConfig{
		URL:      strings.TrimSpace(os.Getenv("BADCASE_TUNNEL_URL")),
		Token:    strings.TrimSpace(os.Getenv("BADCASE_TUNNEL_TOKEN")),
		CAFile:   strings.TrimSpace(os.Getenv("BADCASE_TUNNEL_CA")),
		Insecure: tunnelEnvTruthy("BADCASE_TUNNEL_INSECURE"),
	}
	path, err := tunnelConfigFilePath()
	if err == nil {
		if raw, err := os.ReadFile(path); err == nil {
			var row persistedTunnelConfig
			if json.Unmarshal(raw, &row) == nil {
				if cfg.URL == "" {
					cfg.URL = strings.TrimSpace(row.URL)
				}
				if cfg.Token == "" {
					cfg.Token = strings.TrimSpace(row.Token)
				}
				if cfg.CAFile == "" {
					cfg.CAFile = strings.TrimSpace(row.CAFile)
				}
				if !cfg.Insecure {
					cfg.Insecure = row.Insecure
				}
			}
		}
	}
	return cfg
}

// parseTunnelArgs 解析命令行隧道参数（与 env 合并）；ok 表示最终有可用 URL。
func parseTunnelArgs(args []string) (tunnelConfig, bool) {
	cfg := tunnelConfig{}
	for i := 0; i < len(args); i++ {
		a := strings.ToLower(strings.TrimSpace(args[i]))
		switch a {
		case "--tunnel-url":
			if i+1 < len(args) {
				cfg.URL = strings.TrimSpace(args[i+1])
				i++
			}
		case "--tunnel-token":
			if i+1 < len(args) {
				cfg.Token = strings.TrimSpace(args[i+1])
				i++
			}
		case "--tunnel-insecure":
			cfg.Insecure = true
		}
	}
	if cfg.URL == "" {
		cfg.URL = strings.TrimSpace(os.Getenv("BADCASE_TUNNEL_URL"))
	}
	if cfg.Token == "" {
		cfg.Token = strings.TrimSpace(os.Getenv("BADCASE_TUNNEL_TOKEN"))
	}
	if cfg.CAFile == "" {
		cfg.CAFile = strings.TrimSpace(os.Getenv("BADCASE_TUNNEL_CA"))
	}
	if !cfg.Insecure {
		cfg.Insecure = tunnelEnvTruthy("BADCASE_TUNNEL_INSECURE")
	}
	return cfg, strings.TrimSpace(cfg.URL) != ""
}

func normalizeTunnelConfig(cfg tunnelConfig) (tunnelConfig, error) {
	raw := strings.TrimSpace(cfg.URL)
	if raw == "" {
		return cfg, errors.New("tunnel url empty")
	}
	u, err := url.Parse(raw)
	if err != nil {
		return cfg, fmt.Errorf("invalid tunnel url: %w", err)
	}
	scheme := strings.ToLower(u.Scheme)
	if scheme != "ws" && scheme != "wss" {
		return cfg, fmt.Errorf("unsupported scheme %q (ws/wss only)", u.Scheme)
	}
	host := strings.ToLower(u.Hostname())
	loopback := host == "127.0.0.1" || host == "localhost" || host == "::1"
	if !loopback {
		if scheme != "wss" {
			return cfg, errors.New("非环回隧道必须使用 wss（拒绝明文 ws）")
		}
		if cfg.Insecure {
			return cfg, errors.New("--tunnel-insecure 仅允许环回开发，非环回目标拒绝跳过证书校验")
		}
	}
	if strings.TrimSpace(cfg.Token) == "" {
		return cfg, errors.New("tunnel token empty")
	}
	cfg.URL = raw
	return cfg, nil
}

func buildTunnelTLSConfig(cfg tunnelConfig) *tls.Config {
	if cfg.Insecure {
		return &tls.Config{InsecureSkipVerify: true} // 仅环回调试（normalize 已限制）
	}
	tlsCfg := &tls.Config{}
	caFile := strings.TrimSpace(cfg.CAFile)
	if caFile == "" {
		return tlsCfg
	}
	pool, err := x509.SystemCertPool()
	if err != nil || pool == nil {
		pool = x509.NewCertPool()
	}
	pem, err := os.ReadFile(caFile)
	if err != nil {
		log.Printf("[tunnel] 读取 BADCASE_TUNNEL_CA 失败: %v", err)
		return tlsCfg
	}
	if !pool.AppendCertsFromPEM(pem) {
		log.Printf("[tunnel] BADCASE_TUNNEL_CA 未包含有效证书: %s", caFile)
		return tlsCfg
	}
	tlsCfg.RootCAs = pool
	return tlsCfg
}

// ---------------------------------------------------------------- 客户端

type tunnelStream struct {
	sid uint32
	ws  *websocket.Conn
}

type tunnelClient struct {
	mu      sync.Mutex
	conn    *websocket.Conn
	streams map[uint32]*tunnelStream
	writeMu sync.Mutex
	active  bool // 是否已计入 idle 活跃（避免重复 enter/leave）
	cancel  context.CancelFunc
}

var globalTunnel = &tunnelClient{streams: make(map[uint32]*tunnelStream)}

func (t *tunnelClient) getConn() *websocket.Conn {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.conn
}

func (t *tunnelClient) setConn(c *websocket.Conn) {
	t.mu.Lock()
	t.conn = c
	t.mu.Unlock()
}

func (t *tunnelClient) setActive(v bool) {
	t.mu.Lock()
	changed := t.active != v
	t.active = v
	t.mu.Unlock()
	if !changed {
		return
	}
	if v {
		idleConnEnter()
	} else {
		idleConnLeave()
	}
}

func (t *tunnelClient) getStream(sid uint32) *tunnelStream {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.streams[sid]
}

func (t *tunnelClient) putStream(st *tunnelStream) {
	t.mu.Lock()
	t.streams[st.sid] = st
	t.mu.Unlock()
}

func (t *tunnelClient) removeStream(sid uint32) {
	t.mu.Lock()
	delete(t.streams, sid)
	t.mu.Unlock()
}

func (t *tunnelClient) closeAllStreams() {
	t.mu.Lock()
	all := t.streams
	t.streams = make(map[uint32]*tunnelStream)
	t.mu.Unlock()
	for _, st := range all {
		_ = st.ws.Close()
	}
}

func (t *tunnelClient) writeControl(v interface{}) error {
	raw, err := json.Marshal(v)
	if err != nil {
		return err
	}
	c := t.getConn()
	if c == nil {
		return errors.New("tunnel not connected")
	}
	t.writeMu.Lock()
	defer t.writeMu.Unlock()
	_ = c.SetWriteDeadline(time.Now().Add(15 * time.Second))
	return c.WriteMessage(websocket.TextMessage, raw)
}

func (t *tunnelClient) writeData(sid uint32, payload []byte) error {
	buf := make([]byte, 4+len(payload))
	binary.BigEndian.PutUint32(buf[:4], sid)
	copy(buf[4:], payload)
	c := t.getConn()
	if c == nil {
		return errors.New("tunnel not connected")
	}
	t.writeMu.Lock()
	defer t.writeMu.Unlock()
	_ = c.SetWriteDeadline(time.Now().Add(30 * time.Second))
	return c.WriteMessage(websocket.BinaryMessage, buf)
}

// reconfigure 启动（或替换）隧道连接循环：配置变化时重建。
func (t *tunnelClient) reconfigure(cfg tunnelConfig) {
	t.mu.Lock()
	if t.cancel != nil {
		t.cancel()
	}
	ctx, cancel := context.WithCancel(context.Background())
	t.cancel = cancel
	t.mu.Unlock()
	go t.runLoop(ctx, cfg)
}

func (t *tunnelClient) runLoop(ctx context.Context, cfg tunnelConfig) {
	backoff := tunnelMinBackoff
	lastAuthLog := time.Time{}
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}
		err := t.connectOnce(ctx, cfg)
		if ctx.Err() != nil {
			return
		}
		if errors.Is(err, errTunnelAuth) {
			// token 失效：不狂重试；配置 watcher 会在 token 更新后重建
			if time.Since(lastAuthLog) > time.Minute {
				log.Printf("[tunnel] 认证失败（token 过期或无效）：等待配置更新后重连")
				lastAuthLog = time.Now()
			}
			select {
			case <-ctx.Done():
				return
			case <-time.After(10 * time.Second):
			}
			continue
		}
		log.Printf("[tunnel] 连接断开: %v；%s 后重连", err, backoff)
		select {
		case <-ctx.Done():
			return
		case <-time.After(backoff):
		}
		if backoff < tunnelMaxBackoff {
			backoff *= 2
			if backoff > tunnelMaxBackoff {
				backoff = tunnelMaxBackoff
			}
		}
	}
}

func (t *tunnelClient) connectOnce(ctx context.Context, cfg tunnelConfig) error {
	dialer := websocket.Dialer{
		HandshakeTimeout: 15 * time.Second,
		ReadBufferSize:   4096,
		WriteBufferSize:  4096,
	}
	if strings.HasPrefix(strings.ToLower(cfg.URL), "wss://") {
		dialer.TLSClientConfig = buildTunnelTLSConfig(cfg)
	}
	conn, resp, err := dialer.Dial(cfg.URL, nil)
	if resp != nil && resp.Body != nil {
		_ = resp.Body.Close()
	}
	if err != nil {
		return fmt.Errorf("dial: %w", err)
	}
	conn.SetReadLimit(tunnelMaxFrame)
	t.setConn(conn)
	t.setActive(true)

	// ctx 取消时主动断开阻塞中的读循环
	done := make(chan struct{})
	go func() {
		select {
		case <-ctx.Done():
			_ = conn.Close()
		case <-done:
		}
	}()
	defer func() {
		close(done)
		t.setActive(false)
		t.closeAllStreams()
		t.setConn(nil)
		_ = conn.Close()
	}()

	conn.SetPingHandler(func(appData string) error {
		_ = conn.SetReadDeadline(time.Now().Add(tunnelReadWait))
		return conn.WriteControl(websocket.PongMessage, []byte(appData), time.Now().Add(5*time.Second))
	})
	conn.SetPongHandler(func(string) error {
		_ = conn.SetReadDeadline(time.Now().Add(tunnelReadWait))
		return nil
	})

	// hello
	hostname, _ := os.Hostname()
	hello := map[string]interface{}{
		"op":    "hello",
		"v":     1,
		"token": cfg.Token,
		"device": map[string]string{
			"platform":      runtime.GOOS,
			"hostname":      hostname,
			"proxy_version": tunnelProtocolVersion,
		},
	}
	raw, _ := json.Marshal(hello)
	t.writeMu.Lock()
	_ = conn.SetWriteDeadline(time.Now().Add(15 * time.Second))
	err = conn.WriteMessage(websocket.TextMessage, raw)
	t.writeMu.Unlock()
	if err != nil {
		return fmt.Errorf("send hello: %w", err)
	}

	// hello_ack
	_ = conn.SetReadDeadline(time.Now().Add(tunnelHelloWait))
	_, data, err := conn.ReadMessage()
	if err != nil {
		if websocket.IsCloseError(err, 4001) {
			return errTunnelAuth
		}
		return fmt.Errorf("wait hello_ack: %w", err)
	}
	var ack struct {
		Op    string `json:"op"`
		OK    bool   `json:"ok"`
		Error string `json:"error"`
	}
	if json.Unmarshal(data, &ack) != nil || ack.Op != "hello_ack" || !ack.OK {
		return errTunnelAuth
	}
	log.Printf("[tunnel] 已连接 %s（云端 CDP 通道就绪）", cfg.URL)

	// 主读循环
	_ = conn.SetReadDeadline(time.Now().Add(tunnelReadWait))
	for {
		mt, payload, err := conn.ReadMessage()
		if err != nil {
			if websocket.IsCloseError(err, 4001) {
				return errTunnelAuth
			}
			return err
		}
		_ = conn.SetReadDeadline(time.Now().Add(tunnelReadWait))
		switch mt {
		case websocket.TextMessage:
			t.handleControl(payload)
		case websocket.BinaryMessage:
			t.handleData(payload)
		}
	}
}

func (t *tunnelClient) handleControl(raw []byte) {
	var msg struct {
		Op     string `json:"op"`
		Sid    uint32 `json:"sid"`
		Reason string `json:"reason"`
	}
	if json.Unmarshal(raw, &msg) != nil {
		return
	}
	switch strings.ToLower(strings.TrimSpace(msg.Op)) {
	case "cdp_open":
		go t.openCdpStream(msg.Sid) // dial 可能耗时，勿阻塞读循环
	case "cdp_close":
		t.closeCdpStream(msg.Sid)
	case "pong":
		// 心跳应答，无需处理（读超时已在循环里刷新）
	}
}

func (t *tunnelClient) handleData(frame []byte) {
	if len(frame) < 4 {
		return
	}
	sid := binary.BigEndian.Uint32(frame[:4])
	st := t.getStream(sid)
	if st == nil {
		return
	}
	if err := st.ws.WriteMessage(websocket.TextMessage, frame[4:]); err != nil {
		_ = st.ws.Close()
	}
}

func (t *tunnelClient) ackOpen(sid uint32, ok bool, errMsg string) {
	_ = t.writeControl(map[string]interface{}{
		"op":    "cdp_open_ack",
		"sid":   sid,
		"ok":    ok,
		"error": errMsg,
	})
}

func (t *tunnelClient) openCdpStream(sid uint32) {
	st := globalBrowser.Status()
	if !st.Running || st.CdpPort <= 0 {
		t.ackOpen(sid, false, "browser_not_running")
		return
	}
	wsURL, err := fetchBrowserWSURL(st.CdpPort)
	if err != nil {
		t.ackOpen(sid, false, "cdp_endpoint_unavailable: "+err.Error())
		return
	}
	// 白名单：只允许连本代理自有 Chrome 的 DevTools（防任意端口转发）
	if !isAllowedChromeWS(wsURL, st.CdpPort) {
		t.ackOpen(sid, false, "target_not_allowed")
		return
	}
	conn, resp, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if resp != nil && resp.Body != nil {
		_ = resp.Body.Close()
	}
	if err != nil {
		t.ackOpen(sid, false, "chrome_dial_failed: "+err.Error())
		return
	}
	t.putStream(&tunnelStream{sid: sid, ws: conn})
	t.ackOpen(sid, true, "")
	go t.pumpChrome(sid, conn)
}

func (t *tunnelClient) pumpChrome(sid uint32, conn *websocket.Conn) {
	for {
		mt, payload, err := conn.ReadMessage()
		if err != nil {
			break
		}
		if mt != websocket.TextMessage && mt != websocket.BinaryMessage {
			continue
		}
		if err := t.writeData(sid, payload); err != nil {
			break
		}
	}
	_ = conn.Close()
	if t.getStream(sid) != nil {
		t.removeStream(sid)
		_ = t.writeControl(map[string]interface{}{
			"op":     "cdp_close",
			"sid":    sid,
			"reason": "chrome_ws_closed",
		})
	}
}

func (t *tunnelClient) closeCdpStream(sid uint32) {
	st := t.getStream(sid)
	if st == nil {
		return
	}
	t.removeStream(sid)
	_ = st.ws.Close()
}

// fetchBrowserWSURL 读取本机 Chrome DevTools HTTP 端点的 webSocketDebuggerUrl。
func fetchBrowserWSURL(port int) (string, error) {
	client := &http.Client{Timeout: 3 * time.Second}
	resp, err := client.Get(fmt.Sprintf("http://127.0.0.1:%d/json/version", port))
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("status %d", resp.StatusCode)
	}
	var data struct {
		WebSocketDebuggerURL string `json:"webSocketDebuggerUrl"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return "", err
	}
	ws := strings.TrimSpace(data.WebSocketDebuggerURL)
	if ws == "" {
		return "", errors.New("webSocketDebuggerUrl missing")
	}
	return ws, nil
}

// isAllowedChromeWS 校验 ws 地址指向本机 Chrome 调试端口（127.0.0.1:{port}/devtools/*）。
func isAllowedChromeWS(raw string, port int) bool {
	u, err := url.Parse(strings.TrimSpace(raw))
	if err != nil {
		return false
	}
	if u.Scheme != "ws" && u.Scheme != "wss" {
		return false
	}
	host := strings.ToLower(u.Hostname())
	if host != "127.0.0.1" && host != "localhost" && host != "::1" {
		return false
	}
	p, err := strconv.Atoi(u.Port())
	if err != nil || p != port {
		return false
	}
	return strings.HasPrefix(u.Path, "/devtools/")
}

// startTunnelWatcher 后台重读持久化配置：首次注入 / token 刷新后自动重建隧道。
func startTunnelWatcher() {
	go func() {
		var cur tunnelConfig
		var curSet bool
		first := true
		for {
			cfg := loadTunnelConfig()
			changed := strings.TrimSpace(cfg.URL) != "" && (!curSet ||
				cfg.URL != cur.URL || cfg.Token != cur.Token)
			if changed {
				if norm, err := normalizeTunnelConfig(cfg); err != nil {
					log.Printf("[tunnel] 配置无效，隧道不启动: %v", err)
				} else {
					cur = norm
					curSet = true
					verb := "启动"
					if !first {
						verb = "重配置"
					}
					log.Printf("[tunnel] %s：%s", verb, norm.URL)
					globalTunnel.reconfigure(norm)
				}
			} else if first && !curSet && strings.TrimSpace(cfg.URL) == "" {
				log.Printf("[tunnel] 未配置隧道（--tunnel-url / BADCASE_TUNNEL_URL / 持久化文件），仅本地模式")
			}
			first = false
			time.Sleep(tunnelConfigPollSec * time.Second)
		}
	}()
}
