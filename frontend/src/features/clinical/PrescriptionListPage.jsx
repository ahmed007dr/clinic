import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { Button, Input, Modal } from '@/components/ui'
import { ResourceTable } from '@/components/data/ResourceTable'
import { RelationSelect } from '@/components/data/RelationSelect'
import { useForm } from '@/components/form/useForm'
import { PageHeader } from '@/components/layout/PageHeader'
import { useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { formatDateTime, toDateTimeInput } from '@/lib/format'

import { AllergyBanner } from './AllergyPanel'
import './prescription.css'

const BLANK_ITEM = {
  medication: '',
  dosage: '',
  frequency: '',
  duration: '',
  instructions: '',
}

/**
 * Prescriptions, written with their medicines in one go.
 *
 * The API takes the lines nested inside the prescription and writes them in
 * one transaction, so a saved prescription always has its medicines. Two
 * requests would allow the second to fail and leave a prescription that says
 * nothing — which is not a partial record but a clinical mistake.
 */
export function PrescriptionListPage() {
  const toast = useToast()
  const [search] = useSearchParams()
  const [editing, setEditing] = useState(null)
  const [items, setItems] = useState([{ ...BLANK_ITEM }])
  const [refreshKey, setRefreshKey] = useState(0)

  const save = useMutation((body) =>
    editing === 'new'
      ? api.prescriptions.create(body)
      : api.prescriptions.update(editing.uuid, body),
  )

  const open = (row) => {
    setEditing(row)
    setItems(
      row === 'new'
        ? [{ ...BLANK_ITEM }]
        : row.items?.length
          ? row.items.map((item) => ({ ...item }))
          : [{ ...BLANK_ITEM }],
    )
  }

  const initial =
    editing && editing !== 'new'
      ? {
          patient: editing.patient ?? '',
          visit: editing.visit ?? '',
          doctor: editing.doctor ?? '',
          issued_at: toDateTimeInput(editing.issued_at),
          notes: editing.notes ?? '',
        }
      : {
          patient: search.get('patient') ?? '',
          visit: '',
          doctor: '',
          issued_at: toDateTimeInput(new Date()),
          notes: '',
        }

  const form = useForm(initial, { serverErrors: save.fieldErrors })

  const setItem = (index, key, value) => {
    setItems((current) =>
      current.map((item, position) =>
        position === index ? { ...item, [key]: value } : item,
      ),
    )
  }

  const submit = async (event) => {
    event.preventDefault()
    // Blank rows are how the form offers a next line; they are not medicines.
    const filled = items.filter((item) => item.medication.trim())
    if (filled.length === 0) {
      toast.error('أضف دواءً واحداً على الأقل.')
      return
    }
    try {
      const saved = await save.run({
        ...form.values,
        doctor: form.values.doctor || null,
        items: filled,
      })
      toast.success('تم حفظ الروشتة')
      // The server's own check, the same one the printed prescription uses.
      // A warning, never a block — the doctor decides (§26).
      ;(saved?.allergy_warnings ?? []).forEach((warning) =>
        toast.error(`تنبيه حساسية: «${warning.medication}» يطابق حساسية مسجلة من «${warning.allergen}».`),
      )
      setEditing(null)
      setRefreshKey((value) => value + 1)
    } catch {
      /* per field */
    }
  }

  const columns = [
    { key: 'serial_number', header: 'الرقم', numeric: true },
    { key: 'patient_name', header: 'المريض' },
    { key: 'doctor_name', header: 'الطبيب', render: (row) => row.doctor_name || '—' },
    {
      key: 'items',
      header: 'الأدوية',
      render: (row) => (
        <span title={row.items?.map((item) => item.medication).join('، ')}>
          {row.items?.length
            ? `${row.items.length} — ${row.items[0].medication}${
                row.items.length > 1 ? ' …' : ''
              }`
            : '—'}
        </span>
      ),
    },
    {
      key: 'issued_at',
      header: 'التاريخ',
      render: (row) => formatDateTime(row.issued_at),
    },
    {
      key: '__actions',
      actions: true,
      render: (row) => (
        <div className="ui-row">
          {/* The server-rendered print page: the browser shapes Arabic and
              lays out RTL correctly, which a generated PDF does not. */}
          <a
            className="ui-btn ui-btn--ghost ui-btn--sm"
            href={`/medical/prescription/${row.uuid}/print/`}
            target="_blank"
            rel="noopener"
          >
            طباعة
          </a>
          <Button size="sm" variant="ghost" onClick={() => open(row)}>
            تعديل
          </Button>
        </div>
      ),
    },
  ]

  return (
    <>
      <PageHeader
        title="الروشتات"
        actions={
          <Button variant="primary" onClick={() => open('new')}>
            روشتة جديدة
          </Button>
        }
      />

      <ResourceTable
        resource={api.prescriptions}
        columns={columns}
        refreshKey={refreshKey}
        params={{ patient: search.get('patient') || undefined }}
        searchPlaceholder="ابحث بالمريض أو الدواء…"
        empty={{
          title: 'لا توجد روشتات',
          message: 'ستظهر هنا الروشتات بعد كتابتها.',
        }}
      />

      <Modal
        open={Boolean(editing)}
        onClose={() => {
          setEditing(null)
          save.reset()
        }}
        title={editing === 'new' ? 'روشتة جديدة' : 'تعديل الروشتة'}
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
          <AllergyBanner patientUuid={form.values.patient} />

          <div className="form-grid">
            <div className="form-grid__cell">
              <RelationSelect
                label="المريض"
                required
                resource={api.patients}
                searchable
                value={form.values.patient}
                error={save.fieldErrors.patient}
                onChange={(value) => form.setValue('patient', value)}
              />
            </div>
            <div className="form-grid__cell">
              <RelationSelect
                label="الطبيب"
                resource={api.doctors}
                value={form.values.doctor}
                error={save.fieldErrors.doctor}
                onChange={(value) => form.setValue('doctor', value)}
              />
            </div>
            <div className="form-grid__cell">
              <RelationSelect
                label="الزيارة"
                required
                resource={api.visits}
                searchable
                labelKey="serial_number"
                params={{ patient: form.values.patient || undefined }}
                hint="زيارات المريض المختار فقط"
                value={form.values.visit}
                error={save.fieldErrors.visit}
                onChange={(value) => form.setValue('visit', value)}
              />
            </div>
            <div className="form-grid__cell">
              <Input
                label="التاريخ"
                type="datetime-local"
                error={save.fieldErrors.issued_at}
                {...form.field('issued_at')}
              />
            </div>
          </div>

          <div className="rx">
            <div className="rx__head">
              <h3 className="ui-card__title">الأدوية</h3>
              <Button
                size="sm"
                onClick={() => setItems((current) => [...current, { ...BLANK_ITEM }])}
              >
                إضافة دواء
              </Button>
            </div>

            {save.fieldErrors.items && (
              <div className="form-error">{save.fieldErrors.items}</div>
            )}

            {items.map((item, index) => (
              <div className="rx__item" key={index}>
                <div className="rx__number" aria-hidden="true">
                  {index + 1}
                </div>
                <div className="rx__fields">
                  <Input
                    placeholder="الدواء"
                    aria-label={`الدواء ${index + 1}`}
                    value={item.medication}
                    onChange={(event) =>
                      setItem(index, 'medication', event.target.value)
                    }
                  />
                  <Input
                    placeholder="الجرعة"
                    aria-label={`الجرعة ${index + 1}`}
                    value={item.dosage}
                    onChange={(event) => setItem(index, 'dosage', event.target.value)}
                  />
                  <Input
                    placeholder="التكرار"
                    aria-label={`التكرار ${index + 1}`}
                    value={item.frequency}
                    onChange={(event) =>
                      setItem(index, 'frequency', event.target.value)
                    }
                  />
                  <Input
                    placeholder="المدة"
                    aria-label={`المدة ${index + 1}`}
                    value={item.duration}
                    onChange={(event) => setItem(index, 'duration', event.target.value)}
                  />
                  <Input
                    placeholder="تعليمات"
                    aria-label={`تعليمات ${index + 1}`}
                    value={item.instructions}
                    onChange={(event) =>
                      setItem(index, 'instructions', event.target.value)
                    }
                  />
                </div>
                <Button
                  variant="ghost"
                  icon
                  aria-label={`حذف الدواء ${index + 1}`}
                  // The last row is never removable: an empty list has no way
                  // back to a usable form.
                  disabled={items.length === 1}
                  onClick={() =>
                    setItems((current) =>
                      current.filter((_, position) => position !== index),
                    )
                  }
                >
                  ✕
                </Button>
              </div>
            ))}
          </div>

          <div style={{ marginTop: 'var(--s4)' }}>
            <Input
              label="ملاحظات"
              error={save.fieldErrors.notes}
              {...form.field('notes')}
            />
          </div>

          <button type="submit" className="u-visually-hidden" tabIndex={-1}>
            حفظ
          </button>
        </form>
      </Modal>
    </>
  )
}
