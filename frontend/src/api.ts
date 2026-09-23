export type Role = 'consolidator' | 'transit' | 'distributor' | 'terminal' | 'coordinator' | 'peripheral'

export interface NodeData {
  gid: string
  role: Role
  role_score: number
  cluster_id: number
  priority_score: number
  evidence: string
  depth: number
  is_seed: boolean
  in_degree: number
  out_degree: number
  in_kzt: number
  out_kzt: number
  in_tx: number
  out_tx: number
  pagerank: number
  pass_through: number | null
  in_concentration: number
  out_concentration: number
  boundary: boolean
  component_id: number
}

export interface EdgeData { src: string; dst: string; sum_kzt: number; n_tx: number }
export interface LinkData extends EdgeData { counterparty_gid: string; role: Role }
export interface ClusterData { cluster_id: number; n_nodes: number; n_seed: number; sum_kzt_internal: number; top_gids: string[]; hypothesis: string }
export interface SummaryData {
  n_nodes: number; n_edges: number; n_transactions: number; n_seeds: number; n_clusters: number
  n_components: number; n_isolates: number; n_boundary: number; sum_kzt: number
  period_start: string; period_end: string; elapsed_seconds: number
  role_counts: Record<string, number>; warnings: string[]
}
export interface NodeList { items: NodeData[]; total: number; limit: number; offset: number }
export interface NodeDetail { node: NodeData; incoming: LinkData[]; outgoing: LinkData[]; warnings: string[]; next_steps: string[] }
export interface GraphData { nodes: NodeData[]; edges: EdgeData[]; truncated: boolean; total_nodes: number; total_edges: number }

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message) }
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api${path}`, { signal })
  if (!response.ok) {
    let message = `Ошибка сервера (${response.status})`
    try {
      const body = await response.json() as { detail?: unknown }
      if (typeof body.detail === 'string') message = body.detail
    } catch { /* use HTTP status */ }
    throw new ApiError(message, response.status)
  }
  return response.json() as Promise<T>
}

export const roles: Role[] = ['coordinator', 'consolidator', 'transit', 'distributor', 'terminal', 'peripheral']
export const roleLabel: Record<Role, string> = {
  coordinator: 'Координирующий узел',
  consolidator: 'Консолидация',
  transit: 'Транзит',
  distributor: 'Распределение',
  terminal: 'Конечный получатель',
  peripheral: 'Периферия',
}

export const roleColor: Record<Role, string> = {
  coordinator: '#72569b',
  consolidator: '#c25643',
  transit: '#278779',
  distributor: '#d48d30',
  terminal: '#4c769d',
  peripheral: '#8a9aa1',
}

const number = new Intl.NumberFormat('ru-RU')
const compact = new Intl.NumberFormat('ru-RU', { notation: 'compact', maximumFractionDigits: 1 })
const percent = new Intl.NumberFormat('ru-RU', { style: 'percent', maximumFractionDigits: 0 })
const score = new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
export const formatCount = (value: number) => number.format(value)
export const formatMoney = (value: number) => `${number.format(Math.round(value))} ₸`
export const formatMoneyCompact = (value: number) => `${compact.format(value)} ₸`
export const formatPercent = (value: number) => percent.format(value)
export const formatScore = (value: number) => score.format(value)

export function safeMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Не удалось получить данные. Проверьте, что API запущен, и повторите запрос.'
}
