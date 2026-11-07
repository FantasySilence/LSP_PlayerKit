/**
 * 工具视图注册表（tools.ts）
 *
 * 用 Vite 的 import.meta.glob 在构建时收集 web/src/tools/<id>/View.vue，
 * 得到一个“路径 → 懒加载函数”的映射；运行时再按工具 id 查出对应视图。
 * 注意：这里只收集，不主动加载，真正的 import 发生在组件被渲染时。
 *
 * 约定：工具 id 必须与目录名一致，例如 id 为 pearl 就对应
 * web/src/tools/pearl/View.vue，否则 App.vue 会显示没有视图的提示。
 *
 * 交互关系：
 * - App.vue 的 componentFor 调用 viewFor(id)，再包成 defineAsyncComponent；
 * - hasView 用于判断某个 id 是否有视图（例如后端新增了工具但前端还没实现）。
 */

// 构建时收集所有工具视图；键是相对路径，如 ../tools/pearl/View.vue
const views = import.meta.glob('../tools/*/View.vue') as Record<
  string,
  () => Promise<{ default: unknown }>
>

// 按工具 id 取对应的懒加载函数；没有该工具的视图时返回 null
export function viewFor(id: string): (() => Promise<{ default: unknown }>) | null {
  return views[`../tools/${id}/View.vue`] ?? null
}

// 判断某个工具 id 是否有前端视图
export function hasView(id: string): boolean {
  return Boolean(viewFor(id))
}
