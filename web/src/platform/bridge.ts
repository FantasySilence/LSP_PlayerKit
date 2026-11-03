declare global {
  interface Window {
    pywebview?: {
      api: Record<string, (...args: unknown[]) => Promise<unknown>>
    }
  }
}

export class BridgeError extends Error {
  code: string
  detail: string

  constructor(code: string, message: string, detail = '') {
    super(message)
    this.code = code
    this.detail = detail
  }
}

let readyPromise: Promise<void> | null = null

export function waitReady(): Promise<void> {
  if (window.pywebview?.api) return Promise.resolve()
  if (readyPromise) return readyPromise

  readyPromise = new Promise<void>((resolve, reject) => {
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
      { once: true },
    )
  })
  return readyPromise
}

export async function invoke<T = unknown>(method: string, ...args: unknown[]): Promise<T> {
  await waitReady()
  const api = window.pywebview?.api
  const fn = api?.[method]
  if (!fn) throw new BridgeError('NO_METHOD', `后端缺少方法 ${method}`)

  const raw = (await fn(...args)) as
    | { ok: true; data: T }
    | { ok: false; error: { code: string; message: string; detail: string } }

  if (raw && typeof raw === 'object' && 'ok' in raw) {
    if (!raw.ok) throw new BridgeError(raw.error.code, raw.error.message, raw.error.detail)
    return raw.data
  }
  return raw as T
}

export function callTool<T = unknown>(
  tool: string,
  action: string,
  payload: Record<string, unknown> = {},
): Promise<T> {
  return invoke<T>('tool_call', tool, action, payload)
}
