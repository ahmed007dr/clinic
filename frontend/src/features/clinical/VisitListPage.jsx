import { useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { CrudPage } from '@/components/data/CrudPage'
import { useAuth } from '@/hooks/useAuth'
import { formatDateTime } from '@/lib/format'

/** Truncated in the table; the full text is on the record. */
function excerpt(text, limit = 60) {
  if (!text) return '—'
  return text.length > limit ? `${text.slice(0, limit)}…` : text
}

export function VisitListPage() {
  const [search] = useSearchParams()
  const patient = search.get('patient') || undefined
  const { permissions } = useAuth()

  return (
    <CrudPage
      title="الزيارات"
      // A visit is part of the medical record: only an admin may remove one,
      // and the server refuses anyone else regardless.
      canDelete={permissions.is_admin}
      // A visit opens when the front desk sends the patient in
      // (medical/checkin.py); nobody types one up here.
      canCreate={false}
      subtitle={
        patient
          ? 'مُصفّاة على مريض واحد'
          : 'تُفتح الزيارة تلقائياً عند تسجيل الاستقبال دخول المريض للطبيب'
      }
      resource={api.visits}
      params={{ patient }}
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
      // Patient, date, doctor and clinic are fixed from check-in (the server
      // ignores them on edit); only the clinical content and the follow-up
      // date are written here. They are in the table, not the form.
      fields={[
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
