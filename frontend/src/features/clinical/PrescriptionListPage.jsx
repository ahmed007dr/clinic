import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { api } from '@/api'
import { Button, Input, Modal } from '@/components/ui'
import { ResourceTable } from '@/components/data/ResourceTable'
import { RelationSelect } from '@/components/data/RelationSelect'
import { useForm } from '@/components/form/useForm'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useToast } from '@/hooks/useToast'
import { serverUrl } from '@/lib/config'
import { formatDateTime } from '@/lib/format'

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
  const { user, permissions } = useAuth()
  const [search] = useSearchParams()
  const [editing, setEditing] = useState(null)
  const [items, setItems] = useState([{ ...BLANK_ITEM }])
  const [refreshKey, setRefreshKey] = useState(0)
  // Who the prescription is for: a visit and its patient. Chosen from the
  // patients in the doctor's room; fixed once the prescription exists.
  const [target, setTarget] = useState(null)

  // The doctor's room right now (medical/checkin.py). Management has no room
  // and picks a visit instead.
  const room = useAsync(() => api.visits.inRoom(), [refreshKey], { skip: !permissions.is_doctor })
  const inRoom = room.data ?? []

  const save = useMutation((body) =>
    editing === 'new'
      ? api.prescriptions.create(body)
      : api.prescriptions.update(editing.uuid, body),
  )
  const copy = useMutation((uuid, visit) => api.prescriptions.copy(uuid, visit))

  const fromRoom = (row) => ({ visit: row.visit, patient: row.patient, patient_name: row.patient_name })

  const open = (row) => {
    setEditing(row)
    setTarget(
      row === 'new'
        ? inRoom.length
          ? fromRoom(inRoom[0])
          : null
        : { visit: row.visit, patient: row.patient, patient_name: row.patient_name },
    )
    setItems(
      row === 'new'
        ? [{ ...BLANK_ITEM }]
        : row.items?.length
          ? row.items.map((item) => ({ ...item }))
          : [{ ...BLANK_ITEM }],
    )
  }

  /** Copy an old prescription onto the patient in the room, then open it to adjust. */
  const copyToRoom = async (row) => {
    if (inRoom.length === 0) {
      toast.error('لا يوجد مريض في غرفتك الآن لنسخ الروشتة له.')
      return
    }
    // With several patients sent in, the copy goes to the one who came in
    // first; the doctor sees the name on the opened copy before saving.
    try {
      const copied = await copy.run(row.uuid, inRoom[0].visit)
      toast.success(`نُسخت الروشتة للمريض ${copied.patient_name} — راجعها وعدّلها`)
      setRefreshKey((value) => value + 1)
      open(copied)
    } catch (error) {
      toast.error(error.message)
    }
  }

  const chooseVisit = async (uuid) => {
    if (!uuid) {
      setTarget(null)
      return
    }
    const visit = await api.visits.get(uuid)
    setTarget({ visit: visit.uuid, patient: visit.patient, patient_name: visit.patient_name })
  }

  const initial = { notes: editing && editing !== 'new' ? editing.notes ?? '' : '' }

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
    if (editing === 'new' && !target) {
      toast.error('اختر المريض أولاً.')
      return
    }
    try {
      // Doctor and date are the server's (the signed-in doctor, now); the
      // visit — and with it the patient — only on a new prescription.
      const saved = await save.run({
        notes: form.values.notes,
        items: filled,
        ...(editing === 'new' ? { visit: target.visit } : {}),
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
            href={serverUrl(`/medical/prescription/${row.uuid}/print/`)}
            target="_blank"
            rel="noopener"
          >
            طباعة
          </a>
          <Button size="sm" variant="ghost" onClick={() => open(row)}>
            تعديل
          </Button>
          {permissions.is_doctor && (
            <Button size="sm" variant="ghost" onClick={() => copyToRoom(row)} loading={copy.submitting}>
              نسخ للمريض الحالي
            </Button>
          )}
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
          <AllergyBanner patientUuid={target?.patient} />

          {editing === 'new' && permissions.is_doctor && (
            <div className="rx__room">
              {inRoom.length === 0 ? (
                <div className="form-error">
                  لا يوجد مريض في غرفتك الآن. يظهر المريض هنا عندما يسجّل الاستقبال دخوله إليك.
                </div>
              ) : (
                <div className="ui-row" role="radiogroup" aria-label="المريض في الغرفة">
                  {inRoom.map((row) => (
                    <Button
                      key={row.visit}
                      size="sm"
                      variant={target?.visit === row.visit ? 'primary' : 'secondary'}
                      onClick={() => setTarget(fromRoom(row))}
                    >
                      {row.patient_name}
                    </Button>
                  ))}
                </div>
              )}
            </div>
          )}

          {editing === 'new' && !permissions.is_doctor && (
            <RelationSelect
              label="الزيارة"
              required
              resource={api.visits}
              searchable
              labelKey="patient_name"
              params={{ patient: search.get('patient') || undefined }}
              value={target?.visit ?? ''}
              error={save.fieldErrors.visit}
              onChange={chooseVisit}
            />
          )}

          {/* Who, by whom and when are fixed: the patient from the visit, the
              doctor from the signed-in account, the date from the moment it
              is saved. Shown, never edited. */}
          <dl className="rx__facts">
            <div>
              <dt>المريض</dt>
              <dd>{target?.patient_name ?? '—'}</dd>
            </div>
            <div>
              <dt>الطبيب</dt>
              <dd>
                {editing && editing !== 'new'
                  ? editing.doctor_name ?? '—'
                  : user?.doctor?.name ?? '—'}
              </dd>
            </div>
            <div>
              <dt>التاريخ</dt>
              <dd>
                {editing && editing !== 'new' ? formatDateTime(editing.issued_at) : 'الآن (تلقائي)'}
              </dd>
            </div>
          </dl>

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
