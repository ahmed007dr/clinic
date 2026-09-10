import { useState } from 'react'

import { api } from '@/api'
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  DescriptionList,
  Input,
} from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useMutation } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'

export function AccountPage() {
  const { user, permissions } = useAuth()
  const toast = useToast()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')

  const change = useMutation((a, b) => api.auth.changePassword(a, b))

  const submit = async (event) => {
    event.preventDefault()
    // Checked here rather than server-side: the server has no way to know what
    // the user meant to type twice, and this is the one rule the client owns.
    if (next !== confirm) {
      toast.error('كلمتا المرور غير متطابقتين.')
      return
    }
    try {
      await change.run(current, next)
      toast.success('تم تغيير كلمة المرور')
      setCurrent('')
      setNext('')
      setConfirm('')
    } catch {
      /* per field */
    }
  }

  const granted = Object.entries({
    is_owner: 'مالك المجموعة',
    is_admin: 'إدارة العيادة',
    view_clinical: 'الاطلاع على السجلات الطبية',
    manage_billing: 'إدارة الحسابات',
    manage_staff: 'إدارة المستخدمين',
    all_branches: 'كل الفروع',
  }).filter(([key]) => permissions[key])

  return (
    <>
      <PageHeader title="حسابي" />

      <div className="ui-grid ui-grid--2" style={{ alignItems: 'start' }}>
        <Card>
          <CardHeader title="البيانات" />
          <CardBody>
            <DescriptionList
              columns={1}
              items={[
                { label: 'اسم المستخدم', value: user?.username },
                { label: 'البريد الإلكتروني', value: user?.email },
                { label: 'الدور', value: user?.role },
                { label: 'الفرع', value: user?.branch?.name },
                { label: 'العيادة', value: user?.clinic },
                {
                  label: 'الصلاحيات',
                  value: (
                    <div className="ui-row" style={{ flexWrap: 'wrap' }}>
                      {granted.length > 0 ? (
                        granted.map(([key, label]) => (
                          <Badge key={key} tone="primary">
                            {label}
                          </Badge>
                        ))
                      ) : (
                        <span className="ui-muted">صلاحيات أساسية</span>
                      )}
                    </div>
                  ),
                },
              ]}
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="تغيير كلمة المرور"
            subtitle="ستظل جلستك الحالية مفتوحة بعد التغيير"
          />
          <CardBody>
            <form onSubmit={submit} className="ui-stack">
              {change.formError && <div className="form-error">{change.formError}</div>}
              <Input
                label="كلمة المرور الحالية"
                type="password"
                required
                autoComplete="current-password"
                error={change.fieldErrors.current_password}
                value={current}
                onChange={(event) => setCurrent(event.target.value)}
              />
              <Input
                label="كلمة المرور الجديدة"
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                hint="٨ أحرف على الأقل."
                error={change.fieldErrors.new_password}
                value={next}
                onChange={(event) => setNext(event.target.value)}
              />
              <Input
                label="تأكيد كلمة المرور"
                type="password"
                required
                autoComplete="new-password"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
              />
              <div>
                <Button type="submit" variant="primary" loading={change.submitting}>
                  تغيير كلمة المرور
                </Button>
              </div>
            </form>
          </CardBody>
        </Card>
      </div>
    </>
  )
}
