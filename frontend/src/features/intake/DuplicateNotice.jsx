import { Link } from 'react-router-dom'

import { Button } from '@/components/ui'
import { useT } from '@/i18n'

/**
 * "This person may already be registered." Matches in the caller's own
 * clinics are listed with a link; matches in the group's other clinics are
 * only counted — the desk learns the person exists without being shown
 * another clinic's patient.
 */
export function DuplicateNotice({ found, onContinue, onDismiss }) {
  const { t } = useT()
  return (
    <div className="duplicate-notice" role="alert">
      <strong>{t('intake.duplicate_title')}</strong>
      <p>{t('intake.duplicate_body')}</p>
      {found.duplicates?.length > 0 && (
        <ul className="duplicate-notice__list">
          {found.duplicates.map((patient) => (
            <li key={patient.uuid}>
              <span>{patient.name}</span>{' '}
              <span className="ui-muted" dir="ltr">{patient.serial_number} · {patient.phone1}</span>{' '}
              <Link to={`/patients/${patient.uuid}`}>{t('intake.duplicate_open')}</Link>
            </li>
          ))}
        </ul>
      )}
      {found.other_clinics > 0 && (
        <p className="ui-muted">{t('intake.duplicate_other_clinics', { n: found.other_clinics })}</p>
      )}
      <div className="ui-row">
        <Button size="sm" variant="primary" onClick={onContinue}>{t('intake.duplicate_continue')}</Button>
        <Button size="sm" variant="ghost" onClick={onDismiss}>{t('common.back')}</Button>
      </div>
    </div>
  )
}
