import { useEffect, useState } from 'react'

import { api } from '@/api'
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  ErrorState,
  Input,
  Loading,
  Modal,
  Select,
  StatTile,
  Table,
} from '@/components/ui'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { formatDate, formatDateTime, formatMoney, today } from '@/lib/format'

const INVOICE_TONES = { open: 'warn', partial: 'info', paid: 'ok', void: 'neutral' }

/**
 * One owner group's subscription account, as the developer runs it: the
 * agreed cycle and price, time-limited discounts (a percentage and/or a fixed
 * amount), invoices, cash and bank-transfer payments, and a late-payment note
 * recorded by hand — lateness is a judgement here, not a rule.
 */
export function TenantBilling({ tenant }) {
  const { platformUser } = useAuth()
  const canChange = platformUser?.role === 'super'
  const toast = useToast()
  const { data, loading, error, reload } = useAsync(() => api.platform.billing(tenant), [tenant])
  const [terms, setTerms] = useState(null)
  const [discount, setDiscount] = useState({ percent: '', amount: '', starts_on: today(), ends_on: '', reason: '' })
  const [payment, setPayment] = useState(null) // the invoice being paid, or {} for an unallocated payment
  const [voiding, setVoiding] = useState(null)
  const [late, setLate] = useState('')

  useEffect(() => {
    if (data) {
      setTerms({
        cycle: data.terms.cycle,
        custom_price: data.terms.custom_price ?? '',
        next_invoice_on: data.terms.next_invoice_on ?? '',
        notes: data.terms.notes ?? '',
      })
    }
  }, [data])

  const act = useMutation((fn) => fn())
  const run = async (fn, message) => {
    try {
      await act.run(fn)
      toast.success(message)
      reload()
      return true
    } catch (caught) {
      toast.error(caught.message)
      return false
    }
  }

  if (loading && !data) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />

  const { account } = data

  return (
    <section id="billing" className="ui-stack">
      <h2 className="tenant-billing__title">الاشتراك والمدفوعات</h2>
      <div className="ui-grid ui-grid--3">
        <StatTile label="المفوتر" value={formatMoney(account.invoiced)} />
        <StatTile label="المدفوع" value={formatMoney(account.paid)} />
        <StatTile
          label="المتبقي"
          value={formatMoney(account.balance)}
          tone={Number(account.balance) > 0 ? 'warn' : 'neutral'}
          hint={account.overdue_invoices ? `${account.overdue_invoices} فاتورة تجاوزت الاستحقاق` : undefined}
        />
      </div>

      {account.late && (
        <div className="integrations__missing" role="status">
          مسجَّل متأخر السداد منذ {formatDate(account.late.since)}: {account.late.note}
          {canChange && (
            <Button size="sm" variant="ghost" onClick={() => run(() => api.platform.clearLate(tenant), 'أُزيل التأخير')}>
              إزالة
            </Button>
          )}
        </div>
      )}

      <div className="ui-grid ui-grid--2" style={{ alignItems: 'start' }}>
        <Card>
          <CardHeader
            title="شروط الاشتراك"
            subtitle={
              data.period_price_error
                ?? `سعر الفترة: ${formatMoney(data.period_price)} — ${data.period_description}`
            }
          />
          <CardBody>
            {terms && (
              <div className="integrations__controls">
                <Select
                  id="terms-cycle"
                  label="الدورة"
                  options={[
                    { value: 'monthly', label: 'شهري' },
                    { value: 'yearly', label: 'سنوي' },
                  ]}
                  value={terms.cycle}
                  disabled={!canChange}
                  onChange={(event) => setTerms({ ...terms, cycle: event.target.value })}
                />
                <Input
                  id="terms-price"
                  label="سعر متفق عليه للفترة"
                  hint="فارغ = سعر الباقة"
                  type="number"
                  min="0"
                  step="0.01"
                  value={terms.custom_price}
                  disabled={!canChange}
                  onChange={(event) => setTerms({ ...terms, custom_price: event.target.value })}
                />
                <Input
                  id="terms-next"
                  label="تاريخ الفاتورة القادمة"
                  type="date"
                  value={terms.next_invoice_on}
                  disabled={!canChange}
                  onChange={(event) => setTerms({ ...terms, next_invoice_on: event.target.value })}
                />
                <Input
                  id="terms-notes"
                  label="ملاحظات"
                  value={terms.notes}
                  disabled={!canChange}
                  onChange={(event) => setTerms({ ...terms, notes: event.target.value })}
                />
              </div>
            )}
            {canChange && (
              <div className="ui-row integrations__actions">
                <Button variant="primary" loading={act.submitting}
                  onClick={() => run(() => api.platform.setTerms(tenant, terms), 'تم حفظ الشروط')}>
                  حفظ الشروط
                </Button>
                <Button loading={act.submitting}
                  onClick={() => run(() => api.platform.issueInvoice(tenant, {}), 'صدرت الفاتورة')}>
                  إصدار فاتورة الفترة القادمة الآن
                </Button>
              </div>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="الخصومات" subtitle="لفترة محددة — نسبة، أو مبلغ ثابت، أو الاثنان (النسبة أولاً)" />
          <CardBody>
            <Table
              rows={data.discounts}
              rowKey={(row) => row.id}
              empty={{ title: 'لا توجد خصومات' }}
              columns={[
                {
                  key: 'value', header: 'الخصم',
                  render: (row) => [row.percent && `${Number(row.percent)}%`, row.amount && formatMoney(row.amount)]
                    .filter(Boolean).join(' + '),
                },
                {
                  key: 'period', header: 'الفترة',
                  render: (row) => `${formatDate(row.starts_on)} ← ${formatDate(row.ends_on)}`,
                },
                {
                  key: 'state', header: '',
                  render: (row) => (row.active ? <Badge tone="ok">سارٍ</Badge>
                    : row.expired ? <Badge>منتهٍ</Badge> : <Badge tone="info">قادم</Badge>),
                },
                { key: 'reason', header: 'السبب', render: (row) => row.reason || '—' },
                {
                  key: 'remove', header: '',
                  render: (row) => canChange && (
                    <Button size="sm" variant="ghost"
                      onClick={() => run(() => api.platform.removeDiscount(tenant, row.id), 'حُذف الخصم')}>
                      حذف
                    </Button>
                  ),
                },
              ]}
            />
            {canChange && (
              <>
                <div className="integrations__controls">
                  <Input id="discount-percent" label="نسبة %" type="number" min="0" max="100" step="0.01"
                    value={discount.percent} onChange={(e) => setDiscount({ ...discount, percent: e.target.value })} />
                  <Input id="discount-amount" label="مبلغ ثابت" type="number" min="0" step="0.01"
                    value={discount.amount} onChange={(e) => setDiscount({ ...discount, amount: e.target.value })} />
                  <Input id="discount-from" label="من" type="date"
                    value={discount.starts_on} onChange={(e) => setDiscount({ ...discount, starts_on: e.target.value })} />
                  <Input id="discount-to" label="إلى" type="date"
                    value={discount.ends_on} onChange={(e) => setDiscount({ ...discount, ends_on: e.target.value })} />
                  <Input id="discount-reason" label="السبب"
                    value={discount.reason} onChange={(e) => setDiscount({ ...discount, reason: e.target.value })} />
                </div>
                <div className="ui-row integrations__actions">
                  <Button
                    loading={act.submitting}
                    disabled={(!discount.percent && !discount.amount) || !discount.ends_on}
                    onClick={async () => {
                      if (await run(() => api.platform.addDiscount(tenant, discount), 'أُضيف الخصم')) {
                        setDiscount({ percent: '', amount: '', starts_on: today(), ends_on: '', reason: '' })
                      }
                    }}
                  >
                    إضافة خصم
                  </Button>
                </div>
              </>
            )}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="الفواتير"
          actions={canChange && <Button size="sm" onClick={() => setPayment({})}>تسجيل دفعة بدون فاتورة</Button>}
        />
        <CardBody flush>
          <Table
            rows={data.invoices}
            rowKey={(row) => row.id}
            empty={{ title: 'لم تصدر فواتير بعد' }}
            columns={[
              { key: 'number', header: 'الرقم', render: (row) => <span dir="ltr">{row.number}</span> },
              {
                key: 'period', header: 'الفترة',
                render: (row) => `${formatDate(row.period_start)} ← ${formatDate(row.period_end)}`,
              },
              { key: 'base_amount', header: 'القيمة', numeric: true, render: (row) => formatMoney(row.base_amount) },
              {
                key: 'discount_amount', header: 'الخصم', numeric: true,
                render: (row) => (Number(row.discount_amount) ? formatMoney(row.discount_amount) : '—'),
              },
              { key: 'total', header: 'الإجمالي', numeric: true, render: (row) => <strong>{formatMoney(row.total)}</strong> },
              { key: 'remaining', header: 'المتبقي', numeric: true, render: (row) => formatMoney(row.remaining) },
              { key: 'due_on', header: 'الاستحقاق', render: (row) => formatDate(row.due_on) },
              {
                key: 'status', header: 'الحالة',
                render: (row) => (
                  <div className="ui-row">
                    <Badge tone={INVOICE_TONES[row.status]}>{row.status_label}</Badge>
                    {row.overdue && <Badge tone="urgent">متأخرة</Badge>}
                  </div>
                ),
              },
              {
                key: 'actions', header: '',
                render: (row) => canChange && ['open', 'partial'].includes(row.status) && (
                  <div className="ui-row">
                    <Button size="sm" variant="primary" onClick={() => setPayment(row)}>تسجيل دفعة</Button>
                    {row.status === 'open' && (
                      <Button size="sm" variant="ghost" onClick={() => setVoiding({ invoice: row, reason: '' })}>
                        إلغاء
                      </Button>
                    )}
                  </div>
                ),
              },
            ]}
          />
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="المدفوعات" />
        <CardBody flush>
          <Table
            rows={data.payments}
            rowKey={(row) => row.id}
            empty={{ title: 'لا توجد مدفوعات' }}
            columns={[
              { key: 'paid_at', header: 'التاريخ', render: (row) => formatDateTime(row.paid_at) },
              { key: 'amount', header: 'المبلغ', numeric: true, render: (row) => formatMoney(row.amount) },
              {
                key: 'method', header: 'الطريقة',
                render: (row) => row.method_label + (row.mode === 'test' ? ' (تجريبي)' : ''),
              },
              { key: 'invoice', header: 'الفاتورة', render: (row) => row.invoice ?? '—' },
              { key: 'reference', header: 'المرجع', render: (row) => <span dir="ltr">{row.reference || '—'}</span> },
              {
                key: 'status', header: 'الحالة',
                render: (row) => (
                  <Badge tone={row.status === 'confirmed' ? 'ok' : row.status === 'failed' ? 'urgent' : 'warn'}>
                    {row.status_label}
                  </Badge>
                ),
              },
              { key: 'recorded_by', header: 'سجّلها', render: (row) => row.recorded_by ?? 'البوابة' },
            ]}
          />
        </CardBody>
      </Card>

      {canChange && !account.late && (
        <Card>
          <CardHeader title="تسجيل تأخر في السداد" subtitle="ملاحظة يسجلها المطوّر؛ لا تُوقف الاشتراك تلقائياً" />
          <CardBody>
            <div className="ui-row" style={{ alignItems: 'flex-end' }}>
              <div style={{ flex: 1 }}>
                <Input id="late-note" label="الملاحظة" value={late} onChange={(e) => setLate(e.target.value)} />
              </div>
              <Button
                loading={act.submitting}
                onClick={async () => {
                  if (await run(() => api.platform.markLate(tenant, late), 'سُجّل التأخير')) setLate('')
                }}
              >
                تسجيل
              </Button>
            </div>
          </CardBody>
        </Card>
      )}

      <PaymentModal
        invoice={payment}
        onClose={() => setPayment(null)}
        onSubmit={async (body) => {
          if (await run(() => api.platform.recordPayment(tenant, body), 'سُجّلت الدفعة')) setPayment(null)
        }}
        submitting={act.submitting}
      />

      <Modal
        open={Boolean(voiding)}
        onClose={() => setVoiding(null)}
        title={`إلغاء الفاتورة ${voiding?.invoice.number ?? ''}`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setVoiding(null)}>رجوع</Button>
            <Button
              variant="danger"
              loading={act.submitting}
              disabled={!voiding?.reason}
              onClick={async () => {
                if (await run(() => api.platform.voidInvoice(voiding.invoice.id, voiding.reason), 'أُلغيت الفاتورة')) {
                  setVoiding(null)
                }
              }}
            >
              إلغاء الفاتورة
            </Button>
          </>
        }
      >
        <Input id="void-reason" label="سبب الإلغاء" required value={voiding?.reason ?? ''}
          onChange={(e) => setVoiding({ ...voiding, reason: e.target.value })} />
      </Modal>
    </section>
  )
}

function PaymentModal({ invoice, onClose, onSubmit, submitting }) {
  const [form, setForm] = useState({ method: 'cash', amount: '', reference: '', paid_at: today() })

  useEffect(() => {
    if (invoice) setForm({ method: 'cash', amount: invoice.remaining ?? '', reference: '', paid_at: today() })
  }, [invoice])

  return (
    <Modal
      open={Boolean(invoice)}
      onClose={onClose}
      title={invoice?.number ? `دفعة على ${invoice.number}` : 'دفعة بدون فاتورة'}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>إلغاء</Button>
          <Button
            variant="primary"
            loading={submitting}
            disabled={!form.amount || (form.method === 'transfer' && !form.reference)}
            onClick={() => onSubmit({ ...form, invoice: invoice?.id })}
          >
            تسجيل
          </Button>
        </>
      }
    >
      <div className="ui-stack">
        <Select
          id="payment-method"
          label="الطريقة"
          options={[
            { value: 'cash', label: 'نقدي' },
            { value: 'transfer', label: 'تحويل بنكي' },
          ]}
          value={form.method}
          onChange={(e) => setForm({ ...form, method: e.target.value })}
        />
        <Input id="payment-amount" label="المبلغ" type="number" min="0" step="0.01" required value={form.amount}
          onChange={(e) => setForm({ ...form, amount: e.target.value })} />
        <Input id="payment-reference" label="رقم التحويل / المرجع" required={form.method === 'transfer'}
          value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} />
        <Input id="payment-date" label="تاريخ الدفع" type="date" value={form.paid_at}
          onChange={(e) => setForm({ ...form, paid_at: e.target.value })} />
      </div>
    </Modal>
  )
}
