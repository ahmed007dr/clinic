import { api } from '@/api'
import { Badge } from '@/components/ui'
import { CrudPage } from '@/components/data/CrudPage'
import { useAuth } from '@/hooks/useAuth'
import { formatMoney } from '@/lib/format'

/**
 * Each doctor's contract with the group: per service, the price a booking
 * gets and the doctor's share of what is paid. Management writes it; a doctor
 * reads their own here and nothing else (the server enforces both).
 *
 * Leaving the price blank means the service's catalogue price; leaving the
 * percentage blank means the doctor's default (set on the employees screen).
 * A change applies from then on — earned shares keep the figures they were
 * earned at.
 */
export function DoctorRatesPage() {
  const { permissions } = useAuth()
  const manage = permissions.is_admin

  return (
    <CrudPage
      title={manage ? 'تعاقدات الأطباء' : 'تعاقدي'}
      subtitle={
        manage
          ? 'السعر ونسبة الطبيب لكل خدمة. التعديل يسري على العمليات الجديدة فقط.'
          : 'أسعار خدماتك ونسبتك منها كما حددتها إدارة المجمع.'
      }
      resource={api.doctorRates}
      canCreate={manage}
      canEdit={manage}
      canDelete={manage}
      createLabel="إضافة سطر تعاقد"
      searchPlaceholder="ابحث بالطبيب أو الخدمة…"
      columns={[
        { key: 'doctor_name', header: 'الطبيب' },
        { key: 'service_name', header: 'الخدمة' },
        {
          key: 'price',
          header: 'السعر',
          numeric: true,
          render: (row) =>
            row.price !== null ? (
              <strong>{formatMoney(row.price)}</strong>
            ) : (
              <span className="ui-muted">{formatMoney(row.service_base_price)} (سعر الخدمة)</span>
            ),
        },
        {
          key: 'commission_percent',
          header: 'نسبة الطبيب',
          numeric: true,
          render: (row) =>
            row.commission_percent !== null ? (
              `${Number(row.commission_percent)}%`
            ) : (
              <span className="ui-muted">النسبة الافتراضية</span>
            ),
        },
        {
          key: 'is_active',
          header: 'الحالة',
          render: (row) => (
            <Badge tone={row.is_active ? 'ok' : 'neutral'}>{row.is_active ? 'سارٍ' : 'موقوف'}</Badge>
          ),
        },
      ]}
      fields={[
        { name: 'doctor', label: 'الطبيب', type: 'relation', resource: api.doctors, required: true },
        { name: 'service', label: 'الخدمة', type: 'relation', resource: api.services, required: true },
        {
          name: 'price',
          label: 'السعر',
          type: 'money',
          hint: 'اتركه فارغاً لاستخدام سعر الخدمة.',
        },
        {
          name: 'commission_percent',
          label: 'نسبة الطبيب %',
          type: 'number',
          hint: 'من المبلغ المدفوع فعلاً. اتركها فارغة لاستخدام نسبة الطبيب الافتراضية.',
        },
        { name: 'is_active', label: 'سارٍ', type: 'checkbox', default: true },
        { name: 'notes', label: 'ملاحظات', span: 2 },
      ]}
      emptyMessage={
        manage ? 'أضف لكل طبيب أسعار خدماته ونسبته منها.' : 'لم تُحدَّد أسعار أو نسب خاصة بك بعد.'
      }
      deleteWarning="يُحذف سطر التعاقد؛ النسب المستحقة سابقاً لا تتغير."
    />
  )
}
