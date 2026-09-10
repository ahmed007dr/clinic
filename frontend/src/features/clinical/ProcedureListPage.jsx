import { useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { Badge, PROCEDURE_TONES } from '@/components/ui'
import { CrudPage } from '@/components/data/CrudPage'
import { formatDateTime, formatMoney, toDateTimeInput } from '@/lib/format'

const STATUSES = [
  { value: 'planned', label: 'مخطط' },
  { value: 'completed', label: 'تم' },
  { value: 'aborted', label: 'توقف' },
  { value: 'cancelled', label: 'ملغي' },
]

export function ProcedureListPage() {
  const [search] = useSearchParams()
  const patient = search.get('patient') || undefined

  return (
    <CrudPage
      title="الإجراءات"
      resource={api.procedures}
      params={{ patient }}
      createLabel="تسجيل إجراء"
      searchPlaceholder="ابحث بالاسم أو المريض…"
      columns={[
        { key: 'serial_number', header: 'الرقم', numeric: true },
        { key: 'name', header: 'الإجراء' },
        { key: 'patient_name', header: 'المريض' },
        {
          key: 'performed_at',
          header: 'التاريخ',
          render: (row) => formatDateTime(row.performed_at),
        },
        {
          key: 'status',
          header: 'الحالة',
          render: (row) => (
            <Badge tone={PROCEDURE_TONES[row.status] ?? 'neutral'}>
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
        { name: 'name', label: 'اسم الإجراء', required: true, span: 2 },
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
          name: 'visit',
          label: 'الزيارة',
          type: 'relation',
          resource: api.visits,
          searchable: true,
          labelKey: 'serial_number',
          required: true,
          params: (values) => ({ patient: values.patient || undefined }),
          hint: 'زيارات المريض المختار فقط',
        },
        {
          name: 'performed_at',
          label: 'تاريخ الإجراء',
          type: 'datetime',
          required: true,
          default: toDateTimeInput(new Date()),
        },
        {
          name: 'status',
          label: 'الحالة',
          type: 'select',
          default: 'completed',
          placeholder: undefined,
          options: STATUSES,
        },
        { name: 'doctor', label: 'الطبيب', type: 'relation', resource: api.doctors },
        { name: 'service', label: 'الخدمة', type: 'relation', resource: api.services },
        { name: 'body_site', label: 'الموضع' },
        { name: 'quantity', label: 'الكمية', type: 'number', min: 1, default: 1 },
        { name: 'unit_price', label: 'سعر الوحدة', type: 'money' },
        { name: 'discount', label: 'الخصم', type: 'money' },
        { name: 'findings', label: 'ما تم ملاحظته', type: 'textarea', span: 2 },
        { name: 'outcome', label: 'النتيجة', type: 'textarea', span: 2 },
        { name: 'complications', label: 'مضاعفات', type: 'textarea', span: 2 },
        { name: 'notes', label: 'ملاحظات', type: 'textarea', span: 2 },
      ]}
      emptyMessage="ستظهر هنا الإجراءات بعد تسجيلها."
    />
  )
}
