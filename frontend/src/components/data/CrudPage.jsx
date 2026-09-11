import { useState } from 'react'

import { Button, ConfirmDialog, Modal } from '@/components/ui'
import { FormFields, nullableNames } from '@/components/form/FormFields'
import { useForm } from '@/components/form/useForm'
import { PageHeader } from '@/components/layout/PageHeader'
import { useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'

import { ResourceTable } from './ResourceTable'

/**
 * List, create, edit and delete a resource, from a field description.
 *
 * Eight of this application's screens are exactly this and differ only in
 * their columns and fields — branches, services, expense categories, employee
 * types, specialisations, payment methods, roles, staff. Writing them out
 * individually would be eight copies of the same modal, the same error
 * handling and the same "refresh the list after saving", and the eighth copy
 * is always the one missing a piece.
 *
 * Screens with real behaviour of their own — patients, appointments, anything
 * clinical — do **not** use this. They are written out, because forcing them
 * through a generic component is how a generic component becomes unreadable.
 */
export function CrudPage({
  title,
  subtitle,
  resource,
  columns,
  fields,
  emptyMessage,
  searchPlaceholder,
  canCreate = true,
  canEdit = true,
  canDelete = true,
  createLabel = 'إضافة',
  toRecord = (row) => row,
  toInitialValues,
  deleteWarning = 'لا يمكن التراجع عن هذا الإجراء.',
  extraFilters,
  params,
}) {
  const toast = useToast()
  const [editing, setEditing] = useState(null) // row | 'new' | null
  const [deleting, setDeleting] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const refresh = () => setRefreshKey((value) => value + 1)

  const save = useMutation((values) =>
    editing === 'new'
      ? resource.create(values)
      : resource.update(editing.uuid, values),
  )
  const remove = useMutation((uuid) => resource.remove(uuid))

  const initial =
    editing && editing !== 'new'
      ? (toInitialValues ?? defaultInitialValues)(toRecord(editing), fields)
      : Object.fromEntries(fields.map((field) => [field.name, field.default ?? '']))

  const form = useForm(initial, { serverErrors: save.fieldErrors })

  const submit = async (event) => {
    event.preventDefault()
    try {
      const body = form.payload(nullableNames(fields))
      // A hidden or disabled field is one the server decides (an expense's
      // date inside a cash shift, a price from the doctor's contract):
      // sending its value would at best be ignored and at worst refused.
      fields
        .filter((field) => field.hide || field.disabled)
        .forEach((field) => delete body[field.name])
      await save.run(body)
      toast.success(editing === 'new' ? 'تمت الإضافة' : 'تم الحفظ')
      setEditing(null)
      refresh()
    } catch {
      // Field errors are already rendered against their inputs by `useForm`;
      // anything else is shown in the banner inside the modal.
    }
  }

  const confirmDelete = async () => {
    try {
      await remove.run(deleting.uuid)
      toast.success('تم الحذف')
      setDeleting(null)
      refresh()
    } catch (error) {
      toast.error(error.message)
      setDeleting(null)
    }
  }

  const allColumns = [
    ...columns,
    (canEdit || canDelete) && {
      key: '__actions',
      actions: true,
      render: (row) => (
        <div className="ui-row">
          {canEdit && (
            <Button size="sm" variant="ghost" onClick={() => setEditing(row)}>
              تعديل
            </Button>
          )}
          {canDelete && (
            <Button size="sm" variant="ghost" onClick={() => setDeleting(row)}>
              حذف
            </Button>
          )}
        </div>
      ),
    },
  ].filter(Boolean)

  return (
    <>
      <PageHeader
        title={title}
        subtitle={subtitle}
        actions={
          canCreate && (
            <Button variant="primary" onClick={() => setEditing('new')}>
              {createLabel}
            </Button>
          )
        }
      />

      <ResourceTable
        resource={resource}
        columns={allColumns}
        params={params}
        filters={extraFilters}
        refreshKey={refreshKey}
        searchPlaceholder={searchPlaceholder}
        empty={{ title: 'لا توجد سجلات', message: emptyMessage }}
      />

      <Modal
        open={Boolean(editing)}
        onClose={() => {
          setEditing(null)
          save.reset()
        }}
        title={editing === 'new' ? createLabel : 'تعديل'}
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
            fields={fields}
            form={form}
            errors={save.fieldErrors}
            disabled={save.submitting}
          />
          {/* Lets Enter submit the form without a visible duplicate button. */}
          <button type="submit" className="u-visually-hidden" tabIndex={-1}>
            حفظ
          </button>
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        onConfirm={confirmDelete}
        loading={remove.submitting}
        title="تأكيد الحذف"
        message={`سيتم حذف «${deleting?.name ?? ''}». ${deleteWarning}`}
        confirmLabel="حذف"
      />
    </>
  )
}

/** Pull each field's current value out of a record, ready for the form. */
function defaultInitialValues(record, fields) {
  const values = {}
  fields.forEach((field) => {
    const value = record[field.name]
    if (value === null || value === undefined) {
      values[field.name] = ''
    } else if (field.type === 'date' && typeof value === 'string') {
      // The API sends full ISO timestamps; `<input type="date">` accepts only
      // the date part and silently shows nothing if given the rest.
      values[field.name] = value.slice(0, 10)
    } else if (field.type === 'datetime' && typeof value === 'string') {
      values[field.name] = value.slice(0, 16)
    } else {
      values[field.name] = value
    }
  })
  return values
}
