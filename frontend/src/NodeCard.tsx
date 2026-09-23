import {
  type LinkData,
  type NodeDetail,
  type Role,
  formatCount,
  formatMoney,
  formatMoneyCompact,
  formatPercent,
  formatScore,
  roleLabel,
} from './api'
import RoleTag from './RoleTag'

const preciseMoney = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 })
const pagerankNumber = new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 6, maximumFractionDigits: 6 })
const roleWeightNumber = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 })
const passThroughNumber = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 })

const priorityRoleWeight: Record<Role, number> = {
  coordinator: 1,
  consolidator: 0.85,
  distributor: 0.8,
  transit: 0.65,
  terminal: 0.35,
  peripheral: 0.15,
}

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
        <p>Сервер ранжирует узлы для проверки по всей выборке. Оборот, число связей и PageRank переводятся в процентильные ранги.</p>
        <dl>
          <div><dt>Оборот · вес 35%</dt><dd>{preciseMoney.format(node.in_kzt + node.out_kzt)} ₸</dd></div>
          <div>
            <dt>Связи · вес 25%</dt>
            <dd>{formatCount(node.in_degree + node.out_degree)} <small>({formatCount(node.in_degree)} вход. + {formatCount(node.out_degree)} исх.)</small></dd>
          </div>
          <div><dt>PageRank · вес 25%</dt><dd>{pagerankNumber.format(node.pagerank)}</dd></div>
          <div><dt>Роль · вес 15%</dt><dd>{roleLabel[node.role]} · {roleWeightNumber.format(priorityRoleWeight[node.role])}</dd></div>
        </dl>
        <p className="priority-method-formula">Скор = 0,35 × процентиль оборота + 0,25 × процентиль связей + 0,25 × процентиль PageRank + 0,15 × вес роли.</p>
        <p>Это порядок аналитической проверки, а не вероятность нарушения.</p>
      </div>
    </details>

    <section className="detail-section">
      <h3>Основание роли</h3>
      <p className="evidence">{node.evidence}</p>
    </section>

    <section className="detail-section">
      <h3>Потоки в выборке</h3>
      <div className="flow-stats">
        <div>
          <span>Получено</span>
          <strong>{formatMoney(node.in_kzt)}</strong>
          <small>{formatCount(node.in_degree)} отправителей · {formatCount(node.in_tx)} операций</small>
        </div>
        <div>
          <span>Отправлено</span>
          <strong>{formatMoney(node.out_kzt)}</strong>
          <small>{formatCount(node.out_degree)} получателей · {formatCount(node.out_tx)} операций</small>
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
        <summary>Ещё {formatCount(links.length - 5)} связей</summary>
        {renderLinks(sorted.slice(5))}
      </details>}
    </>}
  </section>
}
