/**
 * pywebview 桥接层（bridge.ts）
 *
 * 桌面端用 pywebview 把 Python 后端暴露成 window.pywebview.api，本文件负责：
 * - 等待桥就绪（页面可能先于 Python 注入完成而加载）；
 * - 用统一信封（envelope）调用后端方法，并把失败信封转换成 BridgeError；
 * - 提供 callTool 语法糖，专门调用某个工具的某个 action。
 *
 * 交互关系：
 * - 后端 src/lspkit/api.py 的公开方法都返回信封：
 *   成功为 { ok: true, data }，失败为 { ok: false, error: { code, message, detail } }；
 * - App.vue、SettingsDrawer.vue 以及各工具 View.vue 都通过 invoke/callTool 取数据；
 * - 抛出的 BridgeError 最终多由 platform/toast.ts 的 notifyError 显示成提示。
 */
declare global {
  interface Window {
    // pywebview 注入的对象；api 的键就是后端 Api 类里的方法名
    pywebview?: {
      api: Record<string, (...args: unknown[]) => Promise<unknown>>
    }
  }
}

// 把后端的错误信封封装成异常，调用方 catch 后可以读取 code / detail
export class BridgeError extends Error {
  code: string
  detail: string

  constructor(code: string, message: string, detail = '') {
    super(message)
    // 稳定的错误码（如 INVALID_INPUT），前端可据此区分错误类型
    this.code = code
    // 补充说明，通常作为 Toast 的第二行显示
    this.detail = detail
  }
}

// 就绪 Promise 的缓存：多次调用 waitReady 只监听一次事件，避免重复等待
let readyPromise: Promise<void> | null = null

// 等待 pywebview 就绪：已注入则立刻返回，否则等 pywebviewready 事件（最多 6 秒）
export function waitReady(): Promise<void> {
  if (window.pywebview?.api) return Promise.resolve()
  if (readyPromise) return readyPromise

  readyPromise = new Promise<void>((resolve, reject) => {
    // 超时兜底：通常说明不是从桌面程序启动，而是直接用浏览器打开了页面
    const timer = window.setTimeout(
      () => reject(new BridgeError('BRIDGE_TIMEOUT', '无法连接到后端，请从桌面程序启动')),
      6000,
    )
    window.addEventListener(
      'pywebviewready',
      () => {
        window.clearTimeout(timer)
        resolve()
      },
      // once: true 表示事件只处理一次，触发后监听自动移除
      { once: true },
    )
  })
  return readyPromise
}

/**
 * 调用后端方法并拆信封。
 * - 自动等待桥就绪；
 * - 后端不存在该方法时抛 NO_METHOD；
 * - 成功返回信封里的 data，失败把 error 转成 BridgeError；
 * - 兼容旧行为：返回值不像信封（没有 ok 字段）时原样当作结果返回。
 */
export async function invoke<T = unknown>(method: string, ...args: unknown[]): Promise<T> {
  await waitReady()
  // api 是 pywebview 注入的方法表，按方法名取出可调用函数
  const api = window.pywebview?.api
  const fn = api?.[method]
  if (!fn) throw new BridgeError('NO_METHOD', `后端缺少方法 ${method}`)

  // 后端统一返回信封：成功 { ok: true, data }，失败 { ok: false, error }
  const raw = (await fn(...args)) as
    | { ok: true; data: T }
    | { ok: false; error: { code: string; message: string; detail: string } }

  // 'ok' in raw：只有看起来像信封的返回值才拆包，否则按裸数据返回
  if (raw && typeof raw === 'object' && 'ok' in raw) {
    if (!raw.ok) throw new BridgeError(raw.error.code, raw.error.message, raw.error.detail)
    return raw.data
  }
  return raw as T
}

/**
 * 调用某个工具的 action。
 * 对应后端 Api.tool_call(tool, action, payload)，最终由 Registry 找到该工具注册的处理器；
 * payload 会经 pywebview 序列化后交给 Python，键名需与各工具 actions.py 读取的一致。
 */
export function callTool<T = unknown>(
  tool: string,
  action: string,
  payload: Record<string, unknown> = {},
): Promise<T> {
  return invoke<T>('tool_call', tool, action, payload)
}
