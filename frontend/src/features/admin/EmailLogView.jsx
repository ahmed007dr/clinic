import { useState } from 'react'

import { Badge, Button, Input, Modal, Pagination, Select, Table } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'
import { useDebounce } from '@/hooks/useDebounce'
import { formatDateTime } from '@/lib/format'

import './emaillog.css'

const STATUSES = [
  { value: '', label: 'كل الحالات' },
  { value: 'sent', label: 'أُرسلت' },
  { value: 'failed', label: 'فشلت' },
]

/**
 * What the system emailed: who to, what type, when, whether it left — and, on
 * opening one, the message exactly as the recipient got it, with the template
 * it came from. For checking and review.
 *
 * Shared by the clinic's own screen (Admin, Owner) and the platform's view of
 * one group (support), which differ only in the two fetchers passed in.
 * A message that carried a sign-in code or a single-use link is stored with it
 * masked, so what shows here never lets anyone sign in as the recipient.
 */
export function EmailLogView({ fetchList, fetchOne, deps = [] }) {
  const [text, setText] = useState('')
  const [kind, setKind] = useState('')
  const [status, setStatus] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(null)
  const q = useDebounce(text)

  const { data, loading, error, reload } = useAsync(
    () =>
      fetchList({
        q: q || undefined,
        kind: kind || undefined,
        status: status || undefined,
        from: from || undefined,
        to: to || undefined,
        page,
      }),
    [...deps, q, kind, status, from, to, page],
  )

  // Any change to a filter starts again from the first page.
  const filter = (setter) => (value) => {
    setter(value)
    setPage(1)
  }
  const rows = data?.results ?? []

  return (
    <>
      <div className="email-kinds" role="group" aria-label="نوع الرسالة">
        <button type="button" className="email-kinds__chip" aria-pressed={kind === ''} onClick={() => filter(setKind)('')}>
          الكل
        </button>
        {(data?.by_kind ?? []).map((entry) => (
          <button
            key={entry.kind}
            type="button"
            className="email-kinds__chip"
            aria-pressed={kind === entry.kind}
            disabled={entry.count === 0 && kind !== entry.kind}
            onClick={() => filter(setKind)(kind === entry.kind ? '' : entry.kind)}
          >
            {entry.label} ({entry.count})
          </button>
        ))}
      </div>

      <div className="email-filters">
        <Input
          label="البريد أو العنوان"
          type="search"
          dir="ltr"
          value={text}
          placeholder="name@example.com"
          onChange={(event) => filter(setText)(event.target.value)}
        />
        <Select
          label="الحالة"
          options={STATUSES}
          value={status}
          onChange={(event) => filter(setStatus)(event.target.value)}
        />
        <Input label="من تاريخ" type="date" value={from} onChange={(event) => filter(setFrom)(event.target.value)} />
        <Input label="إلى تاريخ" type="date" value={to} onChange={(event) => filter(setTo)(event.target.value)} />
        <span className="ui-muted">
          {data ? `${data.count} رسالة` : ''}
          {data?.failed ? ` · ${data.failed} فاشلة` : ''}
        </span>
      </div>

      <Table
        rows={rows}
        loading={loading}
        error={error}
        onRetry={reload}
        rowKey={(row) => row.id}
        onRowClick={(row) => setOpen(row.id)}
        empty={{ title: 'لا توجد رسائل', message: 'لم يُرسل النظام رسائل تطابق هذا البحث.' }}
        columns={[
          { key: 'created_at', header: 'الوقت', render: (row) => formatDateTime(row.created_at) },
          { key: 'to', header: 'إلى', render: (row) => <span dir="ltr">{row.to}</span> },
          { key: 'kind_label', header: 'النوع' },
          { key: 'subject', header: 'العنوان' },
          { key: 'branch_name', header: 'العيادة', render: (row) => row.branch_name || '—' },
          {
            key: 'status',
            header: 'الحالة',
            render: (row) => <Badge tone={row.status === 'sent' ? 'ok' : 'urgent'}>{row.status_label}</Badge>,
          },
        ]}
      />
      {data && (
        <Pagination
          page={data.page}
          pages={data.pages}
          count={data.count}
          pageSize={data.page_size}
          onChange={setPage}
          loading={loading}
        />
      )}

      <EmailDialog id={open} fetchOne={fetchOne} onClose={() => setOpen(null)} />
    </>
  )
}

function EmailDialog({ id, fetchOne, onClose }) {
  const { data, loading, error } = useAsync(() => fetchOne(id), [id], { skip: !id })

  return (
    <Modal
      open={Boolean(id)}
      onClose={onClose}
      title={data?.subject ?? 'رسالة'}
      size="wide"
      footer={<Button onClick={onClose}>إغلاق</Button>}
    >
      {loading && <p className="ui-muted">جارٍ التحميل…</p>}
      {error && <p role="alert">{error.message}</p>}
      {data && (
        <>
          <dl className="email-meta">
            <dt>إلى</dt>
            <dd dir="ltr">{data.to}</dd>
            <dt>من</dt>
            <dd dir="ltr">{data.from || '—'}</dd>
            <dt>الوقت</dt>
            <dd>{formatDateTime(data.created_at)}</dd>
            <dt>النوع</dt>
            <dd>{data.kind_label}</dd>
            <dt>الحالة</dt>
            <dd>
              <Badge tone={data.status === 'sent' ? 'ok' : 'urgent'}>{data.status_label}</Badge>
              {data.error ? ` (${data.error})` : ''}
            </dd>
            <dt>القالب</dt>
            <dd dir="ltr">{data.template || 'نص مباشر — بلا قالب'}</dd>
          </dl>
          {data.is_html ? (
            // sandbox="" is the strictest setting: nothing in the message can run.
            <iframe className="email-frame" title="نص الرسالة" sandbox="" srcDoc={data.body} />
          ) : (
            <pre className="email-body">{data.body}</pre>
          )}
        </>
      )}
    </Modal>
  )
}
