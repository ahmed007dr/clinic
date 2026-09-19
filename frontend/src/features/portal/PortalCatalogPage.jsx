import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { LanguageToggle } from '@/components/layout/LanguageToggle'
import { Button, EmptyState, ErrorState, Input, Loading, Textarea } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'
import { useDocumentTitle } from '@/hooks/useDebounce'
import { useToast } from '@/hooks/useToast'
import { formatDate, formatMoney } from '@/lib/format'

import { withNext } from './next'
import { priceText, unitOf } from './catalogText'
import { usePortal } from './PortalContext'
import { PortalOrderStep } from './PortalOrderStep'
import { PortalServiceGrid } from './PortalServiceGrid'
import { CartLink } from './CartLink'
import { usePlace } from './place'

export { priceText }

/**
 * The public catalogue (docs/15, Phase 3): choose a service, then a clinic that
 * offers it, then a doctor there. A clinic that does not offer the service never
 * appears; a doctor appears only under a clinic where they deliver it. Everything
 * comes from the server's one "bookable" rule, so nothing listed here is refused
 * later. Booking itself joins at the end of this path in a later phase.
 */
export function PortalCatalogPage({ doctors = false }) {
  const { service, branch, doctor } = useParams()
  const { slug } = usePortal()
  useDocumentTitle('الخدمات والأسعار')

  return (
    <div className="portal">
      <header className="portal__header">
        <strong className="portal__clinic">الخدمات والأسعار</strong>
        <span className="portal__header-tools">
          <CartLink />
          <LanguageToggle />
        </span>
      </header>
      <main className="portal__content portal__content--wide">
        <nav className="portal-crumbs" aria-label="المسار">
          <Link to={`/portal/${slug}`}>الرئيسية</Link>
          <span aria-hidden="true">›</span>
          <Link to={`/portal/${slug}/services`}>الخدمات</Link>
        </nav>
        {!service && <PortalServiceGrid heading="الخدمات والأسعار" />}
        {service && !branch && <BranchList service={service} />}
        {service && branch && !doctor && (doctors
          ? <DoctorList service={service} branch={branch} />
          : <PortalOrderStep service={service} branch={branch} />)}
        {service && branch && doctor && <SlotPicker service={service} branch={branch} doctor={doctor} />}
      </main>
    </div>
  )
}

function useCatalog(load, deps) {
  const { data, loading, error, reload } = useAsync(load, deps)
  return { data, loading, error, reload }
}

function BranchList({ service }) {
  const { api, slug } = usePortal()
  const place = usePlace()
  const regions = useAsync(() => api.catalogRegions(), [api])
  const { data, loading, error, reload } = useCatalog(
    () => api.catalogBranches(service, place.query), [api, service, place.query],
  )
  if (error) return <ErrorState error={error} onRetry={reload} />
  const unit = unitOf(data?.service)

  return (
    <>
      <h1 className="portal__hello">{data?.service.name ?? 'الخدمة'}</h1>
      <p className="ui-muted">
        اختر العيادة — تظهر فقط العيادات التي تقدّم هذه الخدمة، والأقرب إليك أولاً.
      </p>

      <div className="portal-place" role="group" aria-label="موقعك">
        <Button size="sm" variant="secondary" onClick={place.locate} disabled={place.locating}>
          {place.locating ? 'جارٍ تحديد موقعك…' : 'استخدم موقعي'}
        </Button>
        <label className="portal-place__region">
          <span className="ui-muted">أو اختر محافظتك</span>
          <select className="ui-input" value={place.governorate} onChange={(event) => place.chooseGovernorate(event.target.value)}>
            <option value="">—</option>
            {(regions.data ?? []).map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </label>
        {place.hasPoint && (
          <Button size="sm" variant="ghost" onClick={place.forget}>إيقاف الموقع</Button>
        )}
        {place.problem && <span className="portal-place__problem" role="alert">{place.problem}</span>}
      </div>

      {loading && !data ? (
        <Loading />
      ) : data.branches.length === 0 ? (
        <EmptyState title="لا توجد عيادة تقدّم هذه الخدمة للطلب حالياً" />
      ) : (
        <ul className="portal__list">
          {data.branches.map((branch) => (
            <li key={branch.uuid} className="portal-card">
              <Link className="portal-catalog__title" to={`/portal/${slug}/services/${service}/${branch.uuid}`}>
                {branch.name}
              </Link>
              {branch.nearest && <span className="portal-nearest">الأقرب إليك</span>}
              {branch.address && <span className="portal-about__text">{branch.address}</span>}
              <div className="portal-catalog__meta">
                {branch.governorate && <span>{branch.governorate}</span>}
                {branch.distance_km !== null && branch.distance_km !== undefined && (
                  <span dir="ltr">{branch.distance_km} km</span>
                )}
                <span>{branch.doctors_count > 1 ? `${branch.doctors_count} أطباء` : 'طبيب واحد'}</span>
                <strong>{priceText(data.service.price_display, branch.from_price, unit)}</strong>
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

function DoctorList({ service, branch }) {
  const { api, slug, me } = usePortal()
  const { data, loading, error, reload } = useCatalog(
    () => api.catalogDoctors(service, branch), [api, service, branch],
  )
  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />

  return (
    <>
      <h1 className="portal__hello">{data.service.name} — {data.branch.name}</h1>
      <p className="ui-muted">
        الأطباء الذين يقدّمون هذه الخدمة في هذه العيادة والسعر لدى كل منهم.
      </p>
      {data.doctors.length === 0 ? (
        <EmptyState title="لا يوجد طبيب متاح لهذه الخدمة في هذه العيادة حالياً" />
      ) : (
        <ul className="portal__list">
          {data.doctors.map((doctor) => (
            <li key={doctor.uuid} className="portal-card portal-doctor">
              <span className="portal-doctor__name">د. {doctor.name}</span>
              {doctor.specializations.length > 0 && (
                <span className="portal-doctor__specialties">{doctor.specializations.join('، ')}</span>
              )}
              {doctor.tagline && <span className="portal-doctor__tagline">{doctor.tagline}</span>}
              <strong>{priceText(data.service.price_display, doctor.price, unitOf(data.service))}</strong>
              <Link className="ui-btn ui-btn--secondary ui-btn--sm"
                to={`/portal/${slug}/services/${service}/${branch}/${doctor.uuid}`}>
                الأوقات المتاحة
              </Link>
            </li>
          ))}
        </ul>
      )}
      <p className="ui-muted">
        {me ? (
          'لطلب موعد استخدم «طلب موعد» في حسابك.'
        ) : (
          <>
            لطلب موعد <Link to={`/portal/${slug}/login`}>سجّل الدخول</Link> أو{' '}
            <Link to={`/portal/${slug}/signup`}>أنشئ حسابًا</Link>.
          </>
        )}
      </p>
    </>
  )
}

/**
 * The days that still have a time, then the times on the chosen day — the
 * server's own answer (working hours − time off − holidays − bookings). A chosen
 * time becomes a request (or, at a clinic that confirms website bookings at
 * once, a confirmed booking); the server checks the choice and the time again.
 * Someone not yet signed in is sent to sign in or up and brought straight back
 * to this same choice.
 */
function SlotPicker({ service, branch, doctor }) {
  const { api, slug, me } = usePortal()
  const navigate = useNavigate()
  const toast = useToast()
  const [params] = useSearchParams()
  const choice = useMemo(() => ({ service, branch, doctor }), [service, branch, doctor])
  const [day, setDay] = useState(params.get('day') || '')
  const [slot, setSlot] = useState(params.get('time') || '')
  const [notes, setNotes] = useState('')
  // Arriving from «طلب تغيير الموعد»: the chosen time asks to move that booking.
  const reschedule = params.get('reschedule')
  const [sending, setSending] = useState(false)
  const days = useCatalog(() => api.catalogDays(choice), [api, choice])
  // How the service is sold (by quantity?) and this doctor's price for it.
  const sold = useCatalog(() => api.catalogDoctors(service, branch), [api, service, branch])
  const soldService = sold.data?.service
  const doctorPrice = sold.data?.doctors?.find((d) => d.uuid === doctor)?.price
  const byQuantity = Boolean(soldService?.requires_quantity)
  const [quantity, setQuantity] = useState(params.get('quantity') || '')
  // Left empty for a service the doctor sizes, the estimate is the smallest quantity.
  const shownQuantity = Number(quantity) > 0 ? Number(quantity) : soldService?.doctor_sets_quantity ? Number(soldService.min_quantity) : 0
  const total = byQuantity && shownQuantity > 0 && doctorPrice ? Number(doctorPrice) * shownQuantity : null
  const times = useAsync(() => api.catalogSlots(choice, day), [api, choice, day], { skip: !day })

  if (days.loading) return <Loading />
  if (days.error) return <ErrorState error={days.error} onRetry={days.reload} />

  // Where sign-in / sign-up brings the person back to: this doctor, this time.
  const here = `/portal/${slug}/services/${service}/${branch}/${doctor}?day=${day}&time=${slot}${
    quantity ? `&quantity=${quantity}` : ''
  }${
    reschedule ? `&reschedule=${reschedule}` : ''
  }`

  const send = async () => {
    setSending(true)
    try {
      if (reschedule) {
        await api.rescheduleAppointment(reschedule, { slot: `${day} ${slot}`, notes })
        toast.success('تم إرسال طلب تغيير الموعد. ستتصل بك العيادة.')
      } else {
        const result = await api.requestAppointment({
          service, branch, doctor, slot: `${day} ${slot}`, notes, ...(byQuantity && quantity ? { quantity } : {}),
        })
        toast.success(
          result.status === 'waiting'
            ? 'تم تأكيد موعدك.'
            : 'تم إرسال طلبك. ستتصل بك العيادة لتأكيد الموعد.',
        )
      }
      navigate(`/portal/${slug}`, { replace: true })
    } catch (caught) {
      toast.error(
        caught.fields?.slot || caught.fields?.quantity
          ? [].concat(caught.fields.slot ?? caught.fields.quantity).join(' ')
          : caught.message,
      )
      if (caught.status === 409) {
        setSlot('')
        times.reload()
      }
    } finally {
      setSending(false)
    }
  }

  return (
    <>
      <h1 className="portal__hello">{reschedule ? 'اختر الوقت الجديد' : 'اختر اليوم والوقت'}</h1>
      {days.data.days.length === 0 ? (
        <EmptyState title="لا توجد أوقات متاحة لهذا الطبيب حالياً" message="حاول لاحقاً أو اتصل بالعيادة." />
      ) : (
        <>
          <ul className="portal-choices" aria-label="الأيام المتاحة">
            {days.data.days.map((d) => (
              <li key={d}>
                <button type="button" className={`portal-choice ${d === day ? 'portal-choice--on' : ''}`}
                  onClick={() => { setDay(d); setSlot('') }}>
                  {formatDate(d)}
                </button>
              </li>
            ))}
          </ul>
          {/* `times` is skipped until a day is picked, so for one render after the click it has neither data nor a
              loading flag yet: no data and no error means the request is about to start. */}
          {day && (times.loading || (!times.data && !times.error) ? <Loading /> : times.error ? <ErrorState error={times.error} onRetry={times.reload} /> : (
            times.data.slots.length === 0 ? (
              <EmptyState title="لا توجد أوقات في هذا اليوم" />
            ) : (
              <ul className="portal-choices" aria-label="الأوقات المتاحة">
                {times.data.slots.map((t) => (
                  <li key={t}>
                    <button type="button" dir="ltr" className={`portal-choice ${t === slot ? 'portal-choice--on' : ''}`}
                      onClick={() => setSlot(t)}>
                      {t}
                    </button>
                  </li>
                ))}
              </ul>
            )
          ))}
          {day && slot && (
            <div className="portal-card" role="status">
              <span>
                الوقت المختار: <strong>{formatDate(day)} — <span dir="ltr">{slot}</span></strong>
              </span>
              {byQuantity && (
                <>
                  <Input
                    label={`الكمية (${soldService.quantity_unit || 'وحدة'})`} type="number" inputMode="decimal"
                    min={soldService.min_quantity} max={soldService.max_quantity || undefined} step="any"
                    required={!soldService.doctor_sets_quantity}
                    value={quantity} onChange={(e) => setQuantity(e.target.value)}
                    hint={[
                      `الأدنى ${Number(soldService.min_quantity)}`,
                      soldService.max_quantity && `الأقصى ${Number(soldService.max_quantity)}`,
                      soldService.doctor_sets_quantity && 'الكمية تقديرية؛ يحددها الطبيب أثناء الجلسة ويُحسب المبلغ عليها',
                    ].filter(Boolean).join(' — ')}
                  />
                  {total !== null && (
                    <span role="status">
                      {soldService.doctor_sets_quantity && !(Number(quantity) > 0) ? 'الإجمالي التقديري' : 'الإجمالي'}:{' '}
                      <strong>{formatMoney(total)}</strong>{' '}
                      <span className="ui-muted">({formatMoney(doctorPrice)} × {shownQuantity})</span>
                    </span>
                  )}
                </>
              )}
              {me ? (
                <>
                  <Textarea label="سبب الزيارة (اختياري)" value={notes} maxLength={1000}
                    onChange={(e) => setNotes(e.target.value)} />
                  <Button variant="primary" block loading={sending} onClick={send}>
                    {reschedule ? 'إرسال طلب تغيير الموعد' : 'إرسال طلب الموعد'}
                  </Button>
                  <span className="ui-muted">
                    هذا طلب؛ تتصل بك العيادة لتأكيد الموعد النهائي (إلا إن كانت العيادة تؤكّد الحجز فوراً).
                  </span>
                </>
              ) : (
                <>
                  <span className="ui-muted">سجّل الدخول أو أنشئ حساباً لإكمال الطلب — نعود بك إلى هذا الاختيار.</span>
                  <div className="portal-hero__actions">
                    <Link className="ui-btn ui-btn--primary" to={withNext(`/portal/${slug}/login`, here)}>تسجيل الدخول</Link>
                    <Link className="ui-btn ui-btn--secondary" to={withNext(`/portal/${slug}/signup`, here)}>إنشاء حساب</Link>
                  </div>
                </>
              )}
            </div>
          )}
        </>
      )}
    </>
  )
}
