import { api } from '@/api'
import { CrudPage } from '@/components/data/CrudPage'
import { formatDate, formatMoney, today } from '@/lib/format'

/**
 * Staff records, including pay. Admin only — the endpoint refuses everyone
 * else, which is why the booking forms use the separate doctor picker instead
 * of this.
 */
export function EmployeeListPage() {
  return (
    <CrudPage
      title="الموظفون"
      resource={api.employees}
      createLabel="إضافة موظف"
      searchPlaceholder="ابحث بالاسم أو الرقم القومي…"
      columns={[
        { key: 'serial_number', header: 'الرقم', numeric: true },
        { key: 'name', header: 'الاسم' },
        {
          key: 'employee_type_name',
          header: 'الوظيفة',
          render: (row) => row.employee_type_name || '—',
        },
        { key: 'branch_name', header: 'الفرع' },
        {
          key: 'phone1',
          header: 'الهاتف',
          render: (row) => <span dir="ltr">{row.phone1 || '—'}</span>,
        },
        {
          key: 'hire_date',
          header: 'التعيين',
          render: (row) => formatDate(row.hire_date),
        },
        {
          key: 'salary_value',
          header: 'الراتب',
          numeric: true,
          render: (row) => formatMoney(row.salary_value),
        },
      ]}
      fields={[
        { name: 'name', label: 'الاسم', required: true, span: 2 },
        {
          name: 'employee_type',
          label: 'الوظيفة',
          type: 'relation',
          resource: api.employeeTypes,
        },
        {
          name: 'branch',
          label: 'الفرع',
          type: 'relation',
          resource: api.branches,
          required: true,
        },
        { name: 'national_id', label: 'الرقم القومي', required: true },
        {
          name: 'hire_date',
          label: 'تاريخ التعيين',
          type: 'date',
          required: true,
          default: today(),
        },
        { name: 'phone1', label: 'الهاتف', type: 'tel' },
        { name: 'phone2', label: 'هاتف آخر', type: 'tel' },
        { name: 'email', label: 'البريد', type: 'email' },
        {
          name: 'salary_type',
          label: 'نوع الراتب',
          type: 'relation',
          resource: api.salaryTypes,
        },
        {
          name: 'salary_value',
          label: 'قيمة الراتب',
          type: 'money',
          required: true,
          default: 0,
        },
      ]}
      emptyMessage="أضف موظفي العيادة هنا."
    />
  )
}
