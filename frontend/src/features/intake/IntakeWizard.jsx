import { useState } from 'react'

import { Button, Card, CardBody } from '@/components/ui'
import { useT } from '@/i18n'

import { DuplicateNotice } from './DuplicateNotice'
import { StepDoctor } from './StepDoctor'
import { StepHistory } from './StepHistory'
import { StepPersonal } from './StepPersonal'
import { StepReferral } from './StepReferral'
import { StepReview } from './StepReview'
import { StepVisit } from './StepVisit'
import { WizardProgress } from './WizardProgress'
import './intake.css'

/**
 * The first-visit intake, as six short steps rather than one long form.
 *
 * One component for both doors: the front desk (`mode="staff"`, with a
 * duplicate check after step 1) and a patient registering online
 * (`mode="portal"`). Everything entered lives in one state object, so moving
 * between steps — or back from the review — never loses anything.
 *
 * Validation here only spares a round trip; the server validates everything
 * again and its answer, addressed to a section, sends the person back to the
 * step that needs fixing.
 */

export const STEPS = ['personal', 'visit', 'history', 'referral', 'doctor', 'review']
const OPTIONAL_STEPS = ['history', 'referral']

// Server sections → wizard steps. The doctor/specialty fields travel in the
// server's "visit" section but are asked on their own step.
function stepFor(section, field) {
  if (section === 'visit' && ['specialization', 'requested_doctor'].includes(field)) return 'doctor'
  if (section === 'consent') return 'review'
  return STEPS.includes(section) ? section : 'review'
}

function emptyValues(defaultBranch) {
  return {
    personal: {
      name: '', gender: '', birth_date: '', marital_status: 'single', phone1: '', whatsapp: '',
      email: '', national_id: '', governorate: '', area: '', address: '', branch: defaultBranch || '',
      emergency_contact_name: '', emergency_contact_phone: '', emergency_contact_relation: '',
    },
    visit: { case_type: 'consultation', reason_for_visit: '', symptoms: '', symptom_onset: '', reported_diagnosis: '' },
    history: {
      smoking_status: '', current_medications: '', previous_surgeries: '', previous_hospitalizations: '',
      family_history: '', conditions: [], allergies: [], none_reported: false,
    },
    referral: { referral_source: '', referral_detail: '', referring_doctor_name: '', referred_by_patient: '', recommended_doctor: '' },
    doctor: { mode: 'unknown', specialization: '', requested_doctor: '' },
    consent: { data_processing: false, contact_by_phone: true, contact_by_whatsapp: false, contact_by_sms: false, contact_by_email: false },
  }
}

function localErrors(step, values, options, t) {
  const errors = {}
  const required = t('common.required')
  if (step === 'personal') {
    const p = values.personal
    if (p.name.trim().length < 3) errors.name = required
    if (!p.gender) errors.gender = required
    if (!p.phone1.trim()) errors.phone1 = required
    if (options.canChooseBranch && !p.branch) errors.branch = required
  }
  if (step === 'visit' && !values.visit.reason_for_visit.trim()) errors.reason_for_visit = required
  if (step === 'history') {
    values.history.conditions.forEach((c, i) => {
      if (c.condition === 'other' && !c.other_name.trim()) errors[`condition_${i}`] = required
    })
    values.history.allergies.forEach((a, i) => {
      if (!a.substance.trim()) errors[`allergy_${i}`] = required
    })
  }
  if (step === 'referral') {
    const r = values.referral
    if (r.referral_source === 'doctor_referral' && !r.referring_doctor_name.trim()) errors.referring_doctor_name = required
    if (r.referral_source === 'other' && !r.referral_detail.trim()) errors.referral_detail = required
  }
  if (step === 'doctor') {
    const d = values.doctor
    if (d.mode === 'doctor' && !d.requested_doctor) errors.requested_doctor = required
    if (d.mode === 'specialty' && !d.specialization) errors.specialization = required
  }
  if (step === 'review' && !values.consent.data_processing) errors.data_processing = t('intake.consent_required')
  return errors
}

function buildPayload(values, { mode, confirmNew }) {
  const personal = { ...values.personal }
  if (!personal.birth_date) personal.birth_date = null
  if (!personal.branch) delete personal.branch

  const d = values.doctor
  const visit = {
    ...values.visit,
    specialization: d.mode !== 'unknown' && d.specialization ? d.specialization : null,
    requested_doctor: d.mode === 'doctor' && d.requested_doctor ? d.requested_doctor : null,
  }
  const body = { personal, visit, consent: values.consent }

  const h = values.history
  const answered =
    h.none_reported || h.conditions.length || h.allergies.length || h.smoking_status ||
    ['current_medications', 'previous_surgeries', 'previous_hospitalizations', 'family_history'].some((f) => h[f].trim())
  if (answered) {
    const { none_reported: _ignored, ...history } = h
    body.history = history
  }

  if (values.referral.referral_source) {
    const referral = { ...values.referral }
    referral.recommended_doctor = referral.recommended_doctor || null
    if (mode === 'portal') delete referral.referred_by_patient
    else referral.referred_by_patient = referral.referred_by_patient || null
    body.referral = referral
  }
  if (confirmNew) body.confirm_new = true
  return body
}

export function IntakeWizard({ mode, options, onSubmit, checkDuplicates, onSuccess }) {
  const { t } = useT()
  const [values, setValues] = useState(() => emptyValues(options.defaultBranch))
  const [index, setIndex] = useState(0)
  const [visited, setVisited] = useState(0)
  const [errors, setErrors] = useState({})
  const [duplicates, setDuplicates] = useState(null)
  const [confirmNew, setConfirmNew] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState(null)
  const step = STEPS[index]

  const set = (section, field, value) =>
    setValues((current) => ({ ...current, [section]: { ...current[section], [field]: value } }))

  const go = (target) => {
    setIndex(target)
    setVisited((v) => Math.max(v, target))
    setFormError(null)
    if (typeof window !== 'undefined') window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const validate = (which) => {
    const found = localErrors(which, values, options, t)
    setErrors((current) => ({ ...current, [which]: found }))
    return Object.keys(found).length === 0
  }

  const next = async () => {
    if (!validate(step)) return
    if (step === 'personal' && checkDuplicates && !confirmNew) {
      try {
        const found = await checkDuplicates(values.personal)
        if (found.duplicates.length || found.other_clinics) {
          setDuplicates(found)
          return
        }
      } catch {
        // A failed pre-check never blocks registration: the server checks again.
      }
    }
    go(index + 1)
  }

  const submit = async (overrideConfirm = confirmNew) => {
    if (!validate('review')) return
    setSubmitting(true)
    setFormError(null)
    try {
      const result = await onSubmit(buildPayload(values, { mode, confirmNew: overrideConfirm }))
      onSuccess(result)
    } catch (error) {
      if (error.status === 409 && error.payload) {
        setDuplicates(error.payload)
      } else if (error.status === 400 && error.payload && typeof error.payload === 'object' && !error.payload.detail) {
        const mapped = {}
        Object.entries(error.payload).forEach(([section, fields]) => {
          if (fields && typeof fields === 'object' && !Array.isArray(fields)) {
            Object.entries(fields).forEach(([field, messages]) => {
              const target = stepFor(section, field)
              mapped[target] = { ...(mapped[target] || {}), [field]: [].concat(messages).join(' ') }
            })
          }
        })
        setErrors(mapped)
        const first = STEPS.find((s) => mapped[s])
        setFormError(t('intake.fix_errors'))
        if (first) go(STEPS.indexOf(first))
      } else {
        setFormError(error.message)
      }
    } finally {
      setSubmitting(false)
    }
  }

  const stepProps = { values, set, errors: errors[step] || {}, options }

  return (
    <div className="intake">
      <WizardProgress steps={STEPS} current={index} visited={visited} onJump={go} />
      <Card>
        <CardBody>
          {duplicates && !confirmNew && (
            <DuplicateNotice
              found={duplicates}
              onDismiss={() => setDuplicates(null)}
              onContinue={() => {
                setConfirmNew(true)
                setDuplicates(null)
                if (step === 'review') submit(true)
                else go(index + 1)
              }}
            />
          )}
          {formError && <div className="form-error" role="alert">{formError}</div>}

          <h2 className="intake__title">{t(`intake.steps.${step}`)}</h2>
          {OPTIONAL_STEPS.includes(step) && <p className="ui-muted intake__hint">{t('intake.optional_step')}</p>}

          {step === 'personal' && <StepPersonal {...stepProps} />}
          {step === 'visit' && <StepVisit {...stepProps} />}
          {step === 'history' && <StepHistory {...stepProps} />}
          {step === 'referral' && <StepReferral {...stepProps} />}
          {step === 'doctor' && <StepDoctor {...stepProps} />}
          {step === 'review' && <StepReview {...stepProps} onEdit={(target) => go(STEPS.indexOf(target))} />}

          <div className="intake__actions">
            {index > 0 && (
              <Button onClick={() => go(index - 1)} disabled={submitting}>{t('common.back')}</Button>
            )}
            {step !== 'review' ? (
              <Button variant="primary" onClick={next}>{t('common.next')}</Button>
            ) : (
              <Button variant="primary" loading={submitting} onClick={() => submit()}>
                {mode === 'portal' ? t('intake.submit_portal') : t('intake.submit')}
              </Button>
            )}
          </div>
        </CardBody>
      </Card>
    </div>
  )
}
