import { Input, Select, Textarea } from '@/components/ui'
import { choiceOptions, useT } from '@/i18n'
import { ageFrom, today } from '@/lib/format'

import { Cell } from './Cell'

export function StepPersonal({ values, set, errors = {}, options }) {
  const { t } = useT()
  const personal = values.personal
  const field = (name) => ({
    value: personal[name] ?? '',
    onChange: (event) => set('personal', name, event.target.value),
    error: errors[name],
  })
  const age = ageFrom(personal.birth_date)

  return (
    <div className="form-grid">
      <Cell span={2}>
        <Input label={t('intake.name')} required autoComplete="name" {...field('name')} />
      </Cell>
      <Cell>
        <Select label={t('intake.gender')} required placeholder={t('common.choose')}
          options={choiceOptions(t, 'gender', options.choices.gender)} {...field('gender')} />
      </Cell>
      <Cell>
        <Input label={t('intake.birth_date')} type="date" max={today()}
          hint={age !== null ? t('intake.age_years', { n: age }) : undefined} {...field('birth_date')} />
      </Cell>
      <Cell>
        <Input label={t('intake.phone1')} required type="tel" inputMode="tel" dir="ltr"
          autoComplete="tel" {...field('phone1')} />
      </Cell>
      <Cell>
        <Input label={t('intake.whatsapp')} type="tel" inputMode="tel" dir="ltr"
          hint={t('intake.whatsapp_hint')} {...field('whatsapp')} />
      </Cell>
      <Cell>
        <Input label={t('intake.email')} type="email" dir="ltr" autoComplete="email" {...field('email')} />
      </Cell>
      <Cell>
        <Input label={t('intake.national_id')} inputMode="numeric" dir="ltr" {...field('national_id')} />
      </Cell>
      <Cell>
        <Select label={t('intake.marital_status')}
          options={choiceOptions(t, 'marital_status', options.choices.marital_status)} {...field('marital_status')} />
      </Cell>
      {options.canChooseBranch && (
        <Cell>
          <Select label={t('intake.branch')} required placeholder={t('common.choose')}
            options={(options.branches ?? []).map((b) => ({ value: b.uuid, label: b.name }))} {...field('branch')} />
        </Cell>
      )}
      <Cell>
        <Input label={t('intake.governorate')} autoComplete="address-level1" {...field('governorate')} />
      </Cell>
      <Cell>
        <Input label={t('intake.area')} autoComplete="address-level2" {...field('area')} />
      </Cell>
      <Cell span={2}>
        <Textarea label={t('intake.address')} rows={2} autoComplete="street-address" {...field('address')} />
      </Cell>

      <Cell span={2}>
        <fieldset className="intake__fieldset">
          <legend>{t('intake.emergency_title')}</legend>
          <div className="form-grid">
            <Cell>
              <Input label={t('intake.emergency_name')} {...field('emergency_contact_name')} />
            </Cell>
            <Cell>
              <Input label={t('intake.emergency_phone')} type="tel" dir="ltr" {...field('emergency_contact_phone')} />
            </Cell>
            <Cell>
              <Input label={t('intake.emergency_relation')} {...field('emergency_contact_relation')} />
            </Cell>
          </div>
        </fieldset>
      </Cell>
    </div>
  )
}
