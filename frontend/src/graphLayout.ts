import type { EdgeData, GraphData, NodeData } from './api'

export interface Position { x: number; y: number }

export interface Neighborhood {
  nodes: NodeData[]
  edges: EdgeData[]
  positions: Record<string, Position>
  totalCounterparties: number
  shownCounterparties: number
}

interface Counterparty {
  node: NodeData
  amount: number
  incoming: boolean
  outgoing: boolean
}

const DEFAULT_LIMIT = 20

function compareGid(a: string, b: string): number {
  const left = BigInt(a)
  const right = BigInt(b)
  return left < right ? -1 : left > right ? 1 : 0
}

function placeSide(items: Counterparty[], direction: -1 | 1, positions: Record<string, Position>): number {
  const rowsPerColumn = Math.min(12, Math.max(4, Math.ceil(Math.sqrt(items.length * 1.7))))
  let lowestY = 0
  for (let index = 0; index < items.length; index += 1) {
    const column = Math.floor(index / rowsPerColumn)
    const row = index % rowsPerColumn
    const columnCount = Math.min(rowsPerColumn, items.length - column * rowsPerColumn)
    const y = (row - (columnCount - 1) / 2) * 64 + (column % 2) * 28
    positions[items[index]!.node.gid] = {
      x: direction * (185 + column * 82),
      y,
    }
    lowestY = Math.max(lowestY, y)
  }
  return lowestY
}

function placeBidirectional(items: Counterparty[], startY: number, positions: Record<string, Position>) {
  const columns = Math.min(5, Math.max(1, Math.ceil(Math.sqrt(items.length))))
  for (let index = 0; index < items.length; index += 1) {
    const row = Math.floor(index / columns)
    const column = index % columns
    const rowCount = Math.min(columns, items.length - row * columns)
    positions[items[index]!.node.gid] = {
      x: (column - (rowCount - 1) / 2) * 82,
      y: startY + row * 68,
    }
  }
}

export function buildNeighborhood(data: GraphData, selectedGid: string, showAll: boolean): Neighborhood {
  const selected = data.nodes.find((node) => node.gid === selectedGid)
  if (!selected) {
    return { nodes: [], edges: [], positions: {}, totalCounterparties: 0, shownCounterparties: 0 }
  }

  const counterparts = new Map<string, Counterparty>()
  const byGid = new Map(data.nodes.map((node) => [node.gid, node]))
  for (const edge of data.edges) {
    if (edge.src !== selectedGid && edge.dst !== selectedGid) continue
    if (edge.src === selectedGid && edge.dst === selectedGid) continue
    const gid = edge.src === selectedGid ? edge.dst : edge.src
    const node = byGid.get(gid)
    if (!node) continue
    const entry = counterparts.get(gid) ?? { node, amount: 0, incoming: false, outgoing: false }
    entry.amount += edge.sum_kzt
    if (edge.dst === selectedGid) entry.incoming = true
    if (edge.src === selectedGid) entry.outgoing = true
    counterparts.set(gid, entry)
  }

  const ranked = [...counterparts.values()].sort((a, b) => b.amount - a.amount || compareGid(a.node.gid, b.node.gid))
  const visible = showAll ? ranked : ranked.slice(0, DEFAULT_LIMIT)
  const visibleGids = new Set([selectedGid, ...visible.map(({ node }) => node.gid)])
  const positions: Record<string, Position> = { [selectedGid]: { x: 0, y: 0 } }
  const incomingBottom = placeSide(visible.filter((item) => item.incoming && !item.outgoing), -1, positions)
  const outgoingBottom = placeSide(visible.filter((item) => item.outgoing && !item.incoming), 1, positions)
  placeBidirectional(visible.filter((item) => item.incoming && item.outgoing), Math.max(190, incomingBottom + 110, outgoingBottom + 110), positions)

  return {
    nodes: [selected, ...visible.map(({ node }) => node)],
    edges: data.edges.filter((edge) => visibleGids.has(edge.src) && visibleGids.has(edge.dst)),
    positions,
    totalCounterparties: ranked.length,
    shownCounterparties: visible.length,
  }
}
