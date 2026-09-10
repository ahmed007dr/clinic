import { useNavigate, useParams } from 'react-router-dom'

import { api } from '@/api'
import { Button, Card, CardBody, ErrorState, Loading } from '@/components/ui'
import { FormFields, nullableNames } from '@/components/form/FormFields'
import { useForm, useUnsavedWarning } from '@/components/form/useForm'
import { PageHeader } from '@/components/layout/PageHeader'
import { useMutation, useRecord } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'

const FIELDS = [
  { name: 'name', label: 'الاسم', required: true, span: 2 },
  { name: 'phone1', label: 'الهاتف', type: 'tel' },
  { name: 'phone2', label: 'هاتف آخر', type: 'tel' },
  {
    name: 'gender',
    label: 'النوع',
    type: 'select',
    required: true,
    default: 'female',
    placeholder: undefined,
    options: [
      { value: 'female', label: 'أنثى' },
      { value: 'male', label: 'ذكر' },
    ],
  },
  {
    name: 'marital_status',
    label: 'الحالة الاجتماعية',
    type: 'select',
    default: 'single',
    placeholder: undefined,
    options: [
      { value: 'single', label: 'أعزب' },
      { value: 'married', label: 'متزوج' },
    ],
  },
  { name: 'birth_date', label: 'تاريخ الميلاد', type: 'date' },
  { name: 'national_id', label: 'الرقم القومي' },
  { name: 'email', label: 'البريد الإلكتروني', type: 'email' },
  {
    name: 'branch',
    label: 'الفرع',
    type: 'relation',
    resource: api.branches,
  },
  { name: 'address', label: 'العنوان', type: 'textarea', rows: 2, span: 2 },
  { name: 'notes', label: 'ملاحظات', type: 'textarea', span: 2 },
]

export function PatientFormPage() {
  const { uuid } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { branch } = useAuth()
  const editing = Boolean(uuid)

  const { record, loading, error, reload } = useRecord(api.patients, uuid)

  const save = useMutation((values) =>
    editing ? api.patients.update(uuid, values) : api.patients.create(values),
  )

  const initial = editing
    ? {
        ...Object.fromEntries(
          FIELDS.map((field) => [field.name, record?.[field.name] ?? '']),
        ),
        birth_date: record?.birth_date ?? '',
      }
    : {
        ...Object.fromEntries(
          FIELDS.map((field) => [field.name, field.default ?? '']),
        ),
        // Default to the user's own branch: for a receptionist it is the only
        // one they can pick anyway, and making them pick it every time is a
        // step that exists only because the form did not know.
        branch: branch?.uuid ?? '',
      }

  const form = useForm(initial, { serverErrors: save.fieldErrors })
  useUnsavedWarning(form.dirty && !save.submitting)

  if (editing && loading) return <Loading />
  if (editing && error) return <ErrorState error={error} onRetry={reload} />

  const submit = async (event) => {
    event.preventDefault()
    try {
      const saved = await save.run(form.payload(nullableNames(FIELDS)))
      toast.success(editing ? 'تم حفظ بيانات المريض' : 'تم تسجيل المريض')
      navigate(`/patients/${saved.uuid}`, { replace: true })
    } catch {
      /* Errors are rendered against their fields. */
    }
  }

  return (
    <>
      <PageHeader
        title={editing ? `تعديل: ${record?.name ?? ''}` : 'تسجيل مريض'}
        back={
          editing
            ? { to: `/patients/${uuid}`, label: 'رجوع للملف' }
            : { to: '/patients', label: 'رجوع للقائمة' }
        }
      />

      <Card>
        <CardBody>
          <form onSubmit={submit}>
            {save.formError && <div className="form-error">{save.formError}</div>}
            <FormFields
              fields={FIELDS}
              form={form}
              errors={save.fieldErrors}
              disabled={save.submitting}
            />
            <div className="form-actions">
              <Button type="submit" variant="primary" loading={save.submitting}>
                {editing ? 'حفظ التعديلات' : 'تسجيل'}
              </Button>
              <Button variant="ghost" onClick={() => navigate(-1)}>
                إلغاء
              </Button>
            </div>
          </form>
        </CardBody>
      </Card>
    </>
  )
}
