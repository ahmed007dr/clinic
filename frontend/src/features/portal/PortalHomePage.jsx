import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { Button, Tabs } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'
import { useDocumentTitle } from '@/hooks/useDebounce'
import { useToast } from '@/hooks/useToast'

import '@/features/clinical/allergy.css'

import {
  AppointmentsPanel,
  OrdersPanel,
  FilesPanel,
  LabsPanel,
  PaymentsPanel,
  PlansPanel,
  PrescriptionsPanel,
  VisitsPanel,
} from './PortalPanels'
import { usePortal } from './PortalContext'
import { PortalAbout } from './PortalAbout'
import { CartLink } from './CartLink'
import { PortalProfile } from './PortalProfile'

const TABS = [
  { id: 'appointments', label: 'مواعيدي', Panel: AppointmentsPanel },
  { id: 'orders', label: 'طلباتي', Panel: OrdersPanel },
  { id: 'prescriptions', label: 'الروشتات', Panel: PrescriptionsPanel },
  { id: 'labs', label: 'التحاليل', Panel: LabsPanel },
  { id: 'files', label: 'المستندات', Panel: FilesPanel },
  { id: 'plans', label: 'خطط العلاج', Panel: PlansPanel },
  { id: 'visits', label: 'الزيارات', Panel: VisitsPanel },
  { id: 'payments', label: 'المدفوعات', Panel: PaymentsPanel },
  { id: 'profile', label: 'حسابي', Panel: PortalProfile },
  { id: 'about', label: 'عن العيادة', Panel: PortalAbout },
]

export function PortalHomePage() {
  const { api, me, setMe, slug } = usePortal()
  const [tab, setTab] = useState(() => {
    const asked = new URLSearchParams(window.location.search).get('tab')
    return TABS.some((t) => t.id === asked) ? asked : 'appointments'
  })
  const [refreshKey, setRefreshKey] = useState(0)
  const allergies = useAsync(() => api.allergies(), [api])
  const toast = useToast()

  useDocumentTitle(me.clinic)

  // Back from a payment gateway (api/platform_pay.py appends ?payment=).
  useEffect(() => {
    const url = new URL(window.location.href)
    const outcome = url.searchParams.get('payment')
    if (!outcome) return
    if (outcome === 'ok') toast.success('تم الدفع بنجاح. شكراً لك.')
    // Confirmed by the gateway but not yet recorded by the clinic: it shows as
    // paid only once it is (docs/15, Phase 8).
    else if (outcome === 'pending') toast.success('استلمنا الدفع وجارٍ تسجيله؛ سيظهر مدفوعاً خلال دقائق.')
    else toast.error('لم تكتمل عملية الدفع.')
    url.searchParams.delete('payment')
    window.history.replaceState(null, '', url)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const Panel = TABS.find((t) => t.id === tab).Panel

  return (
    <div className="portal">
      <header className="portal__header">
        <strong className="portal__clinic">{me.clinic}</strong>
        <CartLink />
        <Button size="sm" variant="ghost" onClick={async () => {
          try { await api.logout() } finally { setMe(null) }
        }}>
          خروج
        </Button>
      </header>

      <main className="portal__content">
        <div>
          <h1 className="portal__hello">أهلاً، {me.name}</h1>
          <span className="ui-muted">رقم الملف {me.serial_number}</span>
        </div>

        {allergies.data?.length > 0 && (
          <div className="allergy__banner" role="note">
            <strong>⚠ حساسية مسجلة:</strong>{' '}
            {allergies.data.map((a) => `${a.substance} (${a.severity_label})`).join('، ')}
          </div>
        )}

        {/* Choose a service, then a clinic near you, and add it to «طلباتي». */}
        <Link className="ui-btn ui-btn--primary ui-btn--block" to={`/portal/${slug}`}>اطلب خدمة</Link>

        <Tabs items={TABS.map(({ id, label }) => ({ id, label }))} active={tab} onChange={setTab} />
        <section className="portal__panel">
          <Panel key={`${tab}-${refreshKey}`} />
        </section>
      </main>
    </div>
  )
}
