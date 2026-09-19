import { api } from '@/api'
import { Button, Card, CardBody, CardHeader, Checkbox, ErrorState, Loading } from '@/components/ui'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { useT } from '@/i18n'

/** The clinic's patient-portal choices. Admin only (the API enforces it). */
export function PortalSettings() {
  const toast = useToast()
  const { t } = useT()
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

          <Checkbox
            label={t('portal_settings.self_registration')}
            checked={Boolean(data.portal_self_registration)}
            disabled={save.submitting}
            onChange={async (event) => {
              try {
                setData(await save.run({ portal_self_registration: event.target.checked }))
                toast.success(t('common.saved'))
              } catch (caught) {
                toast.error(caught.message)
              }
            }}
          />
          <p className="ui-muted" style={{ fontSize: 'var(--text-sm)', margin: 0 }}>
            {t('portal_settings.self_registration_hint')}
          </p>
          {data.portal_self_registration && data.registration_url && (
            <div>
              <div className="ui-field__label">{t('portal_settings.registration_url')}</div>
              <div className="ui-row">
                <input className="ui-input" dir="ltr" readOnly value={data.registration_url}
                  onFocus={(event) => event.target.select()} />
                <Button size="sm" onClick={() => navigator.clipboard?.writeText(data.registration_url)}>
                  {t('common.copy')}
                </Button>
              </div>
            </div>
          )}

          <Checkbox
            label="السماح للمريض بالحجز في عيادة غير عيادته"
            checked={Boolean(data.portal_allow_other_branches)}
            disabled={save.submitting}
            onChange={async (event) => {
              try {
                setData(await save.run({ portal_allow_other_branches: event.target.checked }))
                toast.success(t('common.saved'))
              } catch (caught) {
                toast.error(caught.message)
              }
            }}
          />
          <p className="ui-muted" style={{ fontSize: 'var(--text-sm)', margin: 0 }}>
            مغلق افتراضياً: يحجز المريض في عيادته فقط. عند فتحه يرى موظفو العيادة الأخرى بيانات المريض الأساسية
            (الاسم والهاتف) طوال حجزه المؤكّد لديهم، ولا يرون ملفه ولا سجله في عيادته الأصلية.
          </p>

          <Checkbox
            label="إظهار المجمع في دليل العيادات العام"
            checked={Boolean(data.listed_in_directory)}
            disabled={save.submitting}
            onChange={async (event) => {
              try {
                setData(await save.run({ listed_in_directory: event.target.checked }))
                toast.success(t('common.saved'))
              } catch (caught) {
                toast.error(caught.message)
              }
            }}
          />
          <p className="ui-muted" style={{ fontSize: 'var(--text-sm)', margin: 0 }}>
            مغلق افتراضياً: صفحتك العامة تُفتح برابطها فقط. عند تفعيله يجدك الزوار في دليل العيادات بالاسم والعنوان
            والتخصص والخدمة، بما تنشره في صفحتك العامة فقط (الشعار والغلاف المعتمدان، أسماء العيادات وعناوينها،
            التخصصات، والخدمات المتاحة للحجز مع أقل سعر). لا يظهر أي رقم هاتف أو بيان عن الأطباء أو المرضى.
          </p>
          {data.listed_in_directory && data.directory_url && (
            <div>
              <div className="ui-field__label">رابط دليل العيادات</div>
              <div className="ui-row">
                <input className="ui-input" dir="ltr" readOnly value={data.directory_url}
                  onFocus={(event) => event.target.select()} />
                <Button size="sm" onClick={() => navigator.clipboard?.writeText(data.directory_url)}>
                  {t('common.copy')}
                </Button>
              </div>
            </div>
          )}

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
