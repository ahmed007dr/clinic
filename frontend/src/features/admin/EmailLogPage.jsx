import { api } from '@/api'
import { PageHeader } from '@/components/layout/PageHeader'

import { EmailLogView } from './EmailLogView'

/** Every email the system sent for this clinic — the Owner sees the whole
 * group's (and can narrow to one clinic), an Admin their own clinic's. Either
 * can open a message, see when it went out, and send it again. */
export function EmailLogPage() {
  return (
    <>
      <PageHeader
        title="سجل الرسائل"
        subtitle="كل رسالة أرسلها النظام: إلى من، ومتى، ونصّها كما وصل. افتح أي رسالة لرؤية القالب أو لإعادة إرسالها."
      />
      <EmailLogView fetchList={api.emailLog.list} fetchOne={api.emailLog.get} resend={api.emailLog.resend} />
    </>
  )
}
