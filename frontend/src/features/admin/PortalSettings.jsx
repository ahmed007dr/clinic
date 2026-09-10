import { api } from '@/api'
import { Button, Card, CardBody, CardHeader, Checkbox, ErrorState, Loading } from '@/components/ui'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'

/** The clinic's patient-portal choices. Admin only (the API enforces it). */
export function PortalSettings() {
  const toast = useToast()
  const { data, loading, error, reload, setData } = useAsync(() => api.clinicSettings.get(), [])
  const save = useMutation((body) => api.clinicSettings.update(body))

  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />

  return (
    <Card>
      <CardHeader title="بوابة المرضى" subtitle="ما يراه المريض عند دخوله البوابة" />
      <CardBody>
        <div className="ui-stack">
          <div>
            <div className="ui-field__label">رابط البوابة لمرضاك</div>
            <div className="ui-row">
              <input className="ui-input" dir="ltr" readOnly value={data.portal_url}
                onFocus={(event) => event.target.select()} />
              <Button size="sm" onClick={() => navigator.clipboard?.writeText(data.portal_url)}>نسخ</Button>
            </div>
          </div>

          <Checkbox
            label="إظهار نص التشخيص للمريض"
            checked={data.portal_show_diagnosis}
            disabled={save.submitting}
            onChange={async (event) => {
              try {
                setData(await save.run({ portal_show_diagnosis: event.target.checked }))
                toast.success('تم الحفظ')
              } catch (caught) {
                toast.error(caught.message)
              }
            }}
          />

          <ul className="ui-muted" style={{ fontSize: 'var(--text-sm)', margin: 0, paddingInlineStart: 'var(--s5)' }}>
            <li>يرى المريض دائماً: مواعيده، روشتاته، مدفوعاته، تقدّم خطة علاجه، وحساسيته المسجلة.</li>
            <li>التحاليل والمستندات تظهر فقط بعد أن يضغط الطبيب «إصدار للمريض».</li>
            <li>ملاحظات الفحص لا تظهر للمريض أبداً.</li>
            <li>طلبات المواعيد من البوابة تصل للاستقبال بحالة «طلب من المريض» لتأكيدها.</li>
          </ul>
        </div>
      </CardBody>
    </Card>
  )
}
