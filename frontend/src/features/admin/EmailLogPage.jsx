import { api } from '@/api'
import { PageHeader } from '@/components/layout/PageHeader'

import { EmailLogView } from './EmailLogView'

/** Every email the system sent for this clinic — the Owner sees the whole
 * group's, an Admin their own clinic's. */
export function EmailLogPage() {
  return (
    <>
      <PageHeader
        title="سجل الرسائل"
        subtitle="كل رسالة أرسلها النظام: إلى من، ونوعها، ونصّها كما وصل. افتح أي رسالة لرؤية القالب."
      />
      <EmailLogView fetchList={api.emailLog.list} fetchOne={api.emailLog.get} />
    </>
  )
}
