import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { Badge, Button } from '@/components/ui'
import { ResourceTable } from '@/components/data/ResourceTable'
import { ExportButtons } from '@/components/data/ExportButtons'
import { SearchPanel, hasCriteria } from '@/components/data/SearchPanel'
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
  // The list loads only when "بحث" is pressed. The owner dashboard links here
  // with a clinic already chosen, which counts as having asked.
  const linkedBranch = search.get('branch') || undefined
  const [applied, setApplied] = useState(linkedBranch ? { branch: linkedBranch } : null)

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
      <SearchPanel
        queryLabel="الاسم أو رقم الهاتف"
        queryPlaceholder="اكتب اسم المريض أو رقم هاتفه"
        initial={{ branch: linkedBranch ?? '' }}
        fields={[
          { name: 'created_from', label: 'تاريخ التسجيل — من', type: 'date' },
          { name: 'created_to', label: 'تاريخ التسجيل — إلى', type: 'date' },
          {
            name: 'gender',
            label: 'النوع',
            type: 'select',
            options: [
              { value: 'male', label: GENDER.male },
              { value: 'female', label: GENDER.female },
            ],
          },
          ...(permissions.all_branches
            ? [{ name: 'branch', label: 'الفرع', type: 'relation', resource: api.branches }]
            : []),
        ]}
        validate={(values) =>
          hasCriteria(values)
            ? null
            : 'اكتب اسماً أو رقم هاتف، أو اختر تاريخ تسجيل أو النوع أو الفرع، ثم اضغط بحث.'
        }
        onSearch={setApplied}
        onReset={() => setApplied(null)}
      />
      <ResourceTable
        resource={api.patients}
        columns={columns}
        searchable={false}
        enabled={applied !== null}
        params={{
          search: applied?.q,
          created_from: applied?.created_from,
          created_to: applied?.created_to,
          gender: applied?.gender,
          branch: applied?.branch,
        }}
        onRowClick={(row) => navigate(`/patients/${row.uuid}`)}
        idle={{
          title: 'ابحث عن مريض',
          message: 'اكتب الاسم أو الهاتف، أو حدد تاريخ التسجيل أو الفرع أو النوع، ثم اضغط «بحث».',
        }}
        empty={{
          title: 'لا توجد نتائج',
          message: 'لم يُعثر على مريض يطابق هذا البحث. جرّب تغيير الشروط.',
        }}
      />
    </>
  )
}
