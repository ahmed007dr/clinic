import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { Badge, Button, Input, Select, APPOINTMENT_TONES } from '@/components/ui'
import { ResourceTable } from '@/components/data/ResourceTable'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAuth } from '@/hooks/useAuth'
import { formatDateTime, formatMoney } from '@/lib/format'

const STATUSES = [
  { value: 'waiting', label: 'الانتظار' },
  { value: 'entered', label: 'تم الدخول' },
  { value: 'called', label: 'تم الاتصال' },
  { value: 'quick', label: 'حجز سريع' },
]

export function AppointmentListPage() {
  const navigate = useNavigate()
  const { permissions } = useAuth()
  const [search] = useSearchParams()
  const [status, setStatus] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')

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
  ]

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
        params={{ status, from, to, patient }}
        searchPlaceholder="ابحث برقم التذكرة أو اسم المريض…"
        onRowClick={(row) => navigate(`/appointments/${row.uuid}/edit`)}
        filters={
          <>
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
