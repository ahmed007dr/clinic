import { Button, Checkbox, Input, Select, Textarea } from '@/components/ui'
import { choiceOptions, useT } from '@/i18n'

import { Cell } from './Cell'

const BLANK_CONDITION = { other_name: '', details: '', current_treatment: '' }
const BLANK_ALLERGY = { substance: '', reaction: '', severity: 'moderate' }

/**
 * Chronic conditions as a checklist (a tick is "yes"), with details and
 * current treatment only for the ones ticked — so the common answer, "none",
 * costs one click rather than ten.
 *
 * Reused by the patient file's history editor with `withAllergies={false}`
 * (allergies there have their own panel).
 */
export function StepHistory({ values, set, errors = {}, options, withAllergies = true }) {
  const { t } = useT()
  const history = values.history
  const rows = history.conditions ?? []
  const codes = (options.choices.chronic_condition ?? []).filter((code) => code !== 'other')

  const setConditions = (next) => {
    set('history', 'conditions', next)
    if (next.length) set('history', 'none_reported', false)
  }
  const indexOf = (code) => rows.findIndex((row) => row.condition === code)
  const toggle = (code) => {
    const index = indexOf(code)
    setConditions(index >= 0 ? rows.filter((_, i) => i !== index) : [...rows, { condition: code, ...BLANK_CONDITION }])
  }
  const update = (index, name, value) =>
    setConditions(rows.map((row, i) => (i === index ? { ...row, [name]: value } : row)))

  const allergies = history.allergies ?? []
  const setAllergies = (next) => set('history', 'allergies', next)

  const text = (name, rowsCount = 2) => (
    <Textarea label={t(`intake.${name}`)} rows={rowsCount} value={history[name] ?? ''}
      onChange={(event) => set('history', name, event.target.value)} error={errors[name]} />
  )

  return (
    <div className="form-grid">
      <Cell span={2}>
        <fieldset className="intake__fieldset">
          <legend>{t('intake.conditions_title')}</legend>
          <p className="ui-muted intake__hint">{t('intake.conditions_hint')}</p>
          <Checkbox
            label={t('intake.no_conditions')}
            checked={Boolean(history.none_reported)}
            onChange={(event) => {
              set('history', 'none_reported', event.target.checked)
              if (event.target.checked) set('history', 'conditions', [])
            }}
          />
          <div className="condition-list">
            {codes.map((code) => {
              const index = indexOf(code)
              const row = rows[index]
              return (
                <div key={code} className={`condition ${row ? 'condition--on' : ''}`}>
                  <Checkbox label={t(`choices.chronic_condition.${code}`)} checked={Boolean(row)}
                    onChange={() => toggle(code)} />
                  {row && (
                    <div className="condition__details">
                      <Input label={t('intake.condition_details')} value={row.details}
                        onChange={(event) => update(index, 'details', event.target.value)} />
                      <Input label={t('intake.condition_treatment')} value={row.current_treatment}
                        onChange={(event) => update(index, 'current_treatment', event.target.value)} />
                    </div>
                  )}
                </div>
              )
            })}
            {rows.map((row, index) =>
              row.condition !== 'other' ? null : (
                <div key={`other-${index}`} className="condition condition--on">
                  <div className="condition__details">
                    <Input label={t('intake.other_condition_name')} required value={row.other_name}
                      error={errors[`condition_${index}`]}
                      onChange={(event) => update(index, 'other_name', event.target.value)} />
                    <Input label={t('intake.condition_treatment')} value={row.current_treatment}
                      onChange={(event) => update(index, 'current_treatment', event.target.value)} />
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => setConditions(rows.filter((_, i) => i !== index))}>
                    {t('common.remove')}
                  </Button>
                </div>
              ),
            )}
          </div>
          <Button size="sm" onClick={() => setConditions([...rows, { condition: 'other', ...BLANK_CONDITION }])}>
            {t('intake.add_other_condition')}
          </Button>
        </fieldset>
      </Cell>

      {withAllergies && (
        <Cell span={2}>
          <fieldset className="intake__fieldset">
            <legend>{t('intake.allergies_title')}</legend>
            {allergies.length === 0 && <p className="ui-muted intake__hint">{t('intake.no_allergies_hint')}</p>}
            {allergies.map((allergy, index) => (
              <div key={index} className="allergy-row">
                <Input label={t('intake.allergy_substance')} required value={allergy.substance}
                  error={errors[`allergy_${index}`]}
                  onChange={(event) => setAllergies(allergies.map((a, i) => (i === index ? { ...a, substance: event.target.value } : a)))} />
                <Input label={t('intake.allergy_reaction')} value={allergy.reaction}
                  onChange={(event) => setAllergies(allergies.map((a, i) => (i === index ? { ...a, reaction: event.target.value } : a)))} />
                <Select label={t('intake.allergy_severity')} value={allergy.severity}
                  options={choiceOptions(t, 'allergy_severity', options.choices.allergy_severity)}
                  onChange={(event) => setAllergies(allergies.map((a, i) => (i === index ? { ...a, severity: event.target.value } : a)))} />
                <Button size="sm" variant="ghost" onClick={() => setAllergies(allergies.filter((_, i) => i !== index))}>
                  {t('common.remove')}
                </Button>
              </div>
            ))}
            <Button size="sm" onClick={() => setAllergies([...allergies, { ...BLANK_ALLERGY }])}>
              {t('intake.add_allergy')}
            </Button>
          </fieldset>
        </Cell>
      )}

      <Cell>
        <Select label={t('intake.smoking_status')} placeholder={t('common.choose')} value={history.smoking_status ?? ''}
          options={choiceOptions(t, 'smoking_status', options.choices.smoking_status)}
          onChange={(event) => set('history', 'smoking_status', event.target.value)} />
      </Cell>
      <Cell span={2}>{text('current_medications')}</Cell>
      <Cell>{text('previous_surgeries')}</Cell>
      <Cell>{text('previous_hospitalizations')}</Cell>
      <Cell span={2}>{text('family_history')}</Cell>
    </div>
  )
}
