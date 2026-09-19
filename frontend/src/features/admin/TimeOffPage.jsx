import { api } from '@/api'
import { CrudPage } from '@/components/data/CrudPage'
import { formatDate } from '@/lib/format'

/**
 * A doctor's leave (docs/15, Phase 4). While it lasts the website offers no
 * times for that doctor at any clinic. The reason is for the clinic only — it is
 * never shown to the public. Reception can still book by hand.
 */
export function TimeOffPage() {
  return (
    <CrudPage
      title="إجازات الأطباء"
      subtitle="أيام غياب الطبيب (إجازة، مؤتمر…). لا تُعرض له أوقات للحجز من الموقع خلالها."
      resource={api.doctorTimeOff}
      createLabel="إضافة إجازة"
      searchable={false}
      columns={[
        { key: 'doctor_name', header: 'الطبيب' },
        { key: 'start_date', header: 'من', render: (row) => formatDate(row.start_date) },
        { key: 'end_date', header: 'إلى', render: (row) => formatDate(row.end_date) },
        { key: 'reason', header: 'السبب', render: (row) => row.reason || '—' },
      ]}
      fields={[
        {
          name: 'doctor',
          label: 'الطبيب',
          type: 'relation',
          resource: api.doctors,
          required: true,
          span: 2,
        },
        { name: 'start_date', label: 'من تاريخ', type: 'date', required: true },
        { name: 'end_date', label: 'إلى تاريخ', type: 'date', required: true },
        { name: 'reason', label: 'السبب (داخلي)', span: 2, hint: 'لا يظهر للعامة.' },
      ]}
      emptyMessage="لا إجازات مسجّلة."
    />
  )
}
