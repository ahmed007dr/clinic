import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { Badge, Button, Checkbox, Input, Select, APPOINTMENT_TONES } from '@/components/ui'
import { ResourceTable } from '@/components/data/ResourceTable'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAuth } from '@/hooks/useAuth'
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

export function AppointmentListPage() {
  const navigate = useNavigate()
  const { permissions } = useAuth()
  const [search] = useSearchParams()
  const [status, setStatus] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)
  // The front desk's look ahead: bookings after today, and which are paid —
  // to check a pre-paid patient in with their chosen doctor on the day.
  const [upcoming, setUpcoming] = useState(search.get('upcoming') === '1')
  const [paid, setPaid] = useState('')

  const patient = search.get('patient') || undefined

  const columns = [
    { key: 'serial_number', header: 'رقم التذكرة', numeric: true },
    {
      key: 'scheduled_date',
      header: 'الموعد',
      render: (row) => formatDateTime(row.scheduled_date),
    },
    { key: 'patient_name', header: 'المريض' },
    { key: 'doctor_name', header: 'الطبيب', render: (row) => row.doctor_name || '—' },
    { key: 'service_name', header: 'الخدمة', render: (row) => row.service_name || '—' },
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
        actions={
          <Button variant="primary" onClick={() => navigate('/appointments/new')}>
            حجز موعد
          </Button>
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
        }}
        searchPlaceholder="ابحث برقم التذكرة أو اسم المريض…"
        onRowClick={(row) => navigate(`/appointments/${row.uuid}/edit`)}
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
