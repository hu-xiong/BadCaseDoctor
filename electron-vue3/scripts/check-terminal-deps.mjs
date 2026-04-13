/**
 * 嵌入式终端依赖（xterm）需在 electron-vue3 目录安装：npm install
 */
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const need = [
  '@xterm/xterm',
  '@xterm/addon-fit',
  '@xterm/addon-clipboard',
  '@xterm/addon-serialize',
  '@xterm/addon-search'
]
for (const name of need) {
  try {
    require.resolve(name)
  } catch {
    console.error(`[electron-vue3] 未找到依赖 "${name}"，请在本目录执行: npm install`)
    process.exit(1)
  }
}
