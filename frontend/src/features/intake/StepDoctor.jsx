import { Select } from '@/components/ui'
import { useT } from '@/i18n'

import { Cell } from './Cell'

const MODES = ['doctor', 'specialty', 'unknown']

/**
 * A known doctor, a specialty only, or "I don't know" — all three are valid.
 * The doctor list is the clinic's own, filtered to the chosen clinic and, if
 * one is picked, the specialty.
 */
export function StepDoctor({ values, set, errors = {}, options }) {
  const { t } = useT()
  const choice = values.doctor
  const branch = values.personal.branch
  const doctors = (options.doctors ?? []).filter(
    (doctor) =>
      (!branch || doctor.branch === branch) &&
      (!choice.specialization || (doctor.specializations ?? []).includes(choice.specialization)),
  )

  return (
    <div className="form-grid">
      <Cell span={2}>
        <fieldset className="intake__fieldset">
          <legend>{t('intake.doctor_question')}</legend>
          <div className="segmented" role="radiogroup">
            {MODES.map((mode) => (
              <button key={mode} type="button" role="radio" aria-checked={choice.mode === mode}
                className={`segmented__option ${choice.mode === mode ? 'segmented__option--on' : ''}`}
                onClick={() => set('doctor', 'mode', mode)}>
                {t(`intake.doctor_mode.${mode}`)}
              </button>
            ))}
          </div>
        </fieldset>
      </Cell>

      {choice.mode !== 'unknown' && (
        <Cell>
          <Select label={t('intake.specialization')} required={choice.mode === 'specialty'}
            placeholder={t('common.choose')} value={choice.specialization} error={errors.specialization}
            options={(options.specializations ?? []).map((s) => ({ value: s.uuid, label: s.name }))}
            onChange={(event) => {
              set('doctor', 'specialization', event.target.value)
              set('doctor', 'requested_doctor', '')
            }} />
        </Cell>
      )}

      {choice.mode === 'doctor' && (
        <Cell>
          <Select label={t('intake.requested_doctor')} required placeholder={t('common.choose')}
            value={choice.requested_doctor} error={errors.requested_doctor}
            options={doctors.map((d) => ({ value: d.uuid, label: d.name }))}
            onChange={(event) => set('doctor', 'requested_doctor', event.target.value)} />
          {doctors.length === 0 && <p className="ui-muted intake__hint">{t('intake.no_matching_doctors')}</p>}
        </Cell>
      )}

      {choice.mode === 'unknown' && (
        <Cell span={2}>
          <p className="intake__note">{t('intake.unknown_doctor_note')}</p>
        </Cell>
      )}
    </div>
  )
}
