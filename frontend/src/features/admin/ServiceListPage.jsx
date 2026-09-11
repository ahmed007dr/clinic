import { api } from '@/api'
import { Badge } from '@/components/ui'
import { CrudPage } from '@/components/data/CrudPage'
import { formatMoney } from '@/lib/format'

export function ServiceListPage() {
  return (
    <CrudPage
      title="الخدمات"
      subtitle="ما تقدّمه العيادة وأسعاره"
      resource={api.services}
      createLabel="إضافة خدمة"
      searchPlaceholder="ابحث باسم الخدمة…"
      columns={[
        {
          key: 'is_active',
          header: 'الحالة',
          render: (row) => (
            <Badge tone={row.is_active ? 'ok' : 'neutral'}>{row.is_active ? 'يعمل' : 'موقوف'}</Badge>
          ),
        },
        { key: 'name', header: 'الخدمة' },
        {
          key: 'specialization_name',
          header: 'التخصص',
          render: (row) => row.specialization_name || '—',
        },
        {
          key: 'base_price',
          header: 'السعر',
          numeric: true,
          render: (row) => <strong>{formatMoney(row.base_price)}</strong>,
        },
      ]}
      fields={[
        { name: 'name', label: 'اسم الخدمة', required: true },
        {
          name: 'is_active',
          label: 'الخدمة متاحة',
          type: 'checkbox',
          default: true,
          hint: 'الخدمة الموقوفة تختفي من الحجز والإجراءات؛ ما سُجّل بها سابقاً يبقى.',
        },
        {
          name: 'base_price',
          label: 'السعر الأساسي',
          type: 'money',
          required: true,
          default: 0,
        },
        {
          name: 'specialization',
          label: 'التخصص',
          type: 'relation',
          resource: api.specializations,
        },
        { name: 'description', label: 'الوصف', type: 'textarea', span: 2 },
      ]}
      emptyMessage="أضف الخدمات التي تقدّمها العيادة."
    />
  )
}
