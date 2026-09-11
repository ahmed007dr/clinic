import { useState } from 'react'

import { api } from '@/api'
import { Checkbox } from '@/components/ui'
import { CrudPage } from '@/components/data/CrudPage'
import { useAuth } from '@/hooks/useAuth'
import { formatDate, formatMoney, today } from '@/lib/format'

import { VoidButton } from './VoidButton'

const RESOURCE = api.expenses

export function ExpenseListPage() {
  const { permissions } = useAuth()
  // Inside a cash shift the date and clinic are the shift's (the server sets
  // them); asking for them would only invite a back-dated expense.
  const inShift = permissions.works_in_shifts
  const [voided, setVoided] = useState(false)
  // CrudPage refreshes itself after its own saves; a cancellation happens
  // outside it, so the list is remounted to reload.
  const [refreshKey, setRefreshKey] = useState(0)
  return (
    <CrudPage
      key={`${refreshKey}-${voided}`}
      title="المصروفات"
      resource={RESOURCE}
      params={{ voided: voided ? '1' : undefined }}
      canEdit={!voided}
      canDelete={false}
      extraFilters={
        permissions.is_admin && (
          <Checkbox label="الملغاة فقط" checked={voided} onChange={(e) => setVoided(e.target.checked)} />
        )
      }
      createLabel="تسجيل مصروف"
      searchPlaceholder="ابحث بالبند أو الموظف…"
      columns={[
        { key: 'date', header: 'التاريخ', render: (row) => formatDate(row.date) },
        {
          key: 'category_name',
          header: 'البند',
          render: (row) => row.category_name || '—',
        },
        { key: 'branch_name', header: 'الفرع' },
        { key: 'method_name', header: 'الطريقة', render: (row) => row.method_name || '—' },
        {
          key: 'employee_name',
          header: 'الموظف',
          render: (row) => row.employee_name || '—',
        },
        {
          key: 'amount',
          header: 'المبلغ',
          numeric: true,
          render: (row) => <strong>{formatMoney(row.amount)}</strong>,
        },
        ...(permissions.is_admin
          ? [
              {
                key: '__void',
                header: '',
                render: (row) =>
                  row.voided_at ? (
                    <span className="ui-muted">ملغى · {row.void_reason}</span>
                  ) : (
                    <VoidButton resource={RESOURCE} record={row} onDone={() => setRefreshKey((n) => n + 1)} />
                  ),
              },
            ]
          : []),
      ]}
      fields={[
        { name: 'amount', label: 'المبلغ', type: 'money', required: true },
        { name: 'date', label: 'التاريخ', type: 'date', required: true, default: today(), hide: inShift },
        {
          name: 'method',
          label: 'طريقة الدفع',
          type: 'relation',
          resource: api.paymentMethods,
          hint: 'تُخصم من صافي هذه الطريقة في تقرير الوردية.',
        },
        {
          name: 'category',
          label: 'البند',
          type: 'relation',
          resource: api.expenseCategories,
        },
        {
          name: 'branch',
          label: 'الفرع',
          type: 'relation',
          resource: api.branches,
          required: true,
          hide: inShift,
        },
        {
          name: 'employee',
          label: 'الموظف',
          type: 'relation',
          resource: api.employees,
          searchable: true,
        },
        { name: 'notes', label: 'ملاحظات', type: 'textarea', span: 2 },
      ]}
      emptyMessage="ستظهر هنا مصروفات العيادة بعد تسجيلها."
    />
  )
}
