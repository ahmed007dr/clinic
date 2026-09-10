import { useNavigate } from 'react-router-dom'

import { api } from '@/api'
import { Badge, Button } from '@/components/ui'
import { ResourceTable } from '@/components/data/ResourceTable'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAuth } from '@/hooks/useAuth'
import { formatDate } from '@/lib/format'

const GENDER = { male: 'ذكر', female: 'أنثى' }

export function PatientListPage() {
  const navigate = useNavigate()
  const { permissions } = useAuth()

  const columns = [
    { key: 'serial_number', header: 'الرقم', numeric: true },
    { key: 'name', header: 'الاسم' },
    {
      key: 'gender',
      header: 'النوع',
      render: (row) => (
        <Badge tone="neutral">{GENDER[row.gender] ?? row.gender}</Badge>
      ),
    },
    {
      key: 'phone1',
      header: 'الهاتف',
      // Latin digits in an RTL paragraph reorder without this, turning
      // 01001234567 into something that cannot be dialled.
      render: (row) => <span dir="ltr">{row.phone1 || '—'}</span>,
    },
    ...(permissions.all_branches
      ? [
          {
            key: 'branch_name',
            header: 'الفرع',
            render: (row) => row.branch_name || '—',
          },
        ]
      : []),
    {
      key: 'created_at',
      header: 'التسجيل',
      render: (row) => formatDate(row.created_at),
    },
  ]

  return (
    <>
      <PageHeader
        title="المرضى"
        actions={
          <Button variant="primary" onClick={() => navigate('/patients/new')}>
            تسجيل مريض
          </Button>
        }
      />
      <ResourceTable
        resource={api.patients}
        columns={columns}
        searchPlaceholder="ابحث بالاسم أو الرقم أو الهاتف…"
        onRowClick={(row) => navigate(`/patients/${row.uuid}`)}
        empty={{
          title: 'لا يوجد مرضى بعد',
          message: 'ابدأ بتسجيل أول مريض من الزر أعلى الصفحة.',
        }}
      />
    </>
  )
}
