import { Button, Checkbox } from '@/components/ui'
import { useT } from '@/i18n'
import { formatDate } from '@/lib/format'

/** Everything entered, grouped by step, each with a way back — then consent. */
export function StepReview({ values, set, errors = {}, options, onEdit }) {
  const { t } = useT()
  const { personal, visit, history, referral, doctor, consent } = values
  const name = (list, uuid) => (list ?? []).find((item) => item.uuid === uuid)?.name
  const choice = (group, code) => (code ? t(`choices.${group}.${code}`) : null)
  const none = t('intake.summary.none')

  const sections = [
    ['personal', [
      [t('intake.name'), personal.name],
      [t('intake.gender'), choice('gender', personal.gender)],
      [t('intake.birth_date'), personal.birth_date ? formatDate(personal.birth_date) : null],
      [t('intake.phone1'), personal.phone1],
      [t('intake.whatsapp'), personal.whatsapp],
      [t('intake.branch'), name(options.branches, personal.branch)],
      [t('intake.governorate'), [personal.governorate, personal.area].filter(Boolean).join(' — ')],
      [t('intake.emergency_title'), [personal.emergency_contact_name, personal.emergency_contact_phone].filter(Boolean).join(' — ')],
    ]],
    ['visit', [
      [t('intake.case_type'), choice('case_type', visit.case_type)],
      [t('intake.reason_for_visit'), visit.reason_for_visit],
      [t('intake.symptoms'), visit.symptoms],
      [t('intake.symptom_onset'), choice('symptom_onset', visit.symptom_onset)],
    ]],
    ['history', [
      [t('intake.conditions_title'),
        history.conditions.length
          ? history.conditions.map((c) => (c.condition === 'other' ? c.other_name : choice('chronic_condition', c.condition))).join('، ')
          : history.none_reported ? t('intake.no_conditions') : null],
      [t('intake.allergies_title'), history.allergies.map((a) => a.substance).filter(Boolean).join('، ')],
      [t('intake.current_medications'), history.current_medications],
      [t('intake.smoking_status'), choice('smoking_status', history.smoking_status)],
    ]],
    ['referral', [
      [t('intake.referral_source'), choice('referral_source', referral.referral_source)],
      [t('intake.referring_doctor_name'), referral.referring_doctor_name],
      [t('intake.referrer_name'), referral.referral_detail],
      [t('intake.recommended_doctor'), name(options.doctors, referral.recommended_doctor)],
    ]],
    ['doctor', [
      [t('intake.doctor_question'), t(`intake.doctor_mode.${doctor.mode}`)],
      [t('intake.specialization'), name(options.specializations, doctor.specialization)],
      [t('intake.requested_doctor'), doctor.mode === 'doctor' ? name(options.doctors, doctor.requested_doctor) : null],
    ]],
  ]

  return (
    <div className="review">
      <p className="ui-muted">{t('intake.review_hint')}</p>
      {sections.map(([step, rows]) => (
        <section key={step} className="review__section">
          <header className="review__header">
            <h3>{t(`intake.steps.${step}`)}</h3>
            <Button size="sm" variant="ghost" onClick={() => onEdit(step)}>{t('common.edit')}</Button>
          </header>
          <dl className="review__list">
            {rows.map(([label, value]) => (
              <div key={label} className="review__row">
                <dt>{label}</dt>
                <dd>{value || <span className="ui-muted">{none}</span>}</dd>
              </div>
            ))}
          </dl>
        </section>
      ))}

      <fieldset className="intake__fieldset review__consent">
        <legend>{t('intake.consent_title')}</legend>
        <Checkbox label={t('intake.consent_data')} checked={consent.data_processing}
          onChange={(event) => set('consent', 'data_processing', event.target.checked)} />
        {errors.data_processing && <p className="ui-field__error" role="alert">{errors.data_processing}</p>}
        <p className="ui-field__label">{t('intake.contact_title')}</p>
        {['phone', 'whatsapp', 'sms', 'email'].map((channel) => (
          <Checkbox key={channel} label={t(`intake.contact_${channel}`)} checked={consent[`contact_by_${channel}`]}
            onChange={(event) => set('consent', `contact_by_${channel}`, event.target.checked)} />
        ))}
      </fieldset>
    </div>
  )
}
