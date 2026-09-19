import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { Badge, Button, Checkbox, Input, Select, APPOINTMENT_TONES } from '@/components/ui'
import { ResourceTable } from '@/components/data/ResourceTable'
import { EmailReportButton } from '@/components/data/EmailReportButton'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { formatDateTime, formatMoney } from '@/lib/format'

import { VisitDeskActions } from './VisitDeskActions'

const PAYMENT = {
  paid: { label: 'مدفوع', tone: 'ok' },
  partial: { label: 'مدفوع جزئياً', tone: 'warn' },
  unpaid: { label: 'غير مدفوع', tone: 'neutral' },
}

const STATUSES = [
  { value: 'waiting', label: 'الانتظار' },
  { value: 'entered', label: 'تم الدخول' },
  { value: 'called', label: 'تم الاتصال' },
  { value: 'quick', label: 'حجز سريع' },
  { value: 'requested', label: 'طلب من المريض' },
  { value: 'completed', label: 'مكتمل' },
  { value: 'cancelled', label: 'ملغي' },
  { value: 'no_show', label: 'لم يحضر' },
]

const SOURCES = [
  { value: 'portal', label: 'الموقع (بوابة المرضى)' },
  { value: 'reception', label: 'الاستقبال' },
  { value: 'phone', label: 'الهاتف' },
  { value: 'whatsapp', label: 'واتساب' },
  { value: 'admin', label: 'الإدارة' },
]

export function AppointmentListPage() {
  const navigate = useNavigate()
  const { permissions } = useAuth()
  const toast = useToast()
  const [search] = useSearchParams()
  const [status, setStatus] = useState(search.get('status') || '')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
  // The front desk's look ahead: bookings after today, and which are paid —
  // to check a pre-paid patient in with their chosen doctor on the day.
  const [upcoming, setUpcoming] = useState(search.get('upcoming') === '1')
  const [paid, setPaid] = useState('')
  // Where it came from: the website, the desk, the phone… (docs/15).
  const [source, setSource] = useState(search.get('source') || '')

  const patient = search.get('patient') || undefined

  const decide = async (event, row, status, done) => {
    event.stopPropagation()
    try {
      await api.appointments.setStatus(row.uuid, status)
      toast.success(done)
      setRefreshKey((n) => n + 1)
    } catch (caught) {
      toast.error(caught.message)
    }
  }

  const columns = [
    { key: 'serial_number', header: 'رقم التذكرة', numeric: true },
    {
      key: 'scheduled_date',
      header: 'الموعد',
      render: (row) => formatDateTime(row.scheduled_date),
    },
    { key: 'patient_name', header: 'المريض' },
    { key: 'doctor_name', header: 'الطبيب', render: (row) => row.doctor_name || '—' },
    {
      key: 'service_name',
      header: 'الخدمة',
      // Sold by quantity: the service × how many.
      render: (row) =>
        row.service_name
          ? row.quantity
            ? `${row.service_name} × ${Number(row.quantity)}${row.quantity_unit ? ` ${row.quantity_unit}` : ''}${
                row.quantity_is_estimate ? ' (تقديرية)' : ''
              }`
            : row.service_name
          : '—',
    },
    {
      key: 'reschedule_requested_for',
      header: 'طلب نقل',
      render: (row) =>
        row.reschedule_requested_for ? (
          <div title={row.reschedule_note || undefined}>
            <Badge tone="warn">{formatDateTime(row.reschedule_requested_for)}</Badge>
            {permissions.front_desk && (
              <Button size="sm" variant="ghost"
                onClick={async (event) => {
                  event.stopPropagation()
                  await api.appointments.dismissReschedule(row.uuid)
                  setRefreshKey((n) => n + 1)
                }}>
                تجاهل
              </Button>
            )}
          </div>
        ) : null,
    },
    {
      key: 'source',
      header: 'المصدر',
      render: (row) => (
        <Badge tone={row.source === 'portal' ? 'info' : 'neutral'}>{row.source_label}</Badge>
      ),
    },
    {
      key: 'status',
      header: 'الحالة',
      render: (row) => (
        <Badge tone={APPOINTMENT_TONES[row.status] ?? 'neutral'}>
          {row.status_label}
        </Badge>
      ),
    },
    {
      key: 'price',
      header: 'السعر',
      numeric: true,
      render: (row) => formatMoney(row.price),
    },
    permissions.front_desk && {
      key: 'payment_status',
      header: 'الدفع',
      render: (row) =>
        row.payment_status ? (
          <Badge tone={PAYMENT[row.payment_status].tone}>
            {PAYMENT[row.payment_status].label}
            {row.payment_status === 'partial' ? ` · ${formatMoney(row.paid_total)}` : ''}
          </Badge>
        ) : null,
    },
    // A website request the clinic has phoned about: confirm it (the time is
    // then edited on the booking if it moved) or decline it.
    permissions.front_desk && {
      key: '__confirm',
      actions: true,
      render: (row) =>
        row.status === 'requested' ? (
          <div className="ui-row">
            <Button size="sm" variant="primary" onClick={(event) => decide(event, row, 'waiting', 'تم تأكيد الحجز.')}>
              تأكيد
            </Button>
            <Button size="sm" variant="ghost" onClick={(event) => decide(event, row, 'cancelled', 'تم رفض الطلب.')}>
              رفض
            </Button>
          </div>
        ) : null,
    },
    // After the patient has been in: follow-up date and printing, for the desk.
    permissions.front_desk && {
      key: '__desk',
      actions: true,
      render: (row) => (
        <VisitDeskActions appointment={row} onChanged={() => setRefreshKey((n) => n + 1)} />
      ),
    },
  ].filter(Boolean)

  return (
    <>
      <PageHeader
        title="المواعيد"
        // A doctor reads the bookings made for them; the desk makes them.
        actions={
          <>
            <EmailReportButton />
            {permissions.front_desk && (
              <Button variant="primary" onClick={() => navigate('/appointments/new')}>
                حجز موعد
              </Button>
            )}
          </>
        }
      />
      <ResourceTable
        resource={api.appointments}
        columns={columns}
        refreshKey={refreshKey}
        params={{
          status,
          from,
          to,
          patient,
          branch: search.get('branch') || undefined,
          upcoming: upcoming ? '1' : undefined,
          paid: paid || undefined,
          source: source || undefined,
        }}
        searchPlaceholder="ابحث برقم التذكرة أو اسم المريض…"
        onRowClick={
          permissions.front_desk ? (row) => navigate(`/appointments/${row.uuid}/edit`) : undefined
        }
        filters={
          <>
            <Checkbox
              label="القادمة فقط"
              checked={upcoming}
              onChange={(event) => setUpcoming(event.target.checked)}
            />
            {permissions.front_desk && (
              <Select
                value={paid}
                onChange={(event) => setPaid(event.target.value)}
                aria-label="الدفع"
                placeholder="كل حالات الدفع"
                options={[
                  { value: '1', label: 'مدفوعة' },
                  { value: '0', label: 'غير مدفوعة' },
                ]}
              />
            )}
            <Select
              value={source}
              onChange={(event) => setSource(event.target.value)}
              aria-label="مصدر الحجز"
              placeholder="كل المصادر"
              options={SOURCES}
            />
            <Select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              placeholder="كل الحالات"
              options={STATUSES}
              aria-label="تصفية بالحالة"
            />
            <Input
              type="date"
              value={from}
              onChange={(event) => setFrom(event.target.value)}
              aria-label="من تاريخ"
            />
            <Input
              type="date"
              value={to}
              onChange={(event) => setTo(event.target.value)}
              aria-label="إلى تاريخ"
            />
            {(status || from || to) && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setStatus('')
                  setFrom('')
                  setTo('')
                }}
              >
                مسح التصفية
              </Button>
            )}
          </>
        }
      />
    </>
  )
}
