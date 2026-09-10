import { Select, Textarea } from '@/components/ui'
import { choiceOptions, useT } from '@/i18n'

import { Cell } from './Cell'

/** The patient's reason, in their words — never the diagnosis. */
export function StepVisit({ values, set, errors = {}, options }) {
  const { t } = useT()
  const visit = values.visit
  const field = (name) => ({
    value: visit[name] ?? '',
    onChange: (event) => set('visit', name, event.target.value),
    error: errors[name],
  })

  return (
    <div className="form-grid">
      <Cell span={2}>
        <p className="intake__note">{t('intake.visit_note')}</p>
      </Cell>
      <Cell>
        <Select label={t('intake.case_type')}
          options={choiceOptions(t, 'case_type', options.choices.case_type)} {...field('case_type')} />
      </Cell>
      <Cell>
        <Select label={t('intake.symptom_onset')} placeholder={t('common.choose')}
          options={choiceOptions(t, 'symptom_onset', options.choices.symptom_onset)} {...field('symptom_onset')} />
      </Cell>
      <Cell span={2}>
        <Textarea label={t('intake.reason_for_visit')} required rows={3}
          hint={t('intake.reason_hint')} {...field('reason_for_visit')} />
      </Cell>
      <Cell span={2}>
        <Textarea label={t('intake.symptoms')} rows={3} {...field('symptoms')} />
      </Cell>
      <Cell span={2}>
        <Textarea label={t('intake.reported_diagnosis')} rows={2}
          hint={t('intake.reported_diagnosis_hint')} {...field('reported_diagnosis')} />
      </Cell>
    </div>
  )
}
