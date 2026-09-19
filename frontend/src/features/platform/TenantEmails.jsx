import { api } from '@/api'
import { Card, CardBody, CardHeader } from '@/components/ui'
import { EmailLogView } from '@/features/admin/EmailLogView'

/** The emails one group's system sent — for support to check what a clinic
 * says it did or did not receive. Opening it is recorded in the group's audit
 * trail. */
export function TenantEmails({ tenant }) {
  return (
    <Card>
      <CardHeader title="سجل الرسائل" subtitle="ما أرسله النظام لهذه المجموعة ونصّه (للفحص والمراجعة)" />
      <CardBody>
        <EmailLogView
          deps={[tenant]}
          fetchList={(params) => api.platform.emailLog(tenant, params)}
          fetchOne={(id) => api.platform.emailLogEntry(tenant, id)}
        />
      </CardBody>
    </Card>
  )
}
