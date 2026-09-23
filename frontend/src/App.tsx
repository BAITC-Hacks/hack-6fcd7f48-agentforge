import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import Graph from './Graph'
import NodeCard from './NodeCard'
import RoleTag from './RoleTag'
import { initialView, type View } from './selection'
import {
  ApiError, type ClusterData, type GraphData, type NodeDetail, type NodeList,
  type Role, type SummaryData, formatCount, formatMoneyCompact,
  getJson, roleLabel, roles, safeMessage, formatScore,
} from './api'

type Remote<T> = { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; data: T }

const initialParams = new URLSearchParams(window.location.search)
const initialGid = initialParams.get('gid') || null
const initialCluster = initialParams.get('cluster')
const initialRole = initialParams.get('role')
const requestedView = initialParams.get('view')
const parsedInitialCluster = initialCluster !== null && /^\d+$/.test(initialCluster) ? Number(initialCluster) : null

const period = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric', timeZone: 'UTC' })
const day = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', timeZone: 'UTC' })

function Score({ value }: { value: number }) {
  return <span className="score" aria-label={`Приоритетный скор ${formatScore(value)} из 1`}>
    <span>{formatScore(value)}</span>
    <i style={{ width: `${Math.max(0, Math.min(100, value * 100))}%` }} />
  </span>
}

function StatusMessage({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="status-message" role="status">
    <p>{message}</p>
    {retry && <button type="button" className="text-action" onClick={retry}>Повторить запрос</button>}
  </div>
}

export default function App() {
  const [selectedGid, setSelectedGid] = useState<string | null>(initialGid)
  const [view, setView] = useState<View>(initialView(requestedView, initialGid, parsedInitialCluster))
  const [cluster, setCluster] = useState<number | null>(parsedInitialCluster)
  const [role, setRole] = useState<Role | ''>(roles.includes(initialRole as Role) ? initialRole as Role : '')
  const [search, setSearch] = useState('')
  const [searchError, setSearchError] = useState('')
  const [searching, setSearching] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [summary, setSummary] = useState<Remote<SummaryData>>({ status: 'loading' })
  const [clusters, setClusters] = useState<Remote<ClusterData[]>>({ status: 'loading' })
  const [list, setList] = useState<Remote<NodeList>>({ status: 'loading' })
  const [graph, setGraph] = useState<Remote<GraphData>>({ status: 'loading' })
  const [detail, setDetail] = useState<Remote<NodeDetail> | null>(null)
  const searchErrorId = useId()
  const searchSequence = useRef(0)
  const graphGid = view === 'node' ? selectedGid : null
  const graphCluster = view === 'cluster' ? cluster : null

  useEffect(() => {
    const params = new URLSearchParams()
    if (selectedGid) params.set('gid', selectedGid)
    if (cluster !== null) params.set('cluster', String(cluster))
    if (role) params.set('role', role)
    if (view !== 'overview') params.set('view', view)
    const query = params.toString()
    window.history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}`)
  }, [selectedGid, cluster, role, view])

  useEffect(() => {
    const controller = new AbortController()
    setSummary({ status: 'loading' })
    setClusters({ status: 'loading' })
    getJson<SummaryData>('/summary', controller.signal).then((data) => setSummary({ status: 'ready', data })).catch((error) => {
      if (!controller.signal.aborted) setSummary({ status: 'error', message: safeMessage(error) })
    })
    getJson<{ items: ClusterData[] }>('/clusters', controller.signal).then((data) => setClusters({ status: 'ready', data: data.items })).catch((error) => {
      if (!controller.signal.aborted) setClusters({ status: 'error', message: safeMessage(error) })
    })
    return () => controller.abort()
  }, [refresh])

  useEffect(() => {
    const controller = new AbortController()
    const params = new URLSearchParams({ limit: '40', offset: '0' })
    if (role) params.set('role', role)
    if (cluster !== null) params.set('cluster_id', String(cluster))
    setList({ status: 'loading' })
    getJson<NodeList>(`/nodes?${params}`, controller.signal).then((data) => {
      setList({ status: 'ready', data })
      const firstGid = data.items[0]?.gid
      if (firstGid) setSelectedGid((current) => current ?? firstGid)
    }).catch((error) => {
      if (!controller.signal.aborted) setList({ status: 'error', message: safeMessage(error) })
    })
    return () => controller.abort()
  }, [role, cluster, refresh])

  useEffect(() => {
    const controller = new AbortController()
    const params = new URLSearchParams({ limit: '120' })
    if (graphGid) params.set('gid', graphGid)
    else if (graphCluster !== null) params.set('cluster_id', String(graphCluster))
    setGraph({ status: 'loading' })
    getJson<GraphData>(`/graph?${params}`, controller.signal).then((data) => setGraph({ status: 'ready', data })).catch((error) => {
      if (!controller.signal.aborted) setGraph({ status: 'error', message: safeMessage(error) })
    })
    return () => controller.abort()
  }, [graphGid, graphCluster, refresh])

  useEffect(() => {
    if (!selectedGid) { setDetail(null); return }
    const controller = new AbortController()
    setDetail({ status: 'loading' })
    getJson<NodeDetail>(`/nodes/${encodeURIComponent(selectedGid)}`, controller.signal).then((data) => setDetail({ status: 'ready', data })).catch((error) => {
      if (!controller.signal.aborted) setDetail({ status: 'error', message: safeMessage(error) })
    })
    return () => controller.abort()
  }, [selectedGid, refresh])

  function cancelPendingSearch() {
    searchSequence.current += 1
    setSearching(false)
  }

  function chooseNode(gid: string) {
    cancelPendingSearch()
    setSearch('')
    setSelectedGid(gid)
    setView('node')
    setSearchError('')
  }

  async function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const gid = search.trim()
    const sequence = ++searchSequence.current
    if (!/^-?\d+$/.test(gid)) {
      setSearching(false)
      setSearchError('Введите числовой gid клиента.')
      return
    }
    setSearchError('')
    setSearching(true)
    try {
      await getJson<NodeDetail>(`/nodes/${encodeURIComponent(gid)}`)
      if (sequence === searchSequence.current) chooseNode(gid)
    } catch (error) {
      if (sequence === searchSequence.current) {
        setSearchError(error instanceof ApiError && error.status === 404
          ? `Клиент ${gid} не найден в выгрузке.`
          : safeMessage(error))
      }
    } finally {
      if (sequence === searchSequence.current) setSearching(false)
    }
  }

  function selectCluster(value: string) {
    cancelPendingSearch()
    const next = value === '' ? null : Number(value)
    setCluster(next)
    setView(next === null ? 'overview' : 'cluster')
  }

  function selectView(next: View) {
    cancelPendingSearch()
    setView(next)
  }

  function resetFilters() {
    cancelPendingSearch()
    setRole('')
    setCluster(null)
    setView(selectedGid ? 'node' : 'overview')
  }

  const summaryData = summary.status === 'ready' ? summary.data : null
  const graphData = graph.status === 'ready' ? graph.data : null
  const detailData = detail?.status === 'ready' && detail.data.node.gid === selectedGid ? detail.data : null
  const clusterForView = cluster ?? detailData?.node.cluster_id ?? null
  const currentCluster = clusters.status === 'ready' ? clusters.data.find((item) => item.cluster_id === cluster) : undefined
  const outsideFilters = detailData && ((role && detailData.node.role !== role)
    || (cluster !== null && detailData.node.cluster_id !== cluster))

  return <>
    <a className="skip-link" href="#main">К рабочей области</a>
    <div className="app-shell">
      <header className="app-header">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true"><span /><span /><span /></div>
          <div>
            <h1>Граф денег</h1>
            <p>Анализ обезличенной сети переводов</p>
          </div>
        </div>
        <div className="header-context">
          <span className="period-label">{summaryData ? period.format(new Date(`${summaryData.period_start}T00:00:00Z`)) : 'Июль 2026'}</span>
          {summaryData && <span>
            {formatCount(summaryData.n_nodes)} клиентов · {formatCount(summaryData.n_edges)} связей
          </span>}
        </div>
        <details className="exports">
          <summary>Скачать CSV</summary>
          <nav aria-label="Экспорт результатов">
            <a href="/api/exports/nodes_roles.csv" download>Роли узлов</a>
            <a href="/api/exports/clusters.csv" download>Кластеры</a>
            <a href="/api/exports/top_nodes.csv" download>Приоритеты</a>
          </nav>
        </details>
      </header>

      <nav className="compact-nav" aria-label="Разделы рабочей области">
        <a href="#search-title">Поиск</a>
        <a href="#graph-title">Граф</a>
        <a href="#client-card">Карточка</a>
      </nav>
      <p className="sr-only selection-status" role="status" aria-atomic="true">
        {detailData ? `Карточка клиента ${detailData.node.gid} загружена. ${roleLabel[detailData.node.role]}.` : ''}
      </p>

      <main id="main" className="workspace" tabIndex={-1}>
        <aside className="left-panel" aria-label="Поиск и приоритеты">
          <section className="search-section" aria-labelledby="search-title">
            <div className="section-heading">
              <h2 id="search-title" tabIndex={-1}>Найти клиента</h2>
            </div>
            <form className="search-form" onSubmit={submitSearch}>
              <label className="sr-only" htmlFor="gid-search">Идентификатор клиента gid</label>
              <input
                id="gid-search"
                name="gid"
                type="text"
                inputMode="numeric"
                autoComplete="off"
                spellCheck={false}
                placeholder="Введите gid…"
                value={search}
                onChange={(event) => {
                  cancelPendingSearch()
                  setSearch(event.target.value)
                  setSearchError('')
                }}
                aria-describedby={searchError ? searchErrorId : undefined}
                aria-invalid={Boolean(searchError)}
              />
              <button type="submit" disabled={searching}>{searching ? 'Поиск…' : 'Найти'}</button>
            </form>
            {searchError && <p className="field-error" id={searchErrorId} role="alert">{searchError}</p>}
            {detailData && <p className="search-result">
              <a href="#node-card-title" aria-label={`Открыть карточку клиента ${detailData.node.gid}`}>
                Карточка <span translate="no">…{detailData.node.gid.slice(-7)}</span> →
              </a>
            </p>}
          </section>

          <section className="priority-section" aria-labelledby="priority-title">
            <div className="section-heading">
              <h2 id="priority-title">Приоритет проверки</h2>
              {list.status === 'ready' && <span>{formatCount(list.data.total)}</span>}
            </div>
            <p className="section-note">Порядок проверки, не вероятность нарушения.</p>
            <div className="filter-row">
              <label htmlFor="role-filter">Роль в списке</label>
              <select id="role-filter" value={role} onChange={(event) => {
                cancelPendingSearch()
                setRole(event.target.value as Role | '')
              }}>
                <option value="">Все роли</option>
                {roles.map((item) => <option key={item} value={item}>{roleLabel[item]}</option>)}
              </select>
            </div>
            <div className="filter-row">
              <label htmlFor="cluster-filter">Кластер</label>
              <select id="cluster-filter" value={cluster ?? ''} onChange={(event) => selectCluster(event.target.value)}>
                <option value="">Все кластеры</option>
                {clusters.status === 'ready' && clusters.data.map((item) => <option key={item.cluster_id} value={item.cluster_id}>
                  Кластер {item.cluster_id} · {formatCount(item.n_nodes)}
                </option>)}
              </select>
            </div>
            {list.status === 'loading' && <StatusMessage message="Загружаем приоритеты…" />}
            {list.status === 'error' && <StatusMessage message={list.message} retry={() => setRefresh((value) => value + 1)} />}
            {list.status === 'ready' && (list.data.items.length === 0
              ? <StatusMessage message="По этим фильтрам клиентов нет. Выберите другую роль или кластер." />
              : <>
                <ol className="priority-list">
                  {list.data.items.map((node) => <li key={node.gid}>
                    <button
                      type="button"
                      className={`priority-item ${selectedGid === node.gid ? 'is-active' : ''}`}
                      onClick={() => chooseNode(node.gid)}
                      aria-current={selectedGid === node.gid ? 'true' : undefined}
                    >
                      <span className="priority-main">
                        <strong title={node.gid}>{node.gid}</strong>
                        <RoleTag role={node.role} />
                        <span className="priority-evidence" title={node.evidence}>{node.evidence}</span>
                      </span>
                      <Score value={node.priority_score} />
                    </button>
                  </li>)}
                </ol>
                {list.data.total > list.data.items.length && <p className="list-footnote">
                  Первые {list.data.items.length} из {formatCount(list.data.total)} · остальные доступны через поиск.
                </p>}
              </>)}
          </section>
        </aside>

        <section className="center-panel" aria-labelledby="graph-title">
          <div className="graph-heading">
            <div>
              <h2 id="graph-title" tabIndex={-1}>Направление переводов</h2>
            </div>
            <div className="view-tabs" role="group" aria-label="Область графа">
              <button type="button" className={view === 'overview' ? 'active' : ''} onClick={() => selectView('overview')} aria-pressed={view === 'overview'}>
                Обзор
              </button>
              <button type="button" className={view === 'cluster' ? 'active' : ''} onClick={() => clusterForView !== null && selectCluster(String(clusterForView))} aria-pressed={view === 'cluster'} disabled={clusterForView === null} title={clusterForView !== null ? `Открыть кластер ${clusterForView}` : 'Сначала выберите клиента или кластер'}>
                Кластер
              </button>
              <button type="button" className={view === 'node' ? 'active' : ''} onClick={() => selectedGid && selectView('node')} aria-pressed={view === 'node'} disabled={!selectedGid}>
                Окрестность
              </button>
            </div>
          </div>
          {view === 'cluster' && currentCluster && <div className="cluster-summary">
            <div>
              <strong>Кластер {currentCluster.cluster_id}</strong>
              <span>{formatCount(currentCluster.n_nodes)} узлов · {formatCount(currentCluster.n_seed)} исходных клиентов · {formatMoneyCompact(currentCluster.sum_kzt_internal)} внутренних переводов</span>
            </div>
            <p>{currentCluster.hypothesis}</p>
          </div>}
          {graph.status === 'loading' && <StatusMessage message="Строим видимую часть графа…" />}
          {graph.status === 'error' && <StatusMessage message={graph.message} retry={() => setRefresh((value) => value + 1)} />}
          {graphData && (graphData.nodes.length === 0
            ? <StatusMessage message="В этой области нет узлов. Вернитесь к обзору или выберите другой кластер." />
            : <Graph data={graphData} selectedGid={selectedGid} view={view} onSelect={chooseNode} />)}
          <details className="data-caveat">
            <summary>Неполная выборка: до 4-го колена</summary>
            <p>Обход включает только исходящие переводы до 4-го колена. У узлов на границе отсутствие исходящих не доказывает, что деньги остались у них. Входящие переводы исходных клиентов вне выборки не видны.</p>
          </details>
        </section>

        <aside id="client-card" className="right-panel" aria-label="Карточка выбранного клиента" tabIndex={-1}>
          {!selectedGid && <div className="detail-empty">
            <span className="detail-empty-symbol" aria-hidden="true">◎</span>
            <h2>Выберите узел</h2>
            <p>Нажмите узел на графе, откройте клиента из списка или найдите его по gid. Здесь появятся признаки роли и непосредственные связи.</p>
          </div>}
          {detail?.status === 'loading' && <StatusMessage message="Загружаем карточку клиента…" />}
          {detail?.status === 'error' && <StatusMessage message={detail.message} retry={() => setRefresh((value) => value + 1)} />}
          {outsideFilters && <div className="filter-context">
            <p>Выбранный клиент не входит в текущий список по фильтрам. Его карточка сохранена.</p>
            <button type="button" className="text-action" onClick={resetFilters}>Сбросить фильтры</button>
          </div>}
          {detailData && <NodeCard key={detailData.node.gid} detail={detailData} onSelect={chooseNode} />}
        </aside>
      </main>
      <footer className="app-footer">
        {summary.status === 'loading' && <span>Загружаем сводку…</span>}
        {summary.status === 'error' && <span role="alert">
          Сводка недоступна: {summary.message}{' '}
          <button type="button" className="text-action" onClick={() => setRefresh((value) => value + 1)}>Повторить</button>
        </span>}
        {summaryData && <>
          <span>Снимок: {day.format(new Date(`${summaryData.period_start}T00:00:00Z`))} — {day.format(new Date(`${summaryData.period_end}T00:00:00Z`))}</span>
          <span>{formatCount(summaryData.n_transactions)} транзакций · {formatMoneyCompact(summaryData.sum_kzt)}</span>
          <span>{formatCount(summaryData.n_components)} компонент · {formatCount(summaryData.n_isolates)} изолированных узлов</span>
        </>}
      </footer>
    </div>
  </>
}
