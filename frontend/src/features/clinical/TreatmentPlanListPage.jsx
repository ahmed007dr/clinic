import { useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { Badge, PLAN_TONES } from '@/components/ui'
import { CrudPage } from '@/components/data/CrudPage'
import { formatDate, today } from '@/lib/format'

const STATUSES = [
  { value: 'draft', label: 'مسودة' },
  { value: 'active', label: 'جارية' },
  { value: 'completed', label: 'مكتملة' },
  { value: 'cancelled', label: 'ملغاة' },
]

export function TreatmentPlanListPage() {
  const [search] = useSearchParams()
  const patient = search.get('patient') || undefined

  return (
    <CrudPage
      title="خطط العلاج"
      resource={api.treatmentPlans}
      params={{ patient }}
      createLabel="خطة جديدة"
      searchPlaceholder="ابحث بالعنوان أو المريض…"
      columns={[
        { key: 'serial_number', header: 'الرقم', numeric: true },
        { key: 'title', header: 'الخطة' },
        { key: 'patient_name', header: 'المريض' },
        {
          key: 'progress',
          header: 'التقدم',
          numeric: true,
          // The number people actually open this screen for: how far through
          // a course of sessions a patient is.
          render: (row) => `${row.completed_sessions} / ${row.planned_sessions}`,
        },
        {
          key: 'status',
          header: 'الحالة',
          render: (row) => (
            <Badge tone={PLAN_TONES[row.status] ?? 'neutral'}>{row.status_label}</Badge>
          ),
        },
        {
          key: 'start_date',
          header: 'البدء',
          render: (row) => formatDate(row.start_date),
        },
      ]}
      fields={[
        { name: 'title', label: 'اسم الخطة', required: true, span: 2 },
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
          name: 'planned_sessions',
          label: 'عدد الجلسات',
          type: 'number',
          min: 1,
          required: true,
          default: 1,
        },
        { name: 'doctor', label: 'الطبيب', type: 'relation', resource: api.doctors },
        { name: 'service', label: 'الخدمة', type: 'relation', resource: api.services },
        { name: 'branch', label: 'الفرع', type: 'relation', resource: api.branches },
        {
          name: 'start_date',
          label: 'تاريخ البدء',
          type: 'date',
          required: true,
          default: today(),
        },
        {
          name: 'status',
          label: 'الحالة',
          type: 'select',
          default: 'active',
          placeholder: undefined,
          options: STATUSES,
        },
        { name: 'notes', label: 'ملاحظات', type: 'textarea', span: 2 },
      ]}
      emptyMessage="ستظهر هنا خطط العلاج بعد إنشائها."
    />
  )
}
