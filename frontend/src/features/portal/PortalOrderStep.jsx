import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Button, EmptyState, ErrorState, Input, Loading } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { formatMoney } from '@/lib/format'

import { useCart } from './cart'
import { priceText, unitOf } from './catalogText'
import { usePortal } from './PortalContext'

/**
 * The step after choosing a clinic (docs/16): how much of it, and «أضف إلى طلباتي».
 *
 * Nothing here books a doctor's time. The customer says what they want and where;
 * the clinic approves, customer service phones, and only then are the doctor and
 * time settled. A customer who does want a particular doctor and time still can —
 * the link below goes to the doctor-and-time path.
 */
export function PortalOrderStep({ service, branch }) {
  const { api, slug } = usePortal()
  const navigate = useNavigate()
  const toast = useToast()
  const cart = useCart(slug)
  const { data, loading, error, reload } = useAsync(() => api.catalogDoctors(service, branch), [api, service, branch])
  const inBasket = cart.items.find((item) => item.service === service && item.branch === branch)
  const [quantity, setQuantity] = useState(inBasket?.quantity ?? '')

  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />
  if (data.doctors.length === 0) {
    return <EmptyState title="هذه الخدمة غير متاحة للطلب في هذه العيادة حالياً" />
  }

  const s = data.service
  const byQuantity = s.requires_quantity
  const prices = data.doctors.map((d) => d.price).filter((p) => p !== null && p !== undefined).map(Number)
  const unitPrice = prices.length ? Math.min(...prices) : null
  const final =
    prices.length > 0 && new Set(prices).size === 1 && s.price_display === 'fixed' && !(byQuantity && s.doctor_sets_quantity)
  const asked = Number(quantity)
  const shown = asked > 0 ? asked : s.doctor_sets_quantity ? Number(s.min_quantity) : 0
  const total = unitPrice === null ? null : byQuantity ? unitPrice * shown : unitPrice

  let problem = ''
  if (byQuantity && !(asked > 0) && !s.doctor_sets_quantity) problem = 'اكتب الكمية.'
  else if (byQuantity && asked > 0 && asked < Number(s.min_quantity)) problem = `أقل كمية ${Number(s.min_quantity)}.`
  else if (byQuantity && asked > 0 && s.max_quantity && asked > Number(s.max_quantity)) problem = `أكبر كمية ${Number(s.max_quantity)}.`

  const add = () => {
    cart.add({
      service, branch, service_name: s.name, branch_name: data.branch.name,
      quantity: byQuantity ? (asked > 0 ? String(asked) : '') : null,
      unit_price: unitPrice === null ? null : String(unitPrice), price_is_final: final,
      requires_quantity: byQuantity, doctor_sets_quantity: byQuantity && s.doctor_sets_quantity,
      quantity_unit: s.quantity_unit || '', min_quantity: s.min_quantity, max_quantity: s.max_quantity,
      price_display: s.price_display,
    })
    toast.success('أُضيفت الخدمة إلى طلباتي.')
    navigate(`/portal/${slug}/cart`)
  }

  return (
    <>
      <h1 className="portal__hello">{s.name}</h1>
      <p className="ui-muted">
        في <strong>{data.branch.name}</strong> — {s.duration_minutes} دقيقة تقريباً
      </p>

      <div className="portal-card portal-order">
        <div className="portal-catalog__meta">
          <strong>{priceText(s.price_display, unitPrice, unitOf(s))}</strong>
          {prices.length > 1 && <span className="ui-muted">يختلف السعر حسب الطبيب</span>}
        </div>

        {byQuantity && (
          <Input
            label={`الكمية (${s.quantity_unit || 'وحدة'})`} type="number" inputMode="decimal"
            min={s.min_quantity} max={s.max_quantity || undefined} step="any"
            required={!s.doctor_sets_quantity}
            value={quantity} onChange={(event) => setQuantity(event.target.value)}
            error={quantity && problem ? problem : undefined}
            hint={[
              `الأدنى ${Number(s.min_quantity)}`,
              s.max_quantity && `الأقصى ${Number(s.max_quantity)}`,
              s.doctor_sets_quantity && 'الكمية تقديرية؛ يحددها الطبيب أثناء الجلسة ويُحسب المبلغ عليها',
            ].filter(Boolean).join(' — ')}
          />
        )}

        {total !== null && (
          <span role="status">
            {final ? 'الإجمالي' : 'الإجمالي التقديري'}: <strong>{formatMoney(total)}</strong>
            {byQuantity && shown > 0 && (
              <span className="ui-muted"> ({formatMoney(unitPrice)} × {shown})</span>
            )}
          </span>
        )}

        <Button variant="primary" onClick={add} disabled={Boolean(problem)}>
          {inBasket ? 'تحديث في طلباتي' : 'أضف إلى طلباتي'}
        </Button>
        <p className="ui-muted">
          لا تُحجز أوقات الآن: بعد إرسال طلبك توافق العيادة، ثم تتصل بك خدمة العملاء لتحديد الطبيب والموعد.
        </p>
      </div>

      <p className="ui-muted">
        تفضّل طبيباً ووقتاً بعينهما؟{' '}
        <Link to={`/portal/${slug}/services/${service}/${branch}/doctors`}>احجز وقتاً محدداً مع طبيب</Link>
      </p>
    </>
  )
}
