import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import {
  Badge,
  Button,
  Checkbox,
  Modal,
  Select,
  LAB_STATUS_TONES,
  LAB_TONES,
} from '@/components/ui'
import { ResourceTable } from '@/components/data/ResourceTable'
import { FormFields, nullableNames } from '@/components/form/FormFields'
import { useForm } from '@/components/form/useForm'
import { PageHeader } from '@/components/layout/PageHeader'
import { useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { formatDateTime, toDateTimeInput } from '@/lib/format'

const FLAGS = [
  { value: 'normal', label: 'طبيعي' },
  { value: 'abnormal', label: 'غير طبيعي' },
  { value: 'critical', label: 'حرج' },
]

const STATUSES = [
  { value: 'ordered', label: 'مطلوب' },
  { value: 'resulted', label: 'صدرت النتيجة' },
  { value: 'cancelled', label: 'ملغي' },
]

const FIELDS = [
  { name: 'test_name', label: 'التحليل', required: true, span: 2 },
  {
    name: 'patient',
    label: 'المريض',
    type: 'relation',
    resource: api.patients,
    searchable: true,
    required: true,
  },
  {
    name: 'visit',
    label: 'الزيارة',
    type: 'relation',
    resource: api.visits,
    searchable: true,
    labelKey: 'serial_number',
  },
  { name: 'ordered_by', label: 'طلبها', type: 'relation', resource: api.doctors },
  { name: 'branch', label: 'الفرع', type: 'relation', resource: api.branches },
  { name: 'specimen', label: 'العينة' },
  { name: 'lab_name', label: 'المعمل' },
  { name: 'value', label: 'النتيجة' },
  { name: 'unit', label: 'الوحدة' },
  { name: 'reference_range', label: 'المعدل المرجعي' },
  {
    name: 'flag',
    label: 'التقييم',
    type: 'select',
    default: 'normal',
    placeholder: undefined,
    options: FLAGS,
  },
  {
    name: 'status',
    label: 'الحالة',
    type: 'select',
    default: 'ordered',
    placeholder: undefined,
    options: STATUSES,
  },
  { name: 'ordered_at', label: 'تاريخ الطلب', type: 'datetime' },
  { name: 'resulted_at', label: 'تاريخ النتيجة', type: 'datetime' },
  { name: 'notes', label: 'ملاحظات', type: 'textarea', span: 2 },
]

/**
 * Lab results, with acknowledgement.
 *
 * Not built on `CrudPage` because of the one thing that matters here: an
 * abnormal result that nobody has confirmed reading. That is a named act with
 * an actor and a timestamp, not a field on a form, so it gets its own button
 * and its own endpoint — and the list can be filtered down to exactly those.
 */
export function LabResultListPage() {
  const toast = useToast()
  const [search] = useSearchParams()
  const [editing, setEditing] = useState(null)
  const [flag, setFlag] = useState('')
  const [unacknowledged, setUnacknowledged] = useState(
    search.get('unacknowledged') === '1',
  )
  const [refreshKey, setRefreshKey] = useState(0)
  const refresh = () => setRefreshKey((value) => value + 1)

  const save = useMutation((values) =>
    editing === 'new'
      ? api.labResults.create(values)
      : api.labResults.update(editing.uuid, values),
  )
  const acknowledge = useMutation((uuid) => api.labResults.acknowledge(uuid))
  const release = useMutation((uuid, released) => api.labResults.release(uuid, released))

  const initial =
    editing && editing !== 'new'
      ? {
          ...Object.fromEntries(
            FIELDS.map((f) => [f.name, editing[f.name] ?? '']),
          ),
          ordered_at: toDateTimeInput(editing.ordered_at),
          resulted_at: toDateTimeInput(editing.resulted_at),
        }
      : {
          ...Object.fromEntries(FIELDS.map((f) => [f.name, f.default ?? ''])),
          patient: search.get('patient') ?? '',
          ordered_at: toDateTimeInput(new Date()),
        }

  const form = useForm(initial, { serverErrors: save.fieldErrors })

  const submit = async (event) => {
    event.preventDefault()
    try {
      await save.run(form.payload(nullableNames(FIELDS)))
      toast.success('تم الحفظ')
      setEditing(null)
      refresh()
    } catch {
      /* per field */
    }
  }

  const confirmRead = async (row) => {
    try {
      await acknowledge.run(row.uuid)
      toast.success('تم تسجيل الاطلاع')
      refresh()
    } catch (error) {
      toast.error(error.message)
    }
  }

  const columns = [
    { key: 'serial_number', header: 'الرقم', numeric: true },
    { key: 'test_name', header: 'التحليل' },
    { key: 'patient_name', header: 'المريض' },
    {
      key: 'value',
      header: 'النتيجة',
      numeric: true,
      render: (row) =>
        row.value ? (
          <span>
            <strong>{row.value}</strong> {row.unit}
            {row.reference_range && (
              <span className="ui-muted"> ({row.reference_range})</span>
            )}
          </span>
        ) : (
          '—'
        ),
    },
    {
      key: 'flag',
      header: 'التقييم',
      render: (row) => (
        <Badge tone={LAB_TONES[row.flag] ?? 'neutral'}>{row.flag_label}</Badge>
      ),
    },
    {
      key: 'status',
      header: 'الحالة',
      render: (row) => (
        <Badge tone={LAB_STATUS_TONES[row.status] ?? 'neutral'}>
          {row.status_label}
        </Badge>
      ),
    },
    {
      key: 'acknowledged',
      header: 'الاطلاع',
      render: (row) =>
        row.acknowledged_at ? (
          <span className="ui-muted" title={formatDateTime(row.acknowledged_at)}>
            {row.acknowledged_by_name || 'تم'}
          </span>
        ) : (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => confirmRead(row)}
            disabled={acknowledge.submitting}
          >
            تسجيل الاطلاع
          </Button>
        ),
    },
    {
      key: 'released',
      header: 'للمريض',
      render: (row) => (
        <Button
          size="sm"
          variant={row.released_to_patient ? 'ghost' : 'secondary'}
          disabled={release.submitting}
          onClick={async () => {
            try {
              await release.run(row.uuid, !row.released_to_patient)
              toast.success(row.released_to_patient ? 'أُخفيت عن المريض' : 'أصبحت متاحة للمريض في البوابة')
              refresh()
            } catch (error) {
              toast.error(error.message)
            }
          }}
        >
          {row.released_to_patient ? '✓ متاحة — إخفاء' : 'إصدار للمريض'}
        </Button>
      ),
    },
    {
      key: '__actions',
      actions: true,
      render: (row) => (
        <Button size="sm" variant="ghost" onClick={() => setEditing(row)}>
          تعديل
        </Button>
      ),
    },
  ]

  return (
    <>
      <PageHeader
        title="التحاليل"
        subtitle={unacknowledged ? 'نتائج غير طبيعية لم يُسجَّل الاطلاع عليها' : undefined}
        actions={
          <Button variant="primary" onClick={() => setEditing('new')}>
            تسجيل تحليل
          </Button>
        }
      />

      <ResourceTable
        resource={api.labResults}
        columns={columns}
        refreshKey={refreshKey}
        params={{
          patient: search.get('patient') || undefined,
          flag: flag || undefined,
          unacknowledged: unacknowledged ? '1' : undefined,
        }}
        searchPlaceholder="ابحث بالتحليل أو المريض أو المعمل…"
        filters={
          <>
            <Select
              value={flag}
              onChange={(event) => setFlag(event.target.value)}
              placeholder="كل التقييمات"
              options={FLAGS}
              aria-label="تصفية بالتقييم"
            />
            <Checkbox
              label="غير الطبيعية بانتظار الاطلاع"
              checked={unacknowledged}
              onChange={(event) => setUnacknowledged(event.target.checked)}
            />
          </>
        }
        empty={{
          title: 'لا توجد تحاليل',
          message: 'ستظهر هنا التحاليل بعد تسجيلها.',
        }}
      />

      <Modal
        open={Boolean(editing)}
        onClose={() => {
          setEditing(null)
          save.reset()
        }}
        title={editing === 'new' ? 'تسجيل تحليل' : 'تعديل التحليل'}
        size="wide"
        footer={
          <>
            <Button variant="primary" onClick={submit} loading={save.submitting}>
              حفظ
            </Button>
            <Button variant="ghost" onClick={() => setEditing(null)}>
              إلغاء
            </Button>
          </>
        }
      >
        <form onSubmit={submit}>
          {save.formError && <div className="form-error">{save.formError}</div>}
          <FormFields
            fields={FIELDS}
            form={form}
            errors={save.fieldErrors}
            disabled={save.submitting}
          />
          <button type="submit" className="u-visually-hidden" tabIndex={-1}>
            حفظ
          </button>
        </form>
      </Modal>
    </>
  )
}
