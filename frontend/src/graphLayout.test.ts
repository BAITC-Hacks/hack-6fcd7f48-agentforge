import assert from 'node:assert/strict'
import test from 'node:test'
import type { EdgeData, GraphData, NodeData } from './api.ts'
import { buildNeighborhood } from './graphLayout.ts'

function node(gid: string): NodeData {
  return {
    gid, role: 'peripheral', role_score: 0.5, cluster_id: 1, priority_score: 0.25,
    priority_breakdown: [], priority_factor: 1, priority_reason: 'Тестовый узел',
    evidence: 'Тестовый узел', depth: 1, is_seed: false, seed_source_count: 0, seed_paths: [],
    in_degree: 0, out_degree: 0,
    in_kzt: 0, out_kzt: 0, in_tx: 0, out_tx: 0, pagerank: 0.01,
    pass_through: null, in_concentration: 0, out_concentration: 0,
    boundary: false, component_id: 1,
  }
}

function graph(nodes: NodeData[], edges: EdgeData[]): GraphData {
  return { nodes, edges, truncated: false, total_nodes: nodes.length, total_edges: edges.length }
}

function assertSpacing(positions: Record<string, { x: number; y: number }>) {
  const points = Object.values(positions)
  for (let i = 0; i < points.length; i += 1) {
    for (let j = i + 1; j < points.length; j += 1) {
      const dx = points[i]!.x - points[j]!.x
      const dy = points[i]!.y - points[j]!.y
      assert.ok(Math.hypot(dx, dy) >= 40, `centers ${i} and ${j} overlap`)
    }
  }
}

test('isolate and stale selection have safe, distinct outcomes', () => {
  const data = graph([node('9007199254740993')], [])
  const isolated = buildNeighborhood(data, '9007199254740993', false)
  assert.deepEqual(isolated.nodes.map((entry) => entry.gid), ['9007199254740993'])
  assert.deepEqual(isolated.edges, [])
  assert.deepEqual(isolated.positions, { '9007199254740993': { x: 0, y: 0 } })
  assert.equal(isolated.totalCounterparties, 0)
  assert.equal(isolated.shownCounterparties, 0)

  const stale = buildNeighborhood(data, '-9007199254740993', true)
  assert.deepEqual(stale, { nodes: [], edges: [], positions: {}, totalCounterparties: 0, shownCounterparties: 0 })
})

test('incoming, outgoing and two-way nodes occupy separate zones without lost edges', () => {
  const selected = '9007199254740997'
  const incoming = Array.from({ length: 7 }, (_, index) => String(index + 1))
  const outgoing = Array.from({ length: 10 }, (_, index) => String(index + 11))
  const both = ['-9007199254740993', '9007199254740993']
  const edges: EdgeData[] = [
    ...incoming.map((gid) => ({ src: gid, dst: selected, sum_kzt: 7000, n_tx: 1 })),
    ...outgoing.map((gid) => ({ src: selected, dst: gid, sum_kzt: 8000, n_tx: 2 })),
    ...both.flatMap((gid) => [
      { src: gid, dst: selected, sum_kzt: 9000, n_tx: 1 },
      { src: selected, dst: gid, sum_kzt: 10000, n_tx: 2 },
    ]),
    { src: selected, dst: selected, sum_kzt: 5000, n_tx: 1 },
    { src: incoming[0]!, dst: outgoing[0]!, sum_kzt: 5500, n_tx: 1 },
  ]
  const data = graph([selected, ...incoming, ...outgoing, ...both].map(node), edges)
  const before = JSON.stringify(data)
  const result = buildNeighborhood(data, selected, true)
  assert.equal(result.totalCounterparties, 19)
  assert.equal(result.shownCounterparties, 19)
  assert.deepEqual(new Set(result.nodes.map((entry) => entry.gid)), new Set(data.nodes.map((entry) => entry.gid)))
  assert.deepEqual(result.edges, edges)
  assert.equal(JSON.stringify(data), before)
  assert.ok(incoming.every((gid) => result.positions[gid]!.x < 0))
  assert.ok(outgoing.every((gid) => result.positions[gid]!.x > 0))
  assert.ok(both.every((gid) => result.positions[gid]!.y > 0))
  assertSpacing(result.positions)
})

test('80+ counterparties: direct two-way amount, numeric tie and input order determine a stable top 20', () => {
  const selected = '9007199254740997'
  const ordinary = Array.from({ length: 78 }, (_, index) => String(index + 1))
  const negative = '-7'
  const huge = '9007199254740993'
  const all = [negative, ...ordinary, huge]
  const edges: EdgeData[] = all.map((gid) => ({
    src: selected, dst: gid,
    sum_kzt: ordinary.slice(0, 18).includes(gid) ? 1000 - Number(gid) : 200,
    n_tx: 1,
  }))
  edges.push({ src: huge, dst: selected, sum_kzt: 300, n_tx: 3 })
  const data = graph([node(selected), ...all.map(node)], edges)
  const limited = buildNeighborhood(data, selected, false)
  assert.equal(limited.totalCounterparties, 80)
  assert.equal(limited.shownCounterparties, 20)
  const expected = new Set([selected, ...ordinary.slice(0, 18), huge, negative])
  assert.deepEqual(new Set(limited.nodes.map((entry) => entry.gid)), expected)
  assert.ok(limited.edges.every((edge) => expected.has(edge.src) && expected.has(edge.dst)))
  assert.ok(limited.edges.find((edge) => edge.src === huge)?.sum_kzt === 300)
  assertSpacing(limited.positions)

  const full = buildNeighborhood(data, selected, true)
  assert.equal(full.shownCounterparties, 80)
  assert.deepEqual(new Set(full.nodes.map((entry) => entry.gid)), new Set(data.nodes.map((entry) => entry.gid)))
  assert.deepEqual(full.edges, edges)
  assertSpacing(full.positions)

  const shuffled = graph([...data.nodes].reverse(), [...data.edges].reverse())
  const limitedShuffled = buildNeighborhood(shuffled, selected, false)
  assert.deepEqual(limitedShuffled.nodes.map((entry) => entry.gid), limited.nodes.map((entry) => entry.gid))
  assert.deepEqual(limitedShuffled.positions, limited.positions)
  const fullShuffled = buildNeighborhood(shuffled, selected, true)
  assert.deepEqual(fullShuffled.positions, full.positions)
})

test('61 outgoing counterparties fit a useful width when expanded', () => {
  const selected = '9007199254740997'
  const receivers = Array.from({ length: 61 }, (_, index) => String(index + 1))
  const result = buildNeighborhood(
    graph(
      [node(selected), ...receivers.map(node)],
      receivers.map((dst) => ({ src: selected, dst, sum_kzt: 5000, n_tx: 1 })),
    ),
    selected,
    true,
  )
  assert.equal(result.shownCounterparties, 61)
  const xs = Object.values(result.positions).map(({ x }) => x)
  assert.ok(Math.max(...xs) - Math.min(...xs) <= 2000)
  assertSpacing(result.positions)
})
