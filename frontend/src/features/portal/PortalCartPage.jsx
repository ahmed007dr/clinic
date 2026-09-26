import { useState } from 'react'
import { Link } from 'react-router-dom'

import { LanguageToggle } from '@/components/layout/LanguageToggle'
import { Badge, Button, EmptyState, Input, Loading, Textarea } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDebounce'
import { useToast } from '@/hooks/useToast'
import { formatMoney } from '@/lib/format'

import { lineTotal, useCart } from './cart'
import { withNext } from './next'
import { usePortal } from './PortalContext'

/**
 * «طلباتي» before it is sent — the basket (docs/16).
 *
 * The lines are grouped by clinic because each clinic decides its own order. A
 * visitor can fill it without an account; sending needs a signed-in customer, and
 * signing in or up brings them straight back here with the basket intact. The
 * prices shown are the customer's own estimate — the server works them out again.
 */
export function PortalCartPage() {
  const { api, slug, me, loading } = usePortal()
  const toast = useToast()
  const cart = useCart(slug)
  const [notes, setNotes] = useState('')
  const [contact, setContact] = useState('')
  const [payment, setPayment] = useState('manual')
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(null)
  useDocumentTitle('طلباتي')

  const here = `/portal/${slug}/cart`
  const groups = []
  for (const item of cart.items) {
    let group = groups.find((g) => g.branch === item.branch)
    if (!group) groups.push((group = { branch: item.branch, name: item.branch_name, lines: [] }))
    group.lines.push(item)
  }
  const totalOf = (lines) => lines.reduce((sum, line) => sum + (lineTotal(line) ?? 0), 0)
  const estimate = (lines) => lines.some((line) => !line.price_is_final || lineTotal(line) === null)
  const missing = cart.items.find(
    (line) => line.requires_quantity && !line.doctor_sets_quantity && !(Number(line.quantity) > 0),
  )

  const send = async () => {
    setSending(true)
    try {
      const orders = await api.sendOrder({
        items: cart.items.map((line) => ({
          service: line.service, branch: line.branch, ...(line.requires_quantity && line.quantity ? { quantity: line.quantity } : {}),
          ...(line.doctor ? { doctor: line.doctor } : {}), ...(line.slot ? { slot: line.slot } : {}),
        })),
        notes, preferred_contact: contact, payment_preference: payment,
      })
      cart.clear()
      setSent(orders)
    } catch (caught) {
      const detail = caught.fields?.items ? [].concat(caught.fields.items).join(' ') : caught.message
      toast.error(detail)
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="portal">
      <header className="portal__header">
        <strong className="portal__clinic">طلباتي</strong>
        <LanguageToggle />
      </header>
      <main className="portal__content portal__content--wide">
        <nav className="portal-crumbs" aria-label="المسار">
          <Link to={`/portal/${slug}`}>الرئيسية</Link>
          <span aria-hidden="true">›</span>
          <Link to={`/portal/${slug}/cart`}>طلباتي</Link>
        </nav>

        {loading ? (
          <Loading />
        ) : sent ? (
          <Sent orders={sent} slug={slug} />
        ) : cart.count === 0 ? (
          <EmptyState
            title="طلباتك فارغة"
            message="اختر خدمة ثم عيادة وأضفها إلى طلباتك."
            action={<Link className="ui-btn ui-btn--primary" to={`/portal/${slug}`}>تصفح الخدمات</Link>}
          />
        ) : (
          <>
            <h1 className="portal__hello">طلباتي</h1>
            {groups.map((group) => (
              <section key={group.branch} className="portal-card portal-order" aria-label={group.name}>
                <h2 className="portal__section-title">{group.name}</h2>
                <ul className="portal__list">
                  {group.lines.map((line) => (
                    <li key={line.service} className="portal-cart-line">
                      <div>
                        <strong>{line.service_name}</strong>
                        {line.unit_price === null ? (
                          <div className="ui-muted">السعر بعد تقييم الطبيب</div>
                        ) : (
                          <div className="ui-muted">
                            {formatMoney(lineTotal(line))}{!line.price_is_final && ' (تقديري)'}
                          </div>
                        )}
                        {line.slot && <div className="ui-muted">الموعد المفضل: <span dir="ltr">{line.slot}</span></div>}
                      </div>
                      {line.requires_quantity && (
                        <Input
                          label={`الكمية (${line.quantity_unit || 'وحدة'})`} type="number" inputMode="decimal"
                          min={line.min_quantity} max={line.max_quantity || undefined} step="any"
                          value={line.quantity ?? ''}
                          placeholder={line.doctor_sets_quantity ? 'يحددها الطبيب' : ''}
                          onChange={(event) => cart.setQuantity(line, event.target.value)}
                        />
                      )}
                      <Button size="sm" variant="ghost" onClick={() => cart.remove(line)}>حذف</Button>
                    </li>
                  ))}
                </ul>
                <div className="portal-cart-total">
                  {estimate(group.lines) ? 'الإجمالي التقديري' : 'الإجمالي'}: <strong>{formatMoney(totalOf(group.lines))}</strong>
                </div>
              </section>
            ))}

            <div className="portal-card portal-order">
              <Input
                label="أفضل وقت للاتصال بك (اختياري)" value={contact} maxLength={100}
                placeholder="مثال: مساءً بعد الخامسة"
                onChange={(event) => setContact(event.target.value)}
              />
              <Textarea
                label="ملاحظات للعيادة (اختياري)" value={notes} maxLength={1000} rows={3}
                onChange={(event) => setNotes(event.target.value)}
              />
              <fieldset className="portal-when">
                <legend>كيف تفضّل الدفع؟</legend>
                <label>
                  <input type="radio" name="payment" checked={payment === 'manual'} onChange={() => setPayment('manual')} />{' '}
                  يدوياً: تحويل (بنكي / محفظة / إنستاباي) أو عند الوصول للعيادة
                </label>
                <label>
                  <input type="radio" name="payment" checked={payment === 'online'} onChange={() => setPayment('online')} />{' '}
                  أونلاين: أدفع من حسابي بعد تحديد الموعد
                </label>
                <span className="ui-muted">لا يُطلب منك أي مبلغ الآن؛ العيادة توافق أولاً.</span>
              </fieldset>
              {groups.length > 1 && (
                <p className="ui-muted">
                  ستُرسل {groups.length} طلبات، واحد لكل عيادة، وتقرر كل عيادة في طلبها.
                </p>
              )}
              {me ? (
                <Button variant="primary" onClick={send} disabled={sending || Boolean(missing)}>
                  {sending ? 'جارٍ الإرسال…' : 'إرسال الطلب'}
                </Button>
              ) : (
                <div className="portal-hero__actions">
                  <span className="ui-muted">سجّل الدخول لإرسال طلبك — طلباتك محفوظة.</span>
                  <Link className="ui-btn ui-btn--primary" to={withNext(`/portal/${slug}/login`, here)}>تسجيل الدخول</Link>
                  <Link className="ui-btn ui-btn--secondary" to={withNext(`/portal/${slug}/signup`, here)}>إنشاء حساب</Link>
                </div>
              )}
              {missing && <span className="ui-muted" role="alert">اكتب كمية «{missing.service_name}».</span>}
              <p className="ui-muted">
                بعد الإرسال يصلك بريد بطلباتك، وتوافق العيادة، ثم تتصل بك خدمة العملاء. الدفع عند الوصول للعيادة.
              </p>
            </div>
          </>
        )}
      </main>
    </div>
  )
}

function Sent({ orders, slug }) {
  return (
    <div className="portal-card portal-order" role="status">
      <h1 className="portal__hello">استلمنا طلبك</h1>
      <p>
        {orders.length === 1 ? 'طلبك الآن' : 'طلباتك الآن'} بانتظار موافقة العيادة. أرسلنا إليك بريداً بالتفاصيل إن كان بريدك مسجّلاً،
        وبعد الموافقة تتصل بك خدمة العملاء لتحديد الطبيب والموعد.
      </p>
      <ul className="portal__list">
        {orders.map((order) => (
          <li key={order.uuid}>
            <Badge tone="info">{order.serial_number}</Badge> {order.branch.name} — {order.lines.map((l) => l.service_name).join('، ')}
          </li>
        ))}
      </ul>
      <Link className="ui-btn ui-btn--primary" to={`/portal/${slug}?tab=orders`}>متابعة طلباتي</Link>
    </div>
  )
}
