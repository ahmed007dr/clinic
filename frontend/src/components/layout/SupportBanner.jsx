import { useEffect, useState } from 'react'

import { api } from '@/api'
import { Button } from '@/components/ui'
import { useAuth } from '@/hooks/useAuth'
import { APP_BASENAME } from '@/lib/config'

/**
 * Shown on every clinic screen while a developer is signed in as this account
 * for support: who, how long is left, and the way back to the portal. The
 * server ends the session by itself when the time is up.
 */
export function SupportBanner() {
  const { support } = useAuth()
  const [now, setNow] = useState(() => Date.now())
  const [leaving, setLeaving] = useState(false)

  useEffect(() => {
    if (!support) return undefined
    const timer = setInterval(() => setNow(Date.now()), 15000)
    return () => clearInterval(timer)
  }, [support])

  if (!support) return null
  const minutes = Math.max(0, Math.ceil((support.until * 1000 - now) / 60000))

  return (
    <div className="support-banner" role="status">
      <span>
        وضع الدعم الفني — <span dir="ltr">{support.operator_email}</span> · متبقٍ {minutes} دقيقة. كل تعديل يُسجَّل
        باسم الدعم ويظهر لمالك المجموعة.
      </span>
      <Button
        size="sm"
        loading={leaving}
        onClick={async () => {
          setLeaving(true)
          try {
            const { redirect } = await api.auth.endSupport()
            window.location.assign(redirect)
          } catch {
            window.location.assign(`${APP_BASENAME}/platform/login`)
          }
        }}
      >
        إنهاء والعودة للمنصة
      </Button>
    </div>
  )
}
