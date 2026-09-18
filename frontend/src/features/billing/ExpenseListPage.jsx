import { useState } from 'react'

import { api } from '@/api'
import { CrudPage } from '@/components/data/CrudPage'
import { SearchPanel, hasCriteria } from '@/components/data/SearchPanel'
import { useAuth } from '@/hooks/useAuth'
import { serverUrl } from '@/lib/config'
import { formatDate, formatMoney, today } from '@/lib/format'

import { ShiftStamp } from '../shifts/ShiftStamp'
import { VoidButton } from './VoidButton'

const RESOURCE = api.expenses

export function ExpenseListPage() {
  const { permissions } = useAuth()
  // Every expense is recorded inside the recorder's cash shift, which sets its
  // date and clinic (the server does); asking for them would only invite a
  // back-dated expense.
  const inShift = permissions.works_in_shifts
  // CrudPage refreshes itself after its own saves; a cancellation happens
  // outside it, so the list is remounted to reload.
  const [refreshKey, setRefreshKey] = useState(0)
  // Reception sees their own open shift's expenses only — a short list, loaded
  // at once. Management sees the clinic's books, so nothing loads until they
  // state what they are after and press "بحث".
  const books = permissions.view_finance
  const [applied, setApplied] = useState(null)
  const voided = Boolean(applied?.voided)

  return (
    <CrudPage
      key={refreshKey}
      title="المصروفات"
      resource={RESOURCE}
      searchable={!books}
      enabled={!books || applied !== null}
      idle={{
        title: 'ابحث في المصروفات',
        message: 'حدد تاريخاً أو فرعاً أو موظفاً أو مبلغاً، ثم اضغط «بحث».',
      }}
      params={
        books
          ? {
              search: applied?.q,
              from: applied?.from,
              to: applied?.to,
              branch: applied?.branch,
              employee: applied?.employee,
              amount_min: applied?.amount_min,
              amount_max: applied?.amount_max,
              voided: applied?.voided ? '1' : undefined,
            }
          : {}
      }
      beforeTable={
        books && (
          <SearchPanel
            queryLabel="البند أو اسم الموظف أو ملاحظات"
            queryPlaceholder="اكتب اسم البند أو الموظف أو جزءاً من الملاحظات"
            fields={[
              { name: 'from', label: 'من تاريخ', type: 'date' },
              { name: 'to', label: 'إلى تاريخ', type: 'date' },
              ...(permissions.all_branches
                ? [{ name: 'branch', label: 'الفرع', type: 'relation', resource: api.branches }]
                : []),
              {
                name: 'employee',
                label: 'الموظف',
                type: 'relation',
                resource: api.employees,
                searchable: true,
              },
              { name: 'amount_min', label: 'المبلغ من', type: 'money' },
              { name: 'amount_max', label: 'المبلغ إلى', type: 'money' },
              { name: 'voided', label: 'الملغاة فقط', type: 'checkbox' },
            ]}
            validate={(values) =>
              hasCriteria(values, ['voided'])
                ? null
                : 'حدد شرط بحث واحد على الأقل: تاريخ أو فرع أو موظف أو مبلغ، ثم اضغط بحث.'
            }
            onSearch={setApplied}
            onReset={() => setApplied(null)}
          />
        )
      }
      canEdit={!voided}
      canDelete={false}
      createLabel="تسجيل مصروف"
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
        { key: 'shift', header: 'الوردية', render: (row) => <ShiftStamp row={row} /> },
        {
          key: 'amount',
          header: 'المبلغ',
          numeric: true,
          render: (row) => <strong>{formatMoney(row.amount)}</strong>,
        },
        {
          key: '__print',
          header: '',
          render: (row) =>
            !row.voided_at && (
              <a
                className="ui-btn ui-btn--ghost ui-btn--sm"
                href={serverUrl(`/billing/expense/${row.uuid}/print/`)}
                target="_blank"
                rel="noopener"
              >
                طباعة
              </a>
            ),
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
