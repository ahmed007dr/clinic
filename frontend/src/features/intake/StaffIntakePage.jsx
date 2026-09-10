import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '@/api'
import { Button, Card, CardBody, ErrorState, Loading } from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAsync } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useT } from '@/i18n'

import { IntakeWizard } from './IntakeWizard'

/** New patient registration at the front desk. */
export function StaffIntakePage() {
  const { t } = useT()
  const { user, permissions } = useAuth()
  const navigate = useNavigate()
  const [result, setResult] = useState(null)
  const [round, setRound] = useState(0)

  // The clinic's own lists — no doctor or specialty is ever hardcoded.
  const { data, loading, error, reload } = useAsync(async () => {
    const [choices, branches, specializations, doctors] = await Promise.all([
      api.meta.choices(),
      api.branches.list({ page_size: 200 }),
      api.specializations.list({ page_size: 200 }),
      api.doctors.list({ page_size: 200 }),
    ])
    return {
      choices,
      branches: branches.results,
      specializations: specializations.results,
      doctors: doctors.results,
    }
  }, [])

  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />

  return (
    <>
      <PageHeader title={t('intake.title')} back={{ to: '/patients', label: t('intake.back_to_patients') }} />
      {result ? (
        <Card>
          <CardBody>
            <div className="intake-success">
              <span className="intake-success__mark" aria-hidden="true">✓</span>
              <h2>{t('intake.success_title')}</h2>
              <p>{t('intake.success_serial', { name: result.patient.name, serial: result.patient.serial_number })}</p>
              <div className="ui-row">
                <Button variant="primary" onClick={() => navigate(`/patients/${result.patient.uuid}`)}>
                  {t('intake.open_file')}
                </Button>
                <Button onClick={() => { setResult(null); setRound((r) => r + 1) }}>
                  {t('intake.register_another')}
                </Button>
              </div>
            </div>
          </CardBody>
        </Card>
      ) : (
        <IntakeWizard
          key={round}
          mode="staff"
          options={{
            ...data,
            canChooseBranch: permissions.all_branches,
            defaultBranch: user?.branch?.uuid,
            patientResource: api.patients,
          }}
          checkDuplicates={(personal) =>
            api.intake.duplicates({
              phone: personal.phone1, whatsapp: personal.whatsapp, national_id: personal.national_id,
            })
          }
          onSubmit={api.intake.register}
          onSuccess={setResult}
        />
      )}
    </>
  )
}
