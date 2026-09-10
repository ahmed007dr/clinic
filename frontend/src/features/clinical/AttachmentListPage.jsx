import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { Badge, Button, Input, Modal, Select, Textarea } from '@/components/ui'
import { ResourceTable } from '@/components/data/ResourceTable'
import { RelationSelect } from '@/components/data/RelationSelect'
import { PageHeader } from '@/components/layout/PageHeader'
import { useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { fileSize, formatDateTime } from '@/lib/format'

const CATEGORIES = [
  { value: 'lab_report', label: 'تقرير تحاليل' },
  { value: 'imaging', label: 'أشعة' },
  { value: 'consent', label: 'إقرار موافقة' },
  { value: 'referral', label: 'إحالة' },
  { value: 'clinical_photo', label: 'صورة إكلينيكية' },
  { value: 'other', label: 'أخرى' },
]

/**
 * Patient documents.
 *
 * Two things make this different from every other list. Uploads go as
 * multipart, because there is a file. And **downloads go through the API**,
 * not through a link — the files are stored outside the web root and the
 * storage class raises if anything asks it for a URL, so the only way to read
 * one is an authenticated request that the server checks. A direct link would
 * bypass every permission this application has.
 */
export function AttachmentListPage() {
  const toast = useToast()
  const [search] = useSearchParams()
  const [uploading, setUploading] = useState(false)
  const [category, setCategory] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  const [values, setValues] = useState({
    title: '',
    patient: search.get('patient') ?? '',
    visit: '',
    category: 'other',
    notes: '',
    file: null,
  })

  const upload = useMutation((body) => api.attachments.create(body))
  const download = useMutation((uuid, name) => api.attachments.download(uuid, name))
  const release = useMutation((uuid, released) => api.attachments.release(uuid, released))

  const set = (key, value) => setValues((current) => ({ ...current, [key]: value }))

  const submit = async (event) => {
    event.preventDefault()
    if (!values.file) {
      toast.error('اختر ملفاً أولاً.')
      return
    }
    const body = new FormData()
    Object.entries(values).forEach(([key, value]) => {
      if (value === null || value === '') return
      body.append(key, value)
    })
    try {
      await upload.run(body)
      toast.success('تم رفع المستند')
      setUploading(false)
      setValues({
        title: '',
        patient: search.get('patient') ?? '',
        visit: '',
        category: 'other',
        notes: '',
        file: null,
      })
      setRefreshKey((value) => value + 1)
    } catch {
      /* per field */
    }
  }

  const columns = [
    { key: 'serial_number', header: 'الرقم', numeric: true },
    { key: 'title', header: 'المستند' },
    { key: 'patient_name', header: 'المريض' },
    {
      key: 'category',
      header: 'النوع',
      render: (row) => <Badge tone="neutral">{row.category_label}</Badge>,
    },
    {
      key: 'size_bytes',
      header: 'الحجم',
      numeric: true,
      render: (row) => fileSize(row.size_bytes),
    },
    {
      key: 'created_at',
      header: 'الرفع',
      render: (row) => formatDateTime(row.created_at),
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
              setRefreshKey((value) => value + 1)
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
        <Button
          size="sm"
          variant="ghost"
          disabled={download.submitting}
          onClick={async () => {
            try {
              await download.run(row.uuid, row.original_filename || row.title)
            } catch (error) {
              toast.error(error.message)
            }
          }}
        >
          تنزيل
        </Button>
      ),
    },
  ]

  return (
    <>
      <PageHeader
        title="المستندات"
        subtitle="تُحفظ خارج مجلد الويب وتُنزَّل عبر طلب مُصرَّح به فقط"
        actions={
          <Button variant="primary" onClick={() => setUploading(true)}>
            رفع مستند
          </Button>
        }
      />

      <ResourceTable
        resource={api.attachments}
        columns={columns}
        refreshKey={refreshKey}
        params={{
          patient: search.get('patient') || undefined,
          category: category || undefined,
        }}
        searchPlaceholder="ابحث بالعنوان أو المريض أو اسم الملف…"
        filters={
          <Select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            placeholder="كل الأنواع"
            options={CATEGORIES}
            aria-label="تصفية بالنوع"
          />
        }
        empty={{
          title: 'لا توجد مستندات',
          message: 'ارفع تقارير التحاليل والأشعة والإقرارات هنا.',
        }}
      />

      <Modal
        open={uploading}
        onClose={() => {
          setUploading(false)
          upload.reset()
        }}
        title="رفع مستند"
        footer={
          <>
            <Button variant="primary" onClick={submit} loading={upload.submitting}>
              رفع
            </Button>
            <Button variant="ghost" onClick={() => setUploading(false)}>
              إلغاء
            </Button>
          </>
        }
      >
        <form onSubmit={submit}>
          {upload.formError && <div className="form-error">{upload.formError}</div>}

          <div className="form-grid">
            <div className="form-grid__cell" style={{ gridColumn: 'span 2' }}>
              <Input
                label="عنوان المستند"
                required
                error={upload.fieldErrors.title}
                value={values.title}
                onChange={(event) => set('title', event.target.value)}
              />
            </div>

            <div className="form-grid__cell">
              <RelationSelect
                label="المريض"
                required
                resource={api.patients}
                searchable
                value={values.patient}
                error={upload.fieldErrors.patient}
                onChange={(value) => set('patient', value)}
              />
            </div>

            <div className="form-grid__cell">
              <Select
                label="النوع"
                options={CATEGORIES}
                value={values.category}
                error={upload.fieldErrors.category}
                onChange={(event) => set('category', event.target.value)}
              />
            </div>

            <div className="form-grid__cell" style={{ gridColumn: 'span 2' }}>
              <Input
                label="الملف"
                type="file"
                required
                accept=".pdf,.jpg,.jpeg,.png,.webp"
                error={upload.fieldErrors.file}
                hint="PDF أو صورة، بحد أقصى ١٠ ميجابايت. يُفحص محتوى الملف وليس امتداده فقط."
                onChange={(event) => set('file', event.target.files?.[0] ?? null)}
              />
            </div>

            <div className="form-grid__cell" style={{ gridColumn: 'span 2' }}>
              <Textarea
                label="ملاحظات"
                value={values.notes}
                error={upload.fieldErrors.notes}
                onChange={(event) => set('notes', event.target.value)}
              />
            </div>
          </div>

          <button type="submit" className="u-visually-hidden" tabIndex={-1}>
            رفع
          </button>
        </form>
      </Modal>
    </>
  )
}
