import { useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { CrudPage } from '@/components/data/CrudPage'
import { formatDateTime, toDateTimeInput } from '@/lib/format'

/** Truncated in the table; the full text is on the record. */
function excerpt(text, limit = 60) {
  if (!text) return '—'
  return text.length > limit ? `${text.slice(0, limit)}…` : text
}

export function VisitListPage() {
  const [search] = useSearchParams()
  const patient = search.get('patient') || undefined

  return (
    <CrudPage
      title="الزيارات"
      subtitle={patient ? 'مُصفّاة على مريض واحد' : undefined}
      resource={api.visits}
      params={{ patient }}
      createLabel="تسجيل زيارة"
      searchPlaceholder="ابحث بالمريض أو الشكوى أو التشخيص…"
      columns={[
        { key: 'serial_number', header: 'الرقم', numeric: true },
        {
          key: 'visit_date',
          header: 'التاريخ',
          render: (row) => formatDateTime(row.visit_date),
        },
        { key: 'patient_name', header: 'المريض' },
        {
          key: 'doctor_name',
          header: 'الطبيب',
          render: (row) => row.doctor_name || '—',
        },
        {
          key: 'chief_complaint',
          header: 'الشكوى',
          render: (row) => excerpt(row.chief_complaint),
        },
        {
          key: 'diagnosis',
          header: 'التشخيص',
          render: (row) => excerpt(row.diagnosis),
        },
      ]}
      fields={[
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
          name: 'visit_date',
          label: 'تاريخ الزيارة',
          type: 'datetime',
          required: true,
          default: toDateTimeInput(new Date()),
        },
        { name: 'doctor', label: 'الطبيب', type: 'relation', resource: api.doctors },
        { name: 'branch', label: 'الفرع', type: 'relation', resource: api.branches },
        { name: 'chief_complaint', label: 'الشكوى', type: 'textarea', span: 2 },
        { name: 'examination', label: 'الفحص', type: 'textarea', span: 2 },
        { name: 'diagnosis', label: 'التشخيص', type: 'textarea', span: 2 },
        { name: 'treatment_plan', label: 'خطة العلاج', type: 'textarea', span: 2 },
        { name: 'follow_up_date', label: 'موعد المتابعة', type: 'date' },
      ]}
      emptyMessage="ستظهر هنا الزيارات بعد تسجيلها."
      deleteWarning="سيُحذف سجل الزيارة نهائياً."
    />
  )
}
