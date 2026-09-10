import { api } from '@/api'
import { Badge, EmptyState, ErrorState, Loading } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'
import { formatDateTime, formatRelative } from '@/lib/format'

/**
 * A patient's whole history in one column, newest first.
 *
 * The server merges and orders the six record types — doing it here would mean
 * six requests and a merge that goes wrong the first time two events share a
 * timestamp. Clinical entries are simply absent for a user without clinical
 * access; there is nothing to hide in the client because nothing was sent.
 */

const KINDS = {
  visit: { label: 'زيارة', icon: '🩺', tone: 'primary' },
  prescription: { label: 'روشتة', icon: '℞', tone: 'info' },
  procedure: { label: 'إجراء', icon: '⚕', tone: 'info' },
  lab: { label: 'تحليل', icon: '🧪', tone: 'neutral' },
  session: { label: 'جلسة', icon: '📋', tone: 'primary' },
  appointment: { label: 'موعد', icon: '📅', tone: 'neutral' },
  payment: { label: 'دفعة', icon: '💵', tone: 'ok' },
}

// The timeline sends the flag's code; the screen shows the model's Arabic label
// for it (medical.LabResult.Flag), never the raw English word.
const LAB_FLAG_LABELS = {
  normal: 'طبيعي',
  abnormal: 'غير طبيعي',
  critical: 'حرج',
}

const LAB_FLAG_TONES = {
  critical: 'urgent',
  abnormal: 'urgent',
  high: 'warn',
  low: 'warn',
  normal: 'ok',
}

export function PatientTimeline({ uuid }) {
  const { data, loading, error, reload } = useAsync(
    () => api.patients.timeline(uuid),
    [uuid],
  )

  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />

  const entries = data?.entries ?? []

  if (entries.length === 0) {
    return (
      <EmptyState
        icon="🗓"
        title="لا يوجد سجل بعد"
        message="ستظهر هنا المواعيد والزيارات والدفعات فور تسجيلها."
      />
    )
  }

  return (
    <ol className="timeline">
      {entries.map((entry, index) => {
        const kind = KINDS[entry.kind] ?? { label: entry.kind, icon: '•', tone: 'neutral' }
        return (
          <li className="timeline__item" key={`${entry.kind}-${entry.uuid}-${index}`}>
            <span className="timeline__marker" aria-hidden="true">
              {kind.icon}
            </span>

            <div className="timeline__body">
              <div className="timeline__head">
                <Badge tone={kind.tone}>{kind.label}</Badge>
                <strong className="timeline__title">{entry.title}</strong>
                {entry.flag && (
                  <Badge tone={LAB_FLAG_TONES[entry.flag] ?? 'neutral'}>
                    {LAB_FLAG_LABELS[entry.flag] ?? entry.flag}
                  </Badge>
                )}
              </div>

              {entry.detail && <p className="timeline__detail">{entry.detail}</p>}

              <div className="timeline__meta">
                <time dateTime={entry.at} title={formatDateTime(entry.at)}>
                  {formatDateTime(entry.at)}
                </time>
                <span className="ui-muted">· {formatRelative(entry.at)}</span>
                {entry.doctor && <span className="ui-muted">· {entry.doctor}</span>}
              </div>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
