import { useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { useAuth } from '@/hooks/useAuth'
import { Badge, SESSION_TONES } from '@/components/ui'
import { CrudPage } from '@/components/data/CrudPage'
import { formatDateTime, formatMoney, toDateTimeInput } from '@/lib/format'

const STATUSES = [
  { value: 'scheduled', label: 'مجدولة' },
  { value: 'completed', label: 'مكتملة' },
  { value: 'cancelled', label: 'ملغاة' },
  { value: 'no_show', label: 'لم يحضر' },
]

export function TreatmentSessionListPage() {
  const { permissions } = useAuth()
  const [search] = useSearchParams()
  const plan = search.get('plan') || undefined
  const patient = search.get('patient') || undefined

  return (
    <CrudPage
      title="جلسات العلاج"
      subtitle={plan ? 'جلسات خطة واحدة' : undefined}
      resource={api.treatmentSessions}
      params={{ plan, patient }}
      createLabel="إضافة جلسة"
      searchPlaceholder="ابحث بالمريض أو الخطة…"
      columns={[
        { key: 'sequence', header: 'رقم الجلسة', numeric: true },
        { key: 'plan_title', header: 'الخطة' },
        { key: 'patient_name', header: 'المريض' },
        {
          key: 'scheduled_date',
          header: 'الموعد',
          render: (row) => formatDateTime(row.scheduled_date),
        },
        {
          key: 'status',
          header: 'الحالة',
          render: (row) => (
            <Badge tone={SESSION_TONES[row.status] ?? 'neutral'}>
              {row.status_label}
            </Badge>
          ),
        },
        {
          key: 'unit_price',
          header: 'السعر',
          numeric: true,
          render: (row) => formatMoney(row.unit_price),
        },
      ]}
      fields={[
        {
          name: 'plan',
          label: 'الخطة',
          type: 'relation',
          resource: api.treatmentPlans,
          searchable: true,
          labelKey: 'title',
          required: true,
          default: plan ?? '',
        },
        {
          name: 'patient',
          label: 'المريض',
          type: 'relation',
          resource: api.patients,
          searchable: true,
          required: true,
          default: patient ?? '',
        },
        {
          name: 'sequence',
          label: 'رقم الجلسة',
          type: 'number',
          min: 1,
          required: true,
          default: 1,
        },
        {
          name: 'scheduled_date',
          label: 'موعد الجلسة',
          type: 'datetime',
          required: true,
          default: toDateTimeInput(new Date()),
        },
        {
          name: 'status',
          label: 'الحالة',
          type: 'select',
          default: 'scheduled',
          placeholder: undefined,
          options: STATUSES,
        },
        { name: 'performed_at', label: 'تاريخ التنفيذ', type: 'datetime' },
        { name: 'doctor', label: 'الطبيب', type: 'relation', resource: api.doctors },
        { name: 'service', label: 'الخدمة', type: 'relation', resource: api.services },
        { name: 'quantity', label: 'الكمية', type: 'number', min: 1, default: 1 },
        // Price from the doctor's contract; price and discount are
        // management's (billing/pricing.py — the server enforces it).
        {
          name: 'unit_price',
          label: 'سعر الوحدة',
          type: 'money',
          disabled: !permissions.is_admin,
          hint: permissions.is_admin ? undefined : 'من تعاقد الطبيب — تعديله للإدارة فقط',
        },
        { name: 'discount', label: 'الخصم', type: 'money', disabled: !permissions.is_admin },
        { name: 'result', label: 'النتيجة', type: 'textarea', span: 2 },
        { name: 'notes', label: 'ملاحظات', type: 'textarea', span: 2 },
      ]}
      emptyMessage="ستظهر هنا جلسات خطط العلاج."
    />
  )
}
