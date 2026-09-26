import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Button, EmptyState, ErrorState, Input, Loading } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { formatDate, formatMoney } from '@/lib/format'

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
  // The customer's preferred appointment — optional, and it holds nothing (docs/16, R2).
  const [doctorPick, setDoctorPick] = useState(inBasket?.doctor ?? '')
  const [day, setDay] = useState(inBasket?.slot ? inBasket.slot.slice(0, 10) : '')
  const [time, setTime] = useState(inBasket?.slot ? inBasket.slot.slice(11, 16) : '')
  const choice = useMemo(
    () => ({ service, branch, ...(doctorPick ? { doctor: doctorPick } : {}) }), [service, branch, doctorPick],
  )
  const days = useAsync(() => api.catalogBranchDays(choice), [api, choice])
  const times = useAsync(() => api.catalogBranchTimes(choice, day), [api, choice, day], { skip: !day })

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
      doctor: doctorPick, slot: day && time ? `${day} ${time}` : '',
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

        <fieldset className="portal-when">
          <legend>الموعد المفضل (اختياري)</legend>
          <label className="portal-place__region">
            <span className="ui-muted">الطبيب</span>
            <select className="ui-input" value={doctorPick}
              onChange={(event) => { setDoctorPick(event.target.value); setDay(''); setTime('') }}>
              <option value="">أي طبيب متاح</option>
              {data.doctors.map((d) => <option key={d.uuid} value={d.uuid}>د. {d.name}</option>)}
            </select>
          </label>
          {days.loading ? (
            <Loading />
          ) : (days.data?.days ?? []).length === 0 ? (
            <span className="ui-muted">لا توجد أوقات متاحة حالياً — يحددها الاستقبال معك عند الاتصال.</span>
          ) : (
            <ul className="portal-choices" aria-label="الأيام المتاحة">
              {days.data.days.map((d) => (
                <li key={d}>
                  <button type="button" className={`portal-choice ${d === day ? 'portal-choice--on' : ''}`}
                    onClick={() => { setDay(d === day ? '' : d); setTime('') }}>
                    {formatDate(d)}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {day && (times.loading || (!times.data && !times.error) ? <Loading /> : times.error ? (
            <ErrorState error={times.error} onRetry={times.reload} />
          ) : (
            <ul className="portal-choices" aria-label="الأوقات المتاحة">
              {times.data.times.map((t) => (
                <li key={t.time}>
                  <button type="button" dir="ltr" className={`portal-choice ${t.time === time ? 'portal-choice--on' : ''}`}
                    onClick={() => setTime(t.time === time ? '' : t.time)}>
                    {t.time}
                  </button>
                </li>
              ))}
            </ul>
          ))}
          {day && time && (
            <span role="status">
              الموعد المفضل: <strong>{formatDate(day)} — <span dir="ltr">{time}</span></strong>{' '}
              <span className="ui-muted">(لا يُحجز الآن؛ تؤكده العيادة)</span>
            </span>
          )}
        </fieldset>

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
