import { Link } from 'react-router-dom'

import { api } from '@/api'
import { Badge } from '@/components/ui'
import { CrudPage } from '@/components/data/CrudPage'
import { formatMoney } from '@/lib/format'

const PRICE_DISPLAY = [
  { value: 'fixed', label: 'سعر ثابت' },
  { value: 'starting_from', label: 'يبدأ من' },
  { value: 'after_evaluation', label: 'بعد تقييم الطبيب' },
]

export function ServiceListPage() {
  return (
    <CrudPage
      title="الخدمات"
      subtitle="ما تقدّمه العيادة وأسعاره"
      resource={api.services}
      createLabel="إضافة خدمة"
      searchPlaceholder="ابحث باسم الخدمة…"
      beforeTable={
        <p className="ui-muted">
          أي عيادة تقدّم أي خدمة (لتظهر في الحجز الإلكتروني): <Link to="/services/branches">الخدمات في العيادات</Link>
        </p>
      }
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
          key: 'requires_quantity',
          header: 'البيع',
          render: (row) =>
            row.requires_quantity ? (
              <>
                <Badge tone="info">بالكمية{row.quantity_unit ? ` (${row.quantity_unit})` : ''}</Badge>
                {row.doctor_sets_quantity && <Badge tone="primary">يحددها الطبيب</Badge>}
              </>
            ) : (
              'وحدة واحدة'
            ),
        },
        {
          key: 'duration_minutes',
          header: 'المدة',
          numeric: true,
          render: (row) => `${row.duration_minutes} د`,
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
          label: 'السعر الأساسي (لكل وحدة إن كانت تُباع بالكمية)',
          type: 'money',
          required: true,
          default: 0,
        },
        {
          name: 'requires_quantity',
          label: 'تُباع بالكمية',
          type: 'checkbox',
          span: 2,
          hint: 'لبعض الخدمات والمنتجات كمية (نبضات، مل، وحدات…): يصبح السعر لكل وحدة، وإجمالي الحجز = السعر × الكمية. اتركها فارغة لما يُباع كشيء واحد.',
        },
        {
          name: 'doctor_sets_quantity',
          label: 'الطبيب يحدد الكمية أثناء الجلسة',
          type: 'checkbox',
          span: 2,
          hint: 'يُحجز بكمية تقديرية (أو بأقل كمية)، ثم يحدد الطبيب الكمية الفعلية داخل العيادة فيتحدد مبلغ الخدمة: السعر × الكمية، ويُحصَّل الفرق من الاستقبال.',
        },
        { name: 'quantity_unit', label: 'اسم الوحدة', hint: 'مثل: نبضة، مل، وحدة. يظهر بجانب الكمية.' },
        { name: 'min_quantity', label: 'أقل كمية', type: 'number', default: 1 },
        { name: 'max_quantity', label: 'أكبر كمية (اختياري)', type: 'number' },
        {
          name: 'price_display',
          label: 'كيف يُعرض السعر للعامة',
          type: 'select',
          options: PRICE_DISPLAY,
          default: 'fixed',
          hint: '«يبدأ من» للخدمات التي قد يزيد سعرها؛ «بعد التقييم» حين لا يُعرف السعر قبل كشف الطبيب.',
        },
        {
          name: 'duration_minutes',
          label: 'مدة الجلسة (دقيقة)',
          type: 'number',
          default: 30,
          hint: 'تُستخدم لتقسيم مواعيد الطبيب المتاحة.',
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
