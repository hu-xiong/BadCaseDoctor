// 空闲自动退出：无 WebSocket/PTY 连接且超过 IDLE_EXIT_SEC 无客户端活动时退出进程。
// /health 探测不刷新活动时间（避免 Flask 探活阻止关机）。
package main

import (
	"log"
	"os"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

var (
	idleActiveConns int64
	idleLastTouch   atomic.Int64 // unix nano
	idleExitOnce    sync.Once
)

func idleExitSec() int {
	raw := strings.TrimSpace(os.Getenv("IDLE_EXIT_SEC"))
	if raw == "" {
		raw = strings.TrimSpace(os.Getenv("BADCASE_LOCAL_PROXY_IDLE_EXIT_SEC"))
	}
	if raw == "" {
		return 1800 // 默认 30 分钟
	}
	n, err := strconv.Atoi(raw)
	if err != nil {
		return 1800
	}
	return n
}

func touchClientActivity() {
	idleLastTouch.Store(time.Now().UnixNano())
}

func idleConnEnter() {
	atomic.AddInt64(&idleActiveConns, 1)
	touchClientActivity()
}

func idleConnLeave() {
	atomic.AddInt64(&idleActiveConns, -1)
	touchClientActivity()
}

func startIdleExitWatchdog(shutdown func()) {
	sec := idleExitSec()
	if sec <= 0 {
		log.Printf("[go-local-proxy] idle exit disabled (IDLE_EXIT_SEC=%d)", sec)
		return
	}
	touchClientActivity()
	log.Printf("[go-local-proxy] idle exit after %ds without client activity (WS/PTY/browser)", sec)
	go func() {
		ticker := time.NewTicker(15 * time.Second)
		defer ticker.Stop()
		for range ticker.C {
			if atomic.LoadInt64(&idleActiveConns) > 0 {
				continue
			}
			last := idleLastTouch.Load()
			if last <= 0 {
				continue
			}
			idleFor := time.Since(time.Unix(0, last))
			if idleFor < time.Duration(sec)*time.Second {
				continue
			}
			idleExitOnce.Do(func() {
				log.Printf("[go-local-proxy] idle %v >= %ds and no connections — exiting", idleFor.Round(time.Second), sec)
				if shutdown != nil {
					shutdown()
				}
				os.Exit(0)
			})
			return
		}
	}()
}
