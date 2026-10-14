import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { gzipSync } from 'node:zlib'

const CORE_GZIP_LIMIT = 8 * 1024
/** 回放入口（不含 rrweb，rrweb 运行时懒加载）gzip 上限；当前约 4KB */
const REPLAY_GZIP_LIMIT = 6 * 1024
/** rrweb 被打进回放入口的特征（应保持为外部依赖、动态 import） */
const RRWEB_BUNDLED_MARKERS = ['rrweb-snapshot', 'IncrementalSource']

function walk(dir) {
  const out = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) out.push(...walk(p))
    else out.push(p)
  }
  return out
}

let failed = false
for (const file of walk('dist').sort()) {
  const buf = readFileSync(file)
  const gz = gzipSync(buf)
  const line = `${file.padEnd(28)} ${(buf.length / 1024).toFixed(2).padStart(8)} KB  gzip ${(gz.length / 1024).toFixed(2).padStart(7)} KB`
  console.log(line)
  // 体积门禁：core 入口（纯逻辑零 DOM）gzip ≤ 8KB
  if (file === 'dist/core.js' && gz.length > CORE_GZIP_LIMIT) {
    console.error(`core gzip 超限：${(gz.length / 1024).toFixed(2)} KB > 8 KB`)
    failed = true
  }
  // 体积门禁：回放入口（ESM / CJS）gzip ≤ 6KB，且 rrweb 不得被打包进来
  if (file === 'dist/replay/index.js' || file === 'dist/replay/index.cjs') {
    if (gz.length > REPLAY_GZIP_LIMIT) {
      console.error(`${file} gzip 超限：${(gz.length / 1024).toFixed(2)} KB > 6 KB`)
      failed = true
    }
    const text = buf.toString('utf8')
    const hit = RRWEB_BUNDLED_MARKERS.find((m) => text.includes(m))
    if (hit) {
      console.error(`${file} 疑似把 rrweb 打包进来了（命中 ${hit}），rrweb 应保持外部依赖、动态 import`)
      failed = true
    }
  }
}
if (failed) process.exit(1)
