import { useEffect, useRef } from 'react'
import cytoscape, { type Core, type ElementDefinition, type StylesheetStyle } from 'cytoscape'
import { type GraphData, roleColor, roleLabel, roles } from './api'

interface Props {
  data: GraphData
  selectedGid: string | null
  onSelect: (gid: string) => void
}

const graphLabel = (gid: string) => gid.length > 10 ? `…${gid.slice(-7)}` : gid

const graphStyle: StylesheetStyle[] = [
  { selector: 'node', style: {
    'background-color': 'data(color)', 'label': 'data(label)', 'color': '#233d47',
    'font-size': 9, 'font-family': 'Arial, sans-serif', 'text-valign': 'bottom', 'text-margin-y': 5,
    'text-outline-width': 2, 'text-outline-color': '#ffffff',
    'width': 'data(size)', 'height': 'data(size)',
    'border-width': 2, 'border-color': '#ffffff',
  } },
  { selector: 'node[?isSeed]', style: { 'border-width': 3, 'border-color': '#203946' } },
  { selector: 'node[?selected]', style: { 'border-width': 4, 'border-color': '#132f3b', 'font-size': 11, 'font-weight': 'bold', 'z-index': 999 } },
  { selector: 'edge', style: {
    'width': 1.4, 'line-color': '#a9bac0', 'target-arrow-color': '#78919b',
    'target-arrow-shape': 'triangle', 'arrow-scale': 0.8, 'curve-style': 'bezier', 'opacity': 0.72,
  } },
  { selector: 'edge[?emphasis]', style: { 'width': 2.8, 'line-color': '#3c6474', 'target-arrow-color': '#3c6474', 'opacity': 1 } },
]

export default function Graph({ data, selectedGid, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const instance = useRef<Core | null>(null)
  const selectRef = useRef(onSelect)
  selectRef.current = onSelect

  useEffect(() => {
    if (!container.current) return
    const elements: ElementDefinition[] = [
      ...data.nodes.map((node) => ({
        data: {
          id: node.gid, label: graphLabel(node.gid), color: roleColor[node.role],
          size: 15 + Math.min(16, node.priority_score * 19), isSeed: node.is_seed,
          selected: false,
        },
      })),
      ...data.edges.map((edge, index) => ({
        data: { id: `edge-${index}`, source: edge.src, target: edge.dst, emphasis: false },
      })),
    ]
    const cy = cytoscape({
      container: container.current,
      elements,
      style: graphStyle,
      minZoom: 0.25,
      maxZoom: 3,
      layout: { name: 'cose', animate: false, fit: true, padding: 46, nodeRepulsion: () => 7000, idealEdgeLength: () => 90 },
    })
    instance.current = cy
    cy.on('tap', 'node', (event) => selectRef.current(event.target.id()))
    cy.on('mouseover', 'node', (event) => { if (container.current) container.current.title = `gid ${event.target.id()}` })
    cy.on('mouseout', 'node', () => { if (container.current) container.current.removeAttribute('title') })
    return () => { cy.destroy(); instance.current = null }
  }, [data]) // selected styling is updated separately without rerunning layout

  useEffect(() => {
    const cy = instance.current
    if (!cy) return
    cy.nodes().forEach((node) => { node.data('selected', node.id() === selectedGid); node.data('label', node.id() === selectedGid ? node.id() : graphLabel(node.id())) })
    cy.edges().forEach((edge) => { edge.data('emphasis', edge.source().id() === selectedGid || edge.target().id() === selectedGid) })
  }, [selectedGid, data])

  return <div className="graph-wrap">
    <div className="graph-canvas" ref={container} role="img" aria-label={`Схема сети: ${data.nodes.length} узлов, ${data.edges.length} направленных связей. Узлы можно выбрать нажатием. Для клавиатуры используйте список приоритетов или связи в карточке.`} />
    <div className="graph-controls" aria-label="Масштаб графа">
      <button type="button" onClick={() => instance.current?.zoom(Math.min(3, (instance.current?.zoom() ?? 1) * 1.3))} aria-label="Увеличить граф">+</button>
      <button type="button" onClick={() => instance.current?.zoom(Math.max(0.25, (instance.current?.zoom() ?? 1) / 1.3))} aria-label="Уменьшить граф">−</button>
      <button type="button" onClick={() => instance.current?.fit(undefined, 44)} aria-label="Показать весь граф">⌖</button>
    </div>
    <div className="graph-legend" aria-label="Цвета ролей">
      {roles.map((role) => <span key={role}><i style={{ backgroundColor: roleColor[role] }} />{roleLabel[role]}</span>)}
      <span><i className="seed-mark" />Исходный клиент</span>
      <span className="legend-note">Подписи сокращены; полный gid в карточке</span>
    </div>
  </div>
}
