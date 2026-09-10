import { useT } from '@/i18n'

/**
 * Where the person is in the flow. Steps already visited can be reopened, so
 * going back to fix step 1 from the review never loses what was entered.
 */
export function WizardProgress({ steps, current, visited, onJump }) {
  const { t } = useT()
  return (
    <nav className="wizard-progress" aria-label={t('intake.step_of', { n: current + 1, total: steps.length })}>
      <p className="wizard-progress__count">{t('intake.step_of', { n: current + 1, total: steps.length })}</p>
      <ol className="wizard-progress__steps">
        {steps.map((step, index) => {
          const state = index === current ? 'current' : index < current ? 'done' : 'todo'
          const reachable = index <= visited && index !== current
          return (
            <li key={step} className={`wizard-progress__step wizard-progress__step--${state}`}>
              <button
                type="button"
                className="wizard-progress__button"
                disabled={!reachable}
                aria-current={index === current ? 'step' : undefined}
                onClick={() => onJump(index)}
              >
                <span className="wizard-progress__number" aria-hidden="true">
                  {state === 'done' ? '✓' : index + 1}
                </span>
                <span className="wizard-progress__label">{t(`intake.steps.${step}`)}</span>
              </button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
