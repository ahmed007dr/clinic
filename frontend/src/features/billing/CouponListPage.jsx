import { useState } from 'react'

import { api } from '@/api'
import { Badge, Button } from '@/components/ui'
import { CrudPage } from '@/components/data/CrudPage'
import { useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { formatDate, formatMoney } from '@/lib/format'

const STATUS = {
  available: { label: 'متاح', tone: 'ok' },
  used: { label: 'مستخدم', tone: 'neutral' },
  voided: { label: 'ملغى', tone: 'neutral' },
  expired: { label: 'منتهي', tone: 'warn' },
}

/**
 * Discount coupons — Admin and Owner only. A coupon is a fixed amount off, in
 * one patient's name, for a service (the ordinary consultation and what it is
 * worth) or a whole specialty; it is spent once, on a booking. It is the only
 * way a booking is discounted, and so the only way a patient goes in to the
 * doctor without having paid the full price. Never edited: issue another.
 */
export function CouponListPage() {
  const toast = useToast()
  const [refreshKey, setRefreshKey] = useState(0)
  const cancel = useMutation((uuid) => api.coupons.void(uuid))

  const onVoid = async (row) => {
    try {
      await cancel.run(row.uuid)
      toast.success('تم إلغاء الكوبون')
      setRefreshKey((n) => n + 1)
    } catch (error) {
      toast.error(error.message)
    }
  }

  return (
    <CrudPage
      key={refreshKey}
      title="كوبونات الخصم"
      subtitle="خصم بمبلغ ثابت باسم مريض، لخدمة أو لتخصص — يُستخدم مرة واحدة عند الحجز"
      resource={api.coupons}
      createLabel="كوبون جديد"
      canEdit={false}
      canDelete={false}
      searchPlaceholder="ابحث باسم المريض أو هاتفه أو الخدمة…"
      columns={[
        { key: 'patient_name', header: 'المريض' },
        {
          key: 'amount',
          header: 'قيمة الخصم',
          numeric: true,
          render: (row) => <strong>{formatMoney(row.amount)}</strong>,
        },
        {
          key: 'applies',
          header: 'ينطبق على',
          render: (row) =>
            row.service_name ? `الخدمة: ${row.service_name}` : `التخصص: ${row.specialization_name}`,
        },
        { key: 'expires_on', header: 'ينتهي', render: (row) => (row.expires_on ? formatDate(row.expires_on) : '—') },
        { key: 'created_by_name', header: 'أصدره', render: (row) => row.created_by_name || '—' },
        {
          key: 'status',
          header: 'الحالة',
          render: (row) => (
            <Badge tone={STATUS[row.status]?.tone ?? 'neutral'}>{STATUS[row.status]?.label ?? row.status}</Badge>
          ),
        },
        {
          key: '__void',
          header: '',
          render: (row) =>
            row.status === 'available' && (
              <Button size="sm" variant="ghost" onClick={() => onVoid(row)} disabled={cancel.submitting}>
                إلغاء
              </Button>
            ),
        },
      ]}
      fields={[
        {
          name: 'patient',
          label: 'المريض',
          type: 'relation',
          resource: api.patients,
          searchable: true,
          required: true,
          span: 2,
        },
        { name: 'amount', label: 'قيمة الخصم', type: 'money', required: true },
        { name: 'expires_on', label: 'ينتهي في', type: 'date', hint: 'اختياري.' },
        {
          name: 'service',
          label: 'الخدمة',
          type: 'relation',
          resource: api.services,
          hint: 'مثل الكشف العادي — أو اترك الخدمة فارغة واختر التخصص.',
        },
        { name: 'specialization', label: 'التخصص', type: 'relation', resource: api.specializations },
        { name: 'notes', label: 'ملاحظات', type: 'textarea', span: 2 },
      ]}
      emptyMessage="لم يُصدر أي كوبون بعد."
    />
  )
}
