import { useState } from 'react'

import { api } from '@/api'
import { Button, Checkbox, Modal } from '@/components/ui'
import { CrudPage } from '@/components/data/CrudPage'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { formatDate, formatMoney, today } from '@/lib/format'

/**
 * Staff records, including pay. Admin only — the endpoint refuses everyone
 * else, which is why the booking forms use the separate doctor picker instead
 * of this.
 */
export function EmployeeListPage() {
  const { permissions } = useAuth()
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
        {
          key: 'branch_name',
          header: 'الفرع',
          render: (row) => (
            <>
              {row.branch_name}
              {row.extra_branch_names?.length > 0 && (
                <div className="ui-muted">+ {row.extra_branch_names.join('، ')}</div>
              )}
            </>
          ),
        },
        ...(permissions.is_owner
          ? [
              {
                key: 'extra_branches',
                header: 'فروع إضافية',
                render: (row) =>
                  row.employee_type_name === 'Doctor' ? <DoctorBranchesButton employee={row} /> : '—',
              },
            ]
          : []),
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
        {
          name: 'commission_percent',
          label: 'نسبة الطبيب الافتراضية %',
          type: 'number',
          hint: 'للأطباء: نسبته من المبلغ المدفوع فعلاً ما لم يحدد تعاقده نسبة لخدمة بعينها.',
        },
      ]}
      emptyMessage="أضف موظفي العيادة هنا."
    />
  )
}

/**
 * The Owner links a doctor to further clinics of the group (a login then
 * switches between them). Owner only on the server too
 * (EmployeeSerializer.validate_extra_branches) — this is the one place it is
 * offered, rather than a field every Admin would see and be refused on.
 */
function DoctorBranchesButton({ employee }) {
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [chosen, setChosen] = useState(new Set(employee.extra_branches ?? []))
  const [names, setNames] = useState(employee.extra_branch_names ?? [])
  const branches = useAsync(() => api.branches.list({ page_size: 100 }), [], { skip: !open })
  const save = useMutation(() =>
    api.employees.update(employee.uuid, { extra_branches: [...chosen] }),
  )

  const toggle = (uuid) =>
    setChosen((current) => {
      const next = new Set(current)
      if (next.has(uuid)) next.delete(uuid)
      else next.add(uuid)
      return next
    })

  const submit = async () => {
    try {
      const saved = await save.run()
      setNames(saved.extra_branch_names)
      setChosen(new Set(saved.extra_branches))
      setOpen(false)
      toast.success('تم حفظ فروع الطبيب')
    } catch (error) {
      toast.error(error.message)
    }
  }

  const rows = (branches.data?.results ?? []).filter((branch) => branch.uuid !== employee.branch)

  return (
    <span onClick={(event) => event.stopPropagation()}>
      <Button size="sm" variant="ghost" onClick={() => setOpen(true)}>
        {names.length ? names.join('، ') : 'ربط بفروع'}
      </Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={`فروع ${employee.name}`}
        size="narrow"
        footer={
          <>
            <Button variant="primary" onClick={submit} loading={save.submitting}>
              حفظ
            </Button>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              إلغاء
            </Button>
          </>
        }
      >
        <p className="ui-muted">
          الفرع الأساسي: {employee.branch_name}. الطبيب يرى مرضاه في كل فرع يُربط به، وينتقل
          بينها من حسابه.
        </p>
        <div className="ui-stack">
          {rows.map((branch) => (
            <Checkbox
              key={branch.uuid}
              label={branch.name}
              checked={chosen.has(branch.uuid)}
              onChange={() => toggle(branch.uuid)}
            />
          ))}
        </div>
      </Modal>
    </span>
  )
}
