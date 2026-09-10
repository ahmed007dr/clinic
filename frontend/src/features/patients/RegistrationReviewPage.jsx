import { useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '@/api'
import { Badge, Button, ConfirmDialog, DescriptionList, Loading, Modal } from '@/components/ui'
import { ResourceTable } from '@/components/data/ResourceTable'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { useT } from '@/i18n'
import { formatDate, formatDateTime } from '@/lib/format'

/**
 * Self-registrations waiting for the front desk: confirm as a new patient,
 * merge into the patient they turned out to be, or reject.
 */
export function RegistrationReviewPage() {
  const { t } = useT()
  const [selected, setSelected] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)

  return (
    <>
      <PageHeader title={t('review.title')} subtitle={t('review.subtitle')}
        back={{ to: '/patients', label: t('intake.back_to_patients') }} />
      <ResourceTable
        resource={api.patients}
        params={{ needs_review: '1' }}
        refreshKey={refreshKey}
        searchPlaceholder={t('review.search')}
        onRowClick={setSelected}
        empty={{ title: t('review.empty') }}
        columns={[
          { key: 'name', header: t('intake.name') },
          { key: 'phone1', header: t('intake.phone1'), render: (row) => <span dir="ltr">{row.phone1 || '—'}</span> },
          { key: 'branch_name', header: t('common.clinic'), render: (row) => row.branch_name || '—' },
          { key: 'created_at', header: t('review.submitted'), render: (row) => formatDateTime(row.created_at) },
          { key: 'state', header: '', render: () => <Badge tone="warn">{t('review.pending')}</Badge> },
        ]}
      />
      {selected && (
        <ReviewModal
          uuid={selected.uuid}
          onClose={() => setSelected(null)}
          onDone={() => {
            setSelected(null)
            setRefreshKey((k) => k + 1)
          }}
        />
      )}
    </>
  )
}

function ReviewModal({ uuid, onClose, onDone }) {
  const { t } = useT()
  const toast = useToast()
  const [rejecting, setRejecting] = useState(false)
  const { data, loading } = useAsync(() => api.patients.review(uuid), [uuid])
  const confirm = useMutation(() => api.patients.confirmRegistration(uuid))
  const merge = useMutation((target) => api.patients.mergeInto(uuid, target))
  const reject = useMutation(() => api.patients.rejectRegistration(uuid))

  const run = async (mutation, message, argument) => {
    try {
      await mutation.run(argument)
      toast.success(message)
      onDone()
    } catch (error) {
      toast.error(error.message)
    }
  }

  const patient = data?.patient
  const choice = (group, code) => (code ? t(`choices.${group}.${code}`) : null)

  return (
    <Modal
      open
      onClose={onClose}
      title={t('review.title')}
      size="wide"
      footer={
        <>
          <Button variant="primary" loading={confirm.submitting}
            onClick={() => run(confirm, t('review.confirmed'))}>{t('review.confirm')}</Button>
          <Button variant="danger" onClick={() => setRejecting(true)}>{t('review.reject')}</Button>
          <Button variant="ghost" onClick={onClose}>{t('common.close')}</Button>
        </>
      }
    >
      {loading || !patient ? (
        <Loading />
      ) : (
        <div className="ui-stack">
          <DescriptionList
            items={[
              { label: t('intake.name'), value: patient.name },
              { label: t('intake.phone1'), value: <span dir="ltr">{patient.phone1}</span> },
              { label: t('intake.whatsapp'), value: patient.whatsapp ? <span dir="ltr">{patient.whatsapp}</span> : null },
              { label: t('intake.national_id'), value: patient.national_id },
              { label: t('intake.birth_date'), value: patient.birth_date ? formatDate(patient.birth_date) : null },
              { label: t('common.clinic'), value: patient.branch_name },
              { label: t('intake.governorate'), value: [patient.governorate, patient.area].filter(Boolean).join(' — ') },
              { label: t('intake.referral_source'), value: choice('referral_source', patient.referral_source) },
              { label: t('intake.referrer_name'), value: patient.referral_detail },
              { label: t('review.submitted'), value: formatDateTime(patient.created_at) },
            ]}
          />
          <section>
            <h3 className="ui-card__title">{t('review.duplicates')}</h3>
            {data.duplicates.length === 0 ? (
              <p className="ui-muted">{t('review.no_duplicates')}</p>
            ) : (
              <ul className="duplicate-notice__list">
                {data.duplicates.map((match) => (
                  <li key={match.uuid} className="ui-row" style={{ justifyContent: 'space-between' }}>
                    <span>
                      <Link to={`/patients/${match.uuid}`}>{match.name}</Link>{' '}
                      <span className="ui-muted" dir="ltr">{match.serial_number} · {match.phone1}</span>
                    </span>
                    <Button size="sm" loading={merge.submitting}
                      onClick={() => run(merge, t('review.merged'), match.uuid)}>{t('review.merge')}</Button>
                  </li>
                ))}
              </ul>
            )}
            {data.other_clinics > 0 && (
              <p className="ui-muted">{t('intake.duplicate_other_clinics', { n: data.other_clinics })}</p>
            )}
          </section>
        </div>
      )}
      <ConfirmDialog
        open={rejecting}
        onClose={() => setRejecting(false)}
        loading={reject.submitting}
        title={t('review.reject_title')}
        message={t('review.reject_message')}
        confirmLabel={t('review.reject')}
        onConfirm={() => run(reject, t('review.rejected'))}
      />
    </Modal>
  )
}
