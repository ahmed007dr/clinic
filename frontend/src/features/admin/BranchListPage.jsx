import { api } from '@/api'
import { CrudPage } from '@/components/data/CrudPage'

export function BranchListPage() {
  return (
    <CrudPage
      title="الفروع"
      resource={api.branches}
      createLabel="إضافة فرع"
      searchPlaceholder="ابحث بالاسم أو الكود…"
      deleteWarning="لا يمكن حذف فرع مرتبط بمرضى أو مواعيد."
      columns={[
        { key: 'name', header: 'الفرع' },
        { key: 'code', header: 'الكود' },
        {
          key: 'phone',
          header: 'الهاتف',
          render: (row) => <span dir="ltr">{row.phone || '—'}</span>,
        },
        { key: 'address', header: 'العنوان', render: (row) => row.address || '—' },
      ]}
      fields={[
        { name: 'name', label: 'اسم الفرع', required: true },
        { name: 'code', label: 'الكود', required: true },
        { name: 'phone', label: 'الهاتف', type: 'tel' },
        { name: 'email', label: 'البريد', type: 'email' },
        { name: 'address', label: 'العنوان', type: 'textarea', rows: 2, span: 2 },
        {
          name: 'footer_text',
          label: 'تذييل المطبوعات',
          span: 2,
          hint: 'يظهر أسفل الإيصالات والروشتات المطبوعة.',
        },
      ]}
      emptyMessage="أضف فروع العيادة."
    />
  )
}
