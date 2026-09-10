import { useState } from 'react'

import { Button, Tabs } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'
import { useDocumentTitle } from '@/hooks/useDebounce'

import '@/features/clinical/allergy.css'

import {
  AppointmentsPanel,
  FilesPanel,
  LabsPanel,
  PaymentsPanel,
  PlansPanel,
  PrescriptionsPanel,
  VisitsPanel,
} from './PortalPanels'
import { usePortal } from './PortalContext'
import { RequestAppointment } from './RequestAppointment'

const TABS = [
  { id: 'appointments', label: 'مواعيدي', Panel: AppointmentsPanel },
  { id: 'prescriptions', label: 'الروشتات', Panel: PrescriptionsPanel },
  { id: 'labs', label: 'التحاليل', Panel: LabsPanel },
  { id: 'files', label: 'المستندات', Panel: FilesPanel },
  { id: 'plans', label: 'خطط العلاج', Panel: PlansPanel },
  { id: 'visits', label: 'الزيارات', Panel: VisitsPanel },
  { id: 'payments', label: 'المدفوعات', Panel: PaymentsPanel },
]

export function PortalHomePage() {
  const { api, me, setMe } = usePortal()
  const [tab, setTab] = useState('appointments')
  const [requesting, setRequesting] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const allergies = useAsync(() => api.allergies(), [api])

  useDocumentTitle(me.clinic)

  const Panel = TABS.find((t) => t.id === tab).Panel

  return (
    <div className="portal">
      <header className="portal__header">
        <strong className="portal__clinic">{me.clinic}</strong>
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

        <Button variant="primary" block onClick={() => setRequesting(true)}>طلب موعد</Button>

        <Tabs items={TABS.map(({ id, label }) => ({ id, label }))} active={tab} onChange={setTab} />
        <section className="portal__panel">
          <Panel key={`${tab}-${refreshKey}`} />
        </section>
      </main>

      <RequestAppointment
        open={requesting}
        onClose={() => setRequesting(false)}
        onDone={() => {
          setRequesting(false)
          setTab('appointments')
          setRefreshKey((k) => k + 1)
        }}
      />
    </div>
  )
}
