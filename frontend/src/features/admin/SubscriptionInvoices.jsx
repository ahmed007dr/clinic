import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { Badge, Button, Card, CardBody, CardHeader, Input, Modal, Select, Table } from '@/components/ui'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { formatDate, formatMoney } from '@/lib/format'

const TONES = { open: 'warn', partial: 'info', paid: 'ok', void: 'neutral' }

/**
 * The group's invoices from the platform, and paying one online through the
 * platform's gateway (Paymob cards, Fawry, Vodafone Cash) when the platform
 * has turned one on. Cash and bank transfers are recorded by the platform.
 */
export function SubscriptionInvoices() {
  const toast = useToast()
  const [params, setParams] = useSearchParams()
  const { data, reload } = useAsync(() => api.subscription.invoices(), [])
  const [paying, setPaying] = useState(null)
  const [method, setMethod] = useState('')
  const [phone, setPhone] = useState('')
  const pay = useMutation(() => api.subscription.pay(paying.id, { method, phone }))

  useEffect(() => {
    const outcome = params.get('payment')
    if (!outcome) return
    if (outcome === 'ok') toast.success('تم الدفع بنجاح. شكراً لك.')
    else toast.error('لم تكتمل عملية الدفع.')
    params.delete('payment')
    setParams(params, { replace: true })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  if (!data) return null
  const methods = data.methods ?? []

  return (
    <Card>
      <CardHeader
        title="فواتير الاشتراك"
        subtitle={`المتبقي عليك: ${formatMoney(data.account.balance)}`}
      />
      <CardBody flush>
        <Table
          rows={data.invoices}
          rowKey={(row) => row.id}
          empty={{ title: 'لا توجد فواتير' }}
          columns={[
            { key: 'number', header: 'الفاتورة', render: (row) => <span dir="ltr">{row.number}</span> },
            {
              key: 'period', header: 'الفترة',
              render: (row) => `${formatDate(row.period_start)} ← ${formatDate(row.period_end)}`,
            },
            { key: 'total', header: 'الإجمالي', numeric: true, render: (row) => formatMoney(row.total) },
            { key: 'remaining', header: 'المتبقي', numeric: true, render: (row) => formatMoney(row.remaining) },
            { key: 'due_on', header: 'الاستحقاق', render: (row) => formatDate(row.due_on) },
            {
              key: 'status', header: 'الحالة',
              render: (row) => (
                <div className="ui-row">
                  <Badge tone={TONES[row.status]}>{row.status_label}</Badge>
                  {row.overdue && <Badge tone="urgent">متأخرة</Badge>}
                </div>
              ),
            },
            {
              key: 'pay', header: '',
              render: (row) => methods.length > 0 && ['open', 'partial'].includes(row.status) && (
                <Button size="sm" variant="primary" onClick={() => { setPaying(row); setMethod(methods[0].kind) }}>
                  ادفع أونلاين
                </Button>
              ),
            },
          ]}
        />
        {methods.length === 0 && data.invoices.some((i) => ['open', 'partial'].includes(i.status)) && (
          <p className="ui-muted" style={{ padding: 'var(--s3) var(--s4)', margin: 0, fontSize: 'var(--text-sm)' }}>
            للسداد نقداً أو بتحويل بنكي تواصل مع إدارة المنصة؛ تُسجَّل الدفعة على الفاتورة فور استلامها.
          </p>
        )}
      </CardBody>

      <Modal
        open={Boolean(paying)}
        onClose={() => setPaying(null)}
        title={`سداد ${paying?.number ?? ''} — ${formatMoney(paying?.remaining)}`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setPaying(null)}>إلغاء</Button>
            <Button
              variant="primary"
              loading={pay.submitting}
              disabled={!method || (method === 'vodafone_cash' && !phone)}
              onClick={async () => {
                try {
                  const { redirect_url: url } = await pay.run()
                  window.location.assign(url)
                } catch (caught) {
                  toast.error(caught.message)
                  reload()
                }
              }}
            >
              متابعة للدفع
            </Button>
          </>
        }
      >
        <div className="ui-stack">
          <Select id="pay-method" label="طريقة الدفع"
            options={methods.map((m) => ({ value: m.kind, label: m.label }))}
            value={method} onChange={(e) => setMethod(e.target.value)} />
          {method === 'vodafone_cash' && (
            <Input id="pay-phone" label="رقم محفظة فودافون كاش" dir="ltr" inputMode="tel" required
              value={phone} onChange={(e) => setPhone(e.target.value)} />
          )}
          <p className="ui-muted" style={{ margin: 0, fontSize: 'var(--text-sm)' }}>
            ستنتقل إلى صفحة بوابة الدفع الآمنة، ثم تعود إلى هنا بعد إتمام العملية.
          </p>
        </div>
      </Modal>
    </Card>
  )
}
