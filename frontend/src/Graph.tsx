import { useEffect, useMemo, useRef, useState } from 'react'
import cytoscape, { type Core, type ElementDefinition, type StylesheetStyle } from 'cytoscape'
import { type EdgeData, type GraphData, formatCount, roleColor, roleLabel, roles } from './api'
import { buildNeighborhood } from './graphLayout'

type View = 'overview' | 'cluster' | 'node'

interface Props {
  data: GraphData
  selectedGid: string | null
  view: View
  onSelect: (gid: string) => void
}

const FIT_ZOOM_LIMIT = 1.08
const money = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 })
const graphLabel = (gid: string) => gid.length > 10 ? `…${gid.slice(-7)}` : gid
const edgeId = (edge: EdgeData) => `flow:${edge.src}->${edge.dst}`

const graphStyle: StylesheetStyle[] = [
  { selector: 'node', style: {
    'background-color': 'data(color)', 'label': 'data(label)', 'color': '#233d47',
    'font-size': 10, 'font-family': 'Arial, sans-serif', 'text-valign': 'bottom', 'text-margin-y': 5,
    'text-outline-width': 2, 'text-outline-color': '#ffffff',
    'width': 'data(size)', 'height': 'data(size)',
    'border-width': 2, 'border-color': '#ffffff',
  } },
  { selector: 'node[?isSeed]', style: { 'border-width': 3, 'border-color': '#203946' } },
  { selector: 'node[?selected]', style: { 'border-width': 4, 'border-color': '#132f3b', 'font-size': 11, 'font-weight': 'bold', 'z-index': 999 } },
  { selector: 'node[?focusEndpoint]', style: { 'border-width': 4, 'border-color': '#285d73', 'z-index': 998 } },
  { selector: 'node[?dimmed]', style: { 'opacity': 0.18 } },
  { selector: 'edge', style: {
    'width': 1.35, 'line-color': '#819aa5', 'target-arrow-color': '#527784',
    'target-arrow-shape': 'triangle', 'arrow-scale': 0.8, 'curve-style': 'bezier',
    'control-point-step-size': 24, 'opacity': 0.78,
  } },
  { selector: 'edge[?dimmed]', style: { 'opacity': 0.08 } },
  { selector: 'edge[?focused]', style: {
    'width': 3, 'line-color': '#285d73', 'target-arrow-color': '#285d73',
    'opacity': 1, 'z-index': 999,
  } },
]

function fitGraph(cy: Core) {
  cy.resize()
  cy.fit(undefined, 48)
  if (cy.zoom() > FIT_ZOOM_LIMIT) {
    cy.zoom(FIT_ZOOM_LIMIT)
    cy.center()
  }
}

export default function Graph({ data, selectedGid, view, onSelect }: Props) {
  const [expandedGid, setExpandedGid] = useState<string | null>(null)
  const [hoveredNode, setHoveredNode] = useState<string | null>(null)
  const [hoveredEdge, setHoveredEdge] = useState<string | null>(null)
  const [pinnedEdge, setPinnedEdge] = useState<string | null>(null)
  const container = useRef<HTMLDivElement>(null)
  const instance = useRef<Core | null>(null)
  const updateLabels = useRef<(() => void) | null>(null)
  const selectRef = useRef(onSelect)
  const selectedRef = useRef(selectedGid)
  const previousSelection = useRef(selectedGid)
  selectRef.current = onSelect
  selectedRef.current = selectedGid

  useEffect(() => {
    if (previousSelection.current === selectedGid) return
    previousSelection.current = selectedGid
    setExpandedGid(null)
    setPinnedEdge(null)
    setHoveredEdge(null)
    setHoveredNode(null)
  }, [selectedGid])

  const showAll = view === 'node' && selectedGid === expandedGid
  const neighborhood = useMemo(
    () => view === 'node' && selectedGid ? buildNeighborhood(data, selectedGid, showAll) : null,
    [data, selectedGid, showAll, view],
  )
  const waitingForNode = view === 'node' && (!selectedGid || neighborhood?.nodes.length === 0)
  const visibleNodes = neighborhood?.nodes ?? data.nodes
  const visibleEdges = neighborhood?.edges ?? data.edges
  const edgeById = useMemo(() => new Map(visibleEdges.map((edge) => [edgeId(edge), edge])), [visibleEdges])
  const nodeById = useMemo(() => new Map(visibleNodes.map((node) => [node.gid, node])), [visibleNodes])
  const focusedEdgeId = (pinnedEdge && edgeById.has(pinnedEdge) ? pinnedEdge : null)
    ?? (hoveredEdge && edgeById.has(hoveredEdge) ? hoveredEdge : null)
  const focusedEdge = focusedEdgeId ? edgeById.get(focusedEdgeId) : undefined
  const focusedNode = !focusedEdge && hoveredNode ? nodeById.get(hoveredNode) : undefined

  useEffect(() => {
    if (waitingForNode || !container.current) return
    const elements: ElementDefinition[] = [
      ...visibleNodes.map((node) => ({
        data: {
          id: node.gid, label: '', color: roleColor[node.role], role: node.role,
          size: 16 + Math.min(11, node.priority_score * 15),
          baseSize: 16 + Math.min(11, node.priority_score * 15),
          isSeed: node.is_seed, selected: false, focusEndpoint: false, dimmed: false,
        },
        ...(neighborhood ? { position: neighborhood.positions[node.gid] } : {}),
      })),
      ...visibleEdges.map((edge) => ({
        data: {
          id: edgeId(edge), source: edge.src, target: edge.dst,
          src: edge.src, dst: edge.dst, sum_kzt: edge.sum_kzt, n_tx: edge.n_tx,
          focused: false, dimmed: false,
        },
      })),
    ]
    const cy = cytoscape({
      container: container.current,
      elements,
      style: graphStyle,
      minZoom: 0.08,
      maxZoom: 3,
      wheelSensitivity: 0.2,
      layout: neighborhood
        ? { name: 'preset', fit: false, animate: false }
        : { name: 'cose', fit: false, animate: false, padding: 46, nodeRepulsion: () => 7000, idealEdgeLength: () => 90 },
    })
    instance.current = cy

    const refreshLabels = () => {
      const showOtherLabels = cy.zoom() >= (visibleNodes.length > 35 ? 1.5 : 1.25)
      cy.nodes().forEach((node) => {
        const selected = node.id() === selectedRef.current
        node.data('selected', selected)
        node.data('size', selected ? 34 : node.data('baseSize'))
        node.data('label', selected || showOtherLabels ? graphLabel(node.id()) : '')
      })
    }
    updateLabels.current = refreshLabels
    cy.on('zoom', refreshLabels)
    cy.on('tap', 'node', (event) => {
      setPinnedEdge(null)
      selectRef.current(event.target.id())
    })
    cy.on('mouseover', 'node', (event) => setHoveredNode(event.target.id()))
    cy.on('mouseout', 'node', () => setHoveredNode(null))
    cy.on('mouseover', 'edge', (event) => setHoveredEdge(event.target.id()))
    cy.on('mouseout', 'edge', () => setHoveredEdge(null))
    cy.on('tap', 'edge', (event) => {
      setPinnedEdge(event.target.id())
      setHoveredNode(null)
    })
    cy.on('tap', (event) => {
      if (event.target === cy) {
        setPinnedEdge(null)
        setHoveredEdge(null)
        setHoveredNode(null)
      }
    })

    fitGraph(cy)
    refreshLabels()
    const observer = new ResizeObserver(() => fitGraph(cy))
    observer.observe(container.current)
    return () => {
      observer.disconnect()
      cy.destroy()
      instance.current = null
      updateLabels.current = null
    }
  }, [visibleNodes, visibleEdges, neighborhood, waitingForNode, view])

  useEffect(() => {
    updateLabels.current?.()
  }, [selectedGid, visibleNodes])

  useEffect(() => {
    const cy = instance.current
    if (!cy) return
    cy.batch(() => {
      cy.edges().forEach((edge) => {
        edge.data('focused', edge.id() === focusedEdgeId)
        edge.data('dimmed', Boolean(focusedEdgeId) && edge.id() !== focusedEdgeId)
      })
      cy.nodes().forEach((node) => {
        const endpoint = Boolean(focusedEdge && (node.id() === focusedEdge.src || node.id() === focusedEdge.dst))
        node.data('focusEndpoint', endpoint)
        node.data('dimmed', Boolean(focusedEdgeId) && !endpoint)
      })
    })
  }, [focusedEdgeId, focusedEdge, visibleNodes, visibleEdges])

  function zoomBy(multiplier: number) {
    const cy = instance.current
    const element = container.current
    if (!cy || !element) return
    cy.zoom({
      level: Math.max(0.08, Math.min(3, cy.zoom() * multiplier)),
      renderedPosition: { x: element.clientWidth / 2, y: element.clientHeight / 2 },
    })
  }

  const isPinned = Boolean(pinnedEdge && pinnedEdge === focusedEdgeId)
  const inspector = (focusedEdge || focusedNode) && <div className={`graph-inspector${isPinned ? ' is-pinned' : ''}`} role="status">
    {focusedEdge ? <>
      <strong title={`${focusedEdge.src} → ${focusedEdge.dst}`}>{focusedEdge.src} → {focusedEdge.dst}</strong>
      <span>{money.format(focusedEdge.sum_kzt)} ₸ · Операций: {formatCount(focusedEdge.n_tx)}</span>
      {isPinned && <button type="button" className="graph-inspector-close" onClick={() => {
        setPinnedEdge(null)
        setHoveredEdge(null)
        setHoveredNode(null)
        const select = document.getElementById('graph-edge-select')
        const list = select?.closest('details')
        if (list?.open) select?.focus()
        else list?.querySelector('summary')?.focus()
      }}>Снять выделение связи</button>}
    </> : focusedNode && <>
      <strong>gid {focusedNode.gid}</strong>
      <span>{roleLabel[focusedNode.role]}</span>
    </>}
  </div>

  return <>
    {neighborhood && !waitingForNode && <div className="graph-toolbar">
      {!showAll && neighborhood.totalCounterparties > 20 && <span>20 крупнейших контрагентов по сумме переводов</span>}
      {neighborhood.totalCounterparties > 20 && <button type="button" onClick={() => {
        setExpandedGid(showAll ? null : selectedGid)
        setPinnedEdge(null)
        setHoveredEdge(null)
        setHoveredNode(null)
      }}>
        {showAll ? 'Только 20 крупнейших' : 'Показать всех'}
      </button>}
      <span className="graph-directions">Входящие — слева · исходящие — справа · в обе стороны — снизу</span>
    </div>}
    <div className="graph-wrap">
      {waitingForNode
        ? <div className="graph-wait" role="status">Обновляем окрестность выбранного узла…</div>
        : <div className="graph-canvas" ref={container} role="img" aria-label={`Схема сети: ${visibleNodes.length} узлов, ${visibleEdges.length} направленных связей. Узлы можно выбрать нажатием; полный список узлов и переводов доступен ниже графа.`} />}
      {!waitingForNode && <>
        <div className="graph-controls" aria-label="Масштаб графа">
          <button type="button" onClick={() => zoomBy(1.3)} aria-label="Увеличить граф">+</button>
          <button type="button" onClick={() => zoomBy(1 / 1.3)} aria-label="Уменьшить граф">−</button>
          <button type="button" onClick={() => { if (instance.current) fitGraph(instance.current) }} aria-label="Показать весь граф">⌖</button>
        </div>
        {!isPinned && inspector}
        <div className="graph-legend" aria-label="Цвета ролей">
          {roles.map((role) => <span key={role}><i style={{ backgroundColor: roleColor[role] }} />{roleLabel[role]}</span>)}
          <span><i className="seed-mark" />Исходный клиент</span>
        </div>
      </>}
    </div>
    {!waitingForNode && <div className="graph-caption">
      <span>Показано {formatCount(visibleNodes.length)} из {formatCount(data.total_nodes)} узлов · {formatCount(visibleEdges.length)} из {formatCount(data.total_edges)} связей</span>
      {data.truncated && <strong>Область ограничена 120 узлами; расчёты и поиск gid доступны для всей сети.</strong>}
    </div>}
    {!waitingForNode && <details className="graph-access">
      <summary>Узлы и связи списком</summary>
      <div className="graph-access-fields">
        <div>
          <label htmlFor="graph-node-select">Выбрать узел</label>
          <select
            id="graph-node-select"
            value={selectedGid && nodeById.has(selectedGid) ? selectedGid : ''}
            onChange={(event) => { if (event.target.value) onSelect(event.target.value) }}
          >
            <option value="">Выберите узел</option>
            {visibleNodes.map((node) => <option key={node.gid} value={node.gid}>
              gid {node.gid} · {roleLabel[node.role]}
            </option>)}
          </select>
        </div>
        <div>
          <label htmlFor="graph-edge-select">Выбрать перевод</label>
          <select
            id="graph-edge-select"
            value={pinnedEdge && edgeById.has(pinnedEdge) ? pinnedEdge : ''}
            disabled={visibleEdges.length === 0}
            onChange={(event) => {
              setPinnedEdge(event.target.value || null)
              setHoveredEdge(null)
              setHoveredNode(null)
            }}
          >
            <option value="">{visibleEdges.length === 0 ? 'В этой области нет переводов' : 'Выберите перевод'}</option>
            {visibleEdges.map((edge) => <option key={edgeId(edge)} value={edgeId(edge)}>
              {edge.src} → {edge.dst} · {money.format(edge.sum_kzt)} ₸ · Операций: {formatCount(edge.n_tx)}
            </option>)}
          </select>
        </div>
      </div>
    </details>}
    {!waitingForNode && isPinned && inspector}
  </>
}
