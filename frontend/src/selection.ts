export type View = 'overview' | 'cluster' | 'node'

export function initialView(requested: string | null, gid: string | null, cluster: number | null): View {
  if (requested === 'node' && gid) return 'node'
  if (requested === 'cluster' && cluster !== null) return 'cluster'
  return 'overview'
}
