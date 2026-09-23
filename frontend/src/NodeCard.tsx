import {
  type LinkData,
  type NodeDetail,
  formatCount,
  formatMoney,
  formatMoneyCompact,
  formatPercent,
  formatScore,
  roleLabel,
} from './api'
import RoleTag from './RoleTag'

const signalNumber = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 6 })
const factorNumber = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 3 })
const passThroughNumber = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 })

interface Props {
  detail: NodeDetail
  onSelect: (gid: string) => void
}

export default function NodeCard({ detail, onSelect }: Props) {
  const { node, incoming, outgoing, warnings, next_steps } = detail

  return <div className="node-card">
    <div className="node-card-header">
      <p className="kicker">Карточка клиента</p>
      <h2 id="node-card-title" tabIndex={-1} title={node.gid} translate="no">gid {node.gid}</h2>
      <RoleTag role={node.role} />
    </div>

    <div className="node-flags">
      {node.is_seed && <span>Исходный клиент</span>}
      {node.boundary && <span className="flag-warn">Граница 4-го колена</span>}
      <span>Кластер {node.cluster_id}</span>
      {!node.boundary && <span>Колено {node.depth}</span>}
    </div>

    <div className="node-scores">
      <div><small>Приоритет проверки</small><strong>{formatScore(node.priority_score)}</strong></div>
      <div><small>Сила признаков роли</small><strong>{formatPercent(node.role_score)}</strong></div>
    </div>

    <details className="priority-method detail-section">
      <summary>Как рассчитан приоритет</summary>
      <div className="priority-method-body">
        <p>Приоритет основан на наблюдаемых признаках. Значения и веса расчёта:</p>
        <dl>
          {node.priority_breakdown.map((signal, index) => <div key={`${signal.label}-${index}`}>
            <dt>{signal.label}<small>Вес {formatPercent(signal.weight)}</small></dt>
            <dd>{signalNumber.format(signal.value)}<small>Нормировано {signalNumber.format(signal.normalized)} · вклад {signalNumber.format(signal.normalized * signal.weight)}</small></dd>
          </div>)}
        </dl>
        <p className="priority-method-formula">Сумма взвешенных признаков × коэффициент {factorNumber.format(node.priority_factor)}.</p>
        <p>{node.priority_reason}</p>
        <p>Это порядок аналитической проверки, а не вероятность нарушения.</p>
      </div>
    </details>

    <section className="detail-section">
      <h3>Основание роли</h3>
      <p className="evidence">{node.evidence}</p>
    </section>

    <details className="detail-section seed-paths">
      <summary>Пути от исходных клиентов · {formatCount(node.seed_source_count)}</summary>
      <div className="seed-paths-body">
        {node.is_seed && node.seed_source_count === 0
          ? <p>Это исходный клиент; путь к самому себе не учитывается.</p>
          : <p>До этого узла найдены пути от {formatCount(node.seed_source_count)} исходных клиентов.</p>}
        {node.seed_paths.length === 0
          ? !(node.is_seed && node.seed_source_count === 0) && <p>Наблюдаемых путей от исходных клиентов нет.</p>
          : <ol>{node.seed_paths.map((path, pathIndex) => <li key={pathIndex}>
            <div className="seed-path">
              {path.map((gid, stepIndex) => <span className="seed-path-step" key={`${gid}-${stepIndex}`}>
                <button type="button" onClick={() => onSelect(gid)} aria-label={`Открыть карточку клиента ${gid}`} translate="no">gid {gid}</button>
                {stepIndex < path.length - 1 && <span aria-hidden="true">→</span>}
              </span>)}
            </div>
          </li>)}</ol>}
        <p>Это наблюдаемые пути по возрастающей глубине, а не доказательство перевода одних и тех же денег.</p>
        {node.seed_source_count > node.seed_paths.length && node.seed_paths.length > 0 && <p>
          Показано {formatCount(node.seed_paths.length)} из {formatCount(node.seed_source_count)} путей.
        </p>}
      </div>
    </details>

    <section className="detail-section">
      <h3>Потоки в выборке</h3>
      <div className="flow-stats">
        <div>
          <span>Получено</span>
          <strong>{formatMoney(node.in_kzt)}</strong>
          <small>Отправителей: {formatCount(node.in_degree)} · Операций: {formatCount(node.in_tx)}</small>
        </div>
        <div>
          <span>Отправлено</span>
          <strong>{formatMoney(node.out_kzt)}</strong>
          <small>Получателей: {formatCount(node.out_degree)} · Операций: {formatCount(node.out_tx)}</small>
        </div>
      </div>
      {node.pass_through !== null && <p className="metric-note">
        Отношение отправленного к полученному в наблюдаемой сети: {passThroughNumber.format(node.pass_through)}.
      </p>}
    </section>

    {warnings.length > 0 && <section className="detail-section warnings">
      <h3>Ограничения трактовки</h3>
      <ul>{warnings.map((item, index) => <li key={index}>{item}</li>)}</ul>
    </section>}

    <ConnectionList title="Входящие связи" links={incoming} onSelect={onSelect} />
    <ConnectionList title="Исходящие связи" links={outgoing} onSelect={onSelect} />

    {next_steps.length > 0 && <details className="detail-section next-steps">
      <summary>Что проверить дальше</summary>
      <ul>{next_steps.map((item, index) => <li key={index}>{item}</li>)}</ul>
    </details>}
  </div>
}

function ConnectionList({ title, links, onSelect }: { title: string; links: LinkData[]; onSelect: (gid: string) => void }) {
  const sorted = [...links].sort((a, b) => b.sum_kzt - a.sum_kzt || a.counterparty_gid.localeCompare(b.counterparty_gid))
  const renderLinks = (items: LinkData[]) => <ul>
    {items.map((link) => <li key={`${link.src}-${link.dst}`}>
      <button type="button" onClick={() => onSelect(link.counterparty_gid)}>
        <span><strong title={link.counterparty_gid}>{link.counterparty_gid}</strong><small>{roleLabel[link.role]}</small></span>
        <span>{formatMoneyCompact(link.sum_kzt)}<small>Операций: {formatCount(link.n_tx)}</small></span>
      </button>
    </li>)}
  </ul>
  return <section className="detail-section connections">
    <h3>{title} <span>{formatCount(links.length)}</span></h3>
    {links.length === 0 ? <p className="muted">В наблюдаемой сети связей нет.</p> : <>
      {links.length > 5 && <p className="connection-order">Сначала 5 крупнейших по сумме</p>}
      {renderLinks(sorted.slice(0, 5))}
      {links.length > 5 && <details>
        <summary>Остальные связи · {formatCount(links.length - 5)}</summary>
        {renderLinks(sorted.slice(5))}
      </details>}
    </>}
  </section>
}
