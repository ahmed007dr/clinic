import { api } from '@/api'
import { Badge } from '@/components/ui'
import { CrudPage } from '@/components/data/CrudPage'
import { useAuth } from '@/hooks/useAuth'
import { formatDate } from '@/lib/format'

/**
 * Days a clinic is closed (docs/15, Phase 4): no online times are offered that
 * day. A clinic's Admin sets their own clinic's; a day for the whole group (a
 * public holiday) is the Owner's, and shows here read-only for Admins.
 */
export function HolidaysPage() {
  const { permissions } = useAuth()
  return (
    <CrudPage
      title="إجازات العيادة"
      subtitle="أيام إغلاق العيادة. لا تُعرض فيها أوقات للحجز من الموقع."
      resource={api.branchHolidays}
      createLabel="إضافة إجازة"
      searchable={false}
      columns={[
        { key: 'name', header: 'المناسبة', render: (row) => row.name || '—' },
        {
          key: 'branch_name',
          header: 'العيادة',
          render: (row) => row.branch_name || <Badge tone="info">كل المجمع</Badge>,
        },
        { key: 'start_date', header: 'من', render: (row) => formatDate(row.start_date) },
        { key: 'end_date', header: 'إلى', render: (row) => formatDate(row.end_date) },
      ]}
      fields={[
        { name: 'name', label: 'المناسبة', span: 2 },
        {
          name: 'branch',
          label: 'العيادة',
          type: 'relation',
          resource: api.branches,
          placeholder: permissions.is_owner ? '— كل المجمع —' : undefined,
          required: !permissions.is_owner,
          hint: permissions.is_owner ? 'اتركها فارغة لإجازة تشمل كل عيادات المجمع.' : undefined,
          span: 2,
        },
        { name: 'start_date', label: 'من تاريخ', type: 'date', required: true },
        { name: 'end_date', label: 'إلى تاريخ', type: 'date', required: true },
      ]}
      emptyMessage="لا إجازات مسجّلة."
    />
  )
}
