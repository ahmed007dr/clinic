import { RelationSelect } from '@/components/data/RelationSelect'
import { Input, Select } from '@/components/ui'
import { choiceOptions, useT } from '@/i18n'

import { Cell } from './Cell'

/**
 * How they found us. Two facts are kept apart: *who* sent them (the source,
 * and the referrer's name or record) and *which of our doctors* someone
 * recommended. The doctor they are coming to see is chosen on the next step.
 */
export function StepReferral({ values, set, errors = {}, options }) {
  const { t } = useT()
  const referral = values.referral
  const source = referral.referral_source
  const field = (name) => ({
    value: referral[name] ?? '',
    onChange: (event) => set('referral', name, event.target.value),
    error: errors[name],
  })

  return (
    <div className="form-grid">
      <Cell span={2}>
        <Select label={t('intake.referral_source')} placeholder={t('common.choose')}
          options={choiceOptions(t, 'referral_source', options.choices.referral_source)} {...field('referral_source')} />
      </Cell>

      {source === 'doctor_referral' && (
        <Cell span={2}>
          <Input label={t('intake.referring_doctor_name')} required {...field('referring_doctor_name')} />
        </Cell>
      )}

      {source === 'existing_patient' && options.patientResource && (
        <Cell span={2}>
          <RelationSelect label={t('intake.referred_by_patient')} resource={options.patientResource} searchable
            value={referral.referred_by_patient} onChange={(value) => set('referral', 'referred_by_patient', value || '')}
            error={errors.referred_by_patient} />
        </Cell>
      )}

      {['friend_family', 'existing_patient'].includes(source) && (
        <Cell span={2}>
          <Input label={t('intake.referrer_name')} {...field('referral_detail')} />
        </Cell>
      )}

      {source === 'other' && (
        <Cell span={2}>
          <Input label={t('intake.referral_detail_other')} required {...field('referral_detail')} />
        </Cell>
      )}

      {source && (
        <Cell span={2}>
          <Select label={t('intake.recommended_doctor')} placeholder={t('common.none')}
            hint={t('intake.recommended_doctor_hint')}
            options={(options.doctors ?? []).map((d) => ({ value: d.uuid, label: d.name }))}
            {...field('recommended_doctor')} />
        </Cell>
      )}
    </div>
  )
}
