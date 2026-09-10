import { api } from '@/api'
import { CrudPage } from '@/components/data/CrudPage'
import { formatDate, formatMoney, today } from '@/lib/format'

export function ExpenseListPage() {
  return (
    <CrudPage
      title="المصروفات"
      resource={api.expenses}
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
      ]}
      fields={[
        { name: 'amount', label: 'المبلغ', type: 'money', required: true },
        { name: 'date', label: 'التاريخ', type: 'date', required: true, default: today() },
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
