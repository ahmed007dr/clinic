import { useEffect, useState } from 'react'

import { api } from '@/api'
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Checkbox,
  ErrorState,
  Input,
  Loading,
  Textarea,
} from '@/components/ui'
import { RelationSelect } from '@/components/data/RelationSelect'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync, useMutation } from '@/hooks/useApi'

import { DoctorProfileRequests } from './DoctorProfileRequests'
import { LinkFields } from './LinkFields'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { serverUrl } from '@/lib/config'

const TEXT_FIELDS = [
  'print_header_title',
  'print_header_subtitle',
  'address',
  'phone',
  'email',
  'footer_text',
  'print_accent_color',
  'intake_form_title',
  'intake_form_intro',
  'intake_consent_text',
]

/**
 * How a clinic's paper looks — the letterhead on every printed sheet and
 * what the patient intake form asks for (branches/printing.py).
 *
 * The clinic's Admin designs their own clinic's; the Owner any clinic's
 * (api/views/print_settings.py enforces both). "Preview" opens the printed
 * intake form exactly as reception will print it.
 */
export function PrintSettingsPage() {
  const toast = useToast()
  const { user, permissions } = useAuth()
  const [branch, setBranch] = useState(user?.active_branch?.uuid ?? user?.branch?.uuid ?? '')
  const settings = useAsync(() => api.printSettings.get(branch), [branch], { skip: !branch })
  const [values, setValues] = useState(null)

  useEffect(() => {
    if (!settings.data) return
    const data = settings.data
    setValues({
      ...Object.fromEntries(TEXT_FIELDS.map((name) => [name, data[name] ?? ''])),
      print_logo_in_footer: Boolean(data.print_logo_in_footer),
      intake_sections: data.effective_sections ?? [],
      extra_lines: (data.intake_extra_fields ?? []).join('\n'),
      print_links: { ...(data.print_links ?? {}) },
    })
  }, [settings.data])

  const save = useMutation(() =>
    api.printSettings.update(branch, {
      ...Object.fromEntries(TEXT_FIELDS.map((name) => [name, values[name]])),
      print_logo_in_footer: values.print_logo_in_footer,
      intake_sections: values.intake_sections,
      intake_extra_fields: values.extra_lines.split('\n').map((line) => line.trim()).filter(Boolean),
      print_links: values.print_links,
    }),
  )
  const upload = useMutation((file) => api.printSettings.uploadLogo(branch, file))
  const removeLogo = useMutation(() => api.printSettings.update(branch, { remove_logo: true }))

  const set = (name) => (event) =>
    setValues((current) => ({ ...current, [name]: event.target.value }))

  const toggleSection = (key) =>
    setValues((current) => ({
      ...current,
      intake_sections: current.intake_sections.includes(key)
        ? current.intake_sections.filter((item) => item !== key)
        : [...current.intake_sections, key],
    }))

  const submit = async (event) => {
    event.preventDefault()
    try {
      await save.run()
      toast.success('تم حفظ تصميم المطبوعات')
      settings.reload()
    } catch {
      /* per field, below */
    }
  }

  const onLogo = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    try {
      await upload.run(file)
      toast.success('تم رفع الشعار')
      settings.reload()
    } catch (error) {
      toast.error(error.message)
    }
    event.target.value = ''
  }

  const preview = () =>
    window.open(serverUrl(`/patients/print/intake/?branch=${branch}`), '_blank', 'noopener')

  const errors = save.fieldErrors

  return (
    <>
      <PageHeader
        title="تصميم المطبوعات"
        subtitle="الشعار وبيانات العيادة في رأس وتذييل كل المطبوعات، ومحتوى استمارة تسجيل المريض"
        actions={
          branch && (
            <Button variant="ghost" onClick={preview}>
              معاينة الاستمارة
            </Button>
          )
        }
      />

      {permissions.is_owner && (
        <Card>
          <CardBody>
            <RelationSelect
              label="الفرع"
              resource={api.branches}
              value={branch}
              onChange={(value) => setBranch(value ?? '')}
            />
          </CardBody>
        </Card>
      )}

      {settings.loading && !values && <Loading />}
      {settings.error && <ErrorState error={settings.error} onRetry={settings.reload} />}

      <DoctorProfileRequests />

      {values && settings.data && (
        <form className="ui-stack" onSubmit={submit}>
          <Card>
            <CardHeader title="الشعار" subtitle="PNG أو JPG أو WEBP حتى ١ ميجابايت" />
            <CardBody>
              <div className="ui-row" style={{ alignItems: 'center', gap: 'var(--s4)' }}>
                {settings.data.logo_url ? (
                  <img
                    src={settings.data.logo_url}
                    alt="الشعار الحالي"
                    style={{ maxHeight: 72, maxWidth: 180, objectFit: 'contain' }}
                  />
                ) : (
                  <span className="ui-muted">لا يوجد شعار</span>
                )}
                <input type="file" accept="image/png,image/jpeg,image/webp" onChange={onLogo} />
                {settings.data.logo_url && (
                  <Button
                    size="sm"
                    variant="ghost"
                    loading={removeLogo.submitting}
                    onClick={async () => {
                      await removeLogo.run()
                      settings.reload()
                    }}
                  >
                    إزالة الشعار
                  </Button>
                )}
              </div>
              <Checkbox
                label="إظهار الشعار في التذييل أيضاً"
                checked={values.print_logo_in_footer}
                onChange={(event) =>
                  setValues((current) => ({ ...current, print_logo_in_footer: event.target.checked }))
                }
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="رأس الصفحة وتذييلها" />
            <CardBody>
              <div className="form-grid">
                <Input
                  label="الاسم في رأس الصفحة"
                  hint={`اتركه فارغاً لاستخدام اسم الفرع: ${settings.data.branch_name}`}
                  value={values.print_header_title}
                  onChange={set('print_header_title')}
                  error={errors.print_header_title}
                />
                <Input
                  label="سطر تحت الاسم"
                  hint="مثلاً التخصصات أو الشعار النصي"
                  value={values.print_header_subtitle}
                  onChange={set('print_header_subtitle')}
                  error={errors.print_header_subtitle}
                />
                <Input label="الهاتف" value={values.phone} onChange={set('phone')} dir="ltr" error={errors.phone} />
                <Input label="البريد" value={values.email} onChange={set('email')} dir="ltr" error={errors.email} />
                <Textarea label="العنوان" rows={2} value={values.address} onChange={set('address')} error={errors.address} />
                <Input
                  label="نص التذييل"
                  value={values.footer_text}
                  onChange={set('footer_text')}
                  error={errors.footer_text}
                />
                <Input
                  label="لون التصميم"
                  type="color"
                  value={values.print_accent_color || '#0e6e63'}
                  onChange={set('print_accent_color')}
                  error={errors.print_accent_color}
                />
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="روابط التواصل"
              subtitle="تظهر المملوءة فقط: في تذييل الروشتة والاستمارة، وفي بوابة المرضى"
            />
            <CardBody>
              <LinkFields
                kinds={settings.data.link_kinds}
                value={values.print_links}
                onChange={(print_links) => setValues((current) => ({ ...current, print_links }))}
              />
              {errors.print_links && <div className="form-error">{errors.print_links}</div>}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="استمارة تسجيل المريض" subtitle="يطبعها الاستقبال ليملأها المريض ويوقّع عليها" />
            <CardBody>
              <div className="form-grid">
                <Input
                  label="عنوان الاستمارة"
                  hint="الافتراضي: استمارة تسجيل مريض"
                  value={values.intake_form_title}
                  onChange={set('intake_form_title')}
                  error={errors.intake_form_title}
                />
                <Textarea
                  label="مقدمة تحت العنوان"
                  rows={2}
                  value={values.intake_form_intro}
                  onChange={set('intake_form_intro')}
                />
              </div>

              <h3 className="ui-card__title" style={{ marginTop: 'var(--s4)' }}>
                الأقسام
              </h3>
              <div className="ui-row" style={{ flexWrap: 'wrap', gap: 'var(--s3)' }}>
                {settings.data.available_sections.map((section) => (
                  <Checkbox
                    key={section.key}
                    label={section.label}
                    checked={values.intake_sections.includes(section.key)}
                    onChange={() => toggleSection(section.key)}
                  />
                ))}
              </div>
              {errors.intake_sections && <div className="form-error">{errors.intake_sections}</div>}

              <div className="form-grid" style={{ marginTop: 'var(--s4)' }}>
                <Textarea
                  label="أسطر إضافية تُملأ باليد"
                  hint="سطر لكل بند، مثل: جهة التحويل، رقم التأمين. حتى ٢٠ سطراً."
                  rows={4}
                  value={values.extra_lines}
                  onChange={set('extra_lines')}
                  error={errors.intake_extra_fields}
                />
                <Textarea
                  label="نص الإقرار فوق التوقيع"
                  hint="اتركه فارغاً لاستخدام النص الافتراضي."
                  rows={4}
                  value={values.intake_consent_text}
                  onChange={set('intake_consent_text')}
                />
              </div>
            </CardBody>
          </Card>

          {save.formError && <div className="form-error">{save.formError}</div>}
          <div className="form-actions">
            <Button type="submit" variant="primary" loading={save.submitting}>
              حفظ التصميم
            </Button>
          </div>
        </form>
      )}
    </>
  )
}
