import { useState } from 'react'

import { api } from '@/api'
import { Badge, Button, Card, CardBody, CardHeader, DescriptionList, ErrorState, Loading, Modal } from '@/components/ui'
import { StepHistory } from '@/features/intake/StepHistory'
import { useAsync, useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { useT } from '@/i18n'
import { formatDate } from '@/lib/format'

/**
 * The history the patient reported, for clinicians. Labelled as reported —
 * a doctor reading it must never mistake it for someone's diagnosis.
 * Served only to clinical roles (the API refuses Reception).
 */
export function MedicalHistoryCard({ patientUuid }) {
  const { t } = useT()
  const toast = useToast()
  const history = useAsync(() => api.patients.history(patientUuid), [patientUuid])
  const intakes = useAsync(() => api.intakes.list({ patient: patientUuid, page_size: 10 }), [patientUuid])
  const choices = useAsync(() => api.meta.choices(), [])
  const [draft, setDraft] = useState(null)
  const save = useMutation((body) => api.patients.saveHistory(patientUuid, body))
  const choice = (group, code) => (code ? t(`choices.${group}.${code}`) : null)

  if (history.loading || choices.loading) return <Loading />
  if (history.error) return <ErrorState error={history.error} onRetry={history.reload} />
  const data = history.data

  const conditions = data.conditions.length ? (
    <ul className="history__conditions">
      {data.conditions.map((c) => (
        <li key={c.uuid}>
          <strong>{c.condition === 'other' ? c.other_name : choice('chronic_condition', c.condition)}</strong>
          {c.details && <span> — {c.details}</span>}
          {c.current_treatment && <div className="ui-muted">{c.current_treatment}</div>}
        </li>
      ))}
    </ul>
  ) : data.conditions_reviewed ? t('history.none_reported') : <span className="ui-muted">{t('history.not_recorded')}</span>

  const startEditing = () =>
    setDraft({
      smoking_status: data.smoking_status, current_medications: data.current_medications,
      previous_surgeries: data.previous_surgeries, previous_hospitalizations: data.previous_hospitalizations,
      family_history: data.family_history, none_reported: data.conditions_reviewed && !data.conditions.length,
      conditions: data.conditions.map(({ condition, other_name, details, current_treatment }) =>
        ({ condition, other_name, details, current_treatment })),
      allergies: [],
    })

  const submit = async () => {
    const { none_reported: _n, allergies: _a, ...body } = draft
    try {
      await save.run({ ...body, conditions_reviewed: true })
      toast.success(t('history.saved'))
      setDraft(null)
      history.reload()
    } catch (error) {
      toast.error(error.message)
    }
  }

  return (
    <Card>
      <CardHeader title={t('history.title')} subtitle={t('history.note')}
        actions={<Button size="sm" onClick={startEditing}>{t('common.edit')}</Button>} />
      <CardBody>
        <DescriptionList
          columns={1}
          keepEmpty
          items={[
            { label: t('history.conditions'), value: conditions },
            { label: t('intake.current_medications'), value: data.current_medications || '—' },
            { label: t('intake.previous_surgeries'), value: data.previous_surgeries || '—' },
            { label: t('intake.previous_hospitalizations'), value: data.previous_hospitalizations || '—' },
            { label: t('intake.family_history'), value: data.family_history || '—' },
            { label: t('intake.smoking_status'), value: choice('smoking_status', data.smoking_status) || '—' },
          ]}
        />

        <h3 className="ui-card__title history__heading">{t('history.intakes')}</h3>
        {(intakes.data?.results ?? []).length === 0 ? (
          <p className="ui-muted">{t('history.no_intakes')}</p>
        ) : (
          <ul className="history__intakes">
            {intakes.data.results.map((intake) => (
              <li key={intake.uuid}>
                <div className="ui-row">
                  <Badge tone="info">{choice('case_type', intake.case_type)}</Badge>
                  <span className="ui-muted">{formatDate(intake.created_at)}</span>
                  {intake.symptom_onset && <span className="ui-muted">· {choice('symptom_onset', intake.symptom_onset)}</span>}
                </div>
                <p>{intake.reason_for_visit}</p>
                {intake.symptoms && <p className="ui-muted">{intake.symptoms}</p>}
                {(intake.specialization_name || intake.requested_doctor_name) && (
                  <p className="ui-muted">{[intake.specialization_name, intake.requested_doctor_name].filter(Boolean).join(' · ')}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardBody>

      <Modal
        open={Boolean(draft)}
        onClose={() => setDraft(null)}
        title={t('history.title')}
        size="wide"
        footer={
          <>
            <Button variant="primary" loading={save.submitting} onClick={submit}>{t('common.save')}</Button>
            <Button variant="ghost" onClick={() => setDraft(null)}>{t('common.cancel')}</Button>
          </>
        }
      >
        {draft && (
          <StepHistory
            values={{ history: draft }}
            set={(_section, field, value) => setDraft((current) => ({ ...current, [field]: value }))}
            options={{ choices: choices.data }}
            withAllergies={false}
          />
        )}
      </Modal>
    </Card>
  )
}
