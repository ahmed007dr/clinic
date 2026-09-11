import { useNavigate, useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { Badge, Button } from '@/components/ui'
import { ResourceTable } from '@/components/data/ResourceTable'
import { ExportButtons } from '@/components/data/ExportButtons'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAuth } from '@/hooks/useAuth'
import { useT } from '@/i18n'
import { serverUrl } from '@/lib/config'
import { formatDate } from '@/lib/format'

const GENDER = { male: 'ذكر', female: 'أنثى' }

export function PatientListPage() {
  const navigate = useNavigate()
  const { permissions } = useAuth()
  const { t } = useT()
  const [search] = useSearchParams()

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
          <>
          <ExportButtons path="/patients/export/" />
          {/* The server-rendered, printable intake form in the clinic's own design
              (Print design screen): the patient fills it in by hand and signs. */}
          {permissions.front_desk && (
            <a
              className="ui-btn ui-btn--secondary"
              href={serverUrl('/patients/print/intake/')}
              target="_blank"
              rel="noopener"
            >
              {t('patients.print_intake')}
            </a>
          )}
          
          {permissions.front_desk && (
            <Button onClick={() => navigate('/patients/review')}>{t('nav.review')}</Button>
          )}
          <Button variant="primary" onClick={() => navigate('/patients/new')}>
            تسجيل مريض
          </Button>
          </>
        }
      />
      <ResourceTable
        resource={api.patients}
        columns={columns}
        // The owner dashboard links here with a clinic selected.
        params={{ branch: search.get('branch') || undefined }}
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
