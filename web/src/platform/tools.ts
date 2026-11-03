const views = import.meta.glob('../tools/*/View.vue') as Record<
  string,
  () => Promise<{ default: unknown }>
>

export function viewFor(id: string): (() => Promise<{ default: unknown }>) | null {
  return views[`../tools/${id}/View.vue`] ?? null
}

export function hasView(id: string): boolean {
  return Boolean(viewFor(id))
}
