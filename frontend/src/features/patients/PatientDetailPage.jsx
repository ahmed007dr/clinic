import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api } from '@/api'
import {
  Avatar,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  DescriptionList,
  ErrorState,
  Loading,
  Tabs,
} from '@/components/ui'
import { PageHeader } from '@/components/layout/PageHeader'
import { useRecord } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { formatDate, formatMoney } from '@/lib/format'

import { AllergyPanel } from '@/features/clinical/AllergyPanel'
import { useT } from '@/i18n'

import { MedicalHistoryCard } from './MedicalHistoryCard'
import { PortalCard } from './PortalCard'

import { PatientTimeline } from './PatientTimeline'
import './patient.css'

const GENDER = { male: 'ذكر', female: 'أنثى' }
const MARITAL = { single: 'أعزب', married: 'متزوج' }

/**
 * One patient: who they are, and everything that has happened to them.
 *
 * The timeline is the point of this screen. Before it, the same information
 * existed only as six separate tables on six separate screens, so nobody could
 * answer "what has been going on with this patient" without opening all six
 * and reading them in parallel.
 */
export function PatientDetailPage() {
  const { uuid } = useParams()
  const navigate = useNavigate()
  const { permissions } = useAuth()
  const { t } = useT()
  const [tab, setTab] = useState('timeline')

  const { record: patient, loading, error, reload } = useRecord(api.patients, uuid)

  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />
  if (!patient) return null

  const tabs = [
    { id: 'timeline', label: 'السجل الزمني' },
    { id: 'details', label: 'البيانات' },
  ]

  return (
    <>
      <PageHeader
        title={
          <span className="patient__heading">
            <Avatar name={patient.name} src={patient.photo_url} size="lg" />
            <span>
              {patient.name}
              <span className="patient__serial ui-muted"> {patient.serial_number}</span>
            </span>
          </span>
        }
        subtitle={[
          GENDER[patient.gender],
          patient.age !== null && patient.age !== undefined
            ? `${patient.age} سنة`
            : null,
          patient.branch_name,
        ]
          .filter(Boolean)
          .join(' · ')}
        back={{ to: '/patients', label: 'رجوع للمرضى' }}
        actions={
          <>
            {permissions.view_clinical && (
              <Button
                variant="primary"
                onClick={() => navigate(`/visits/new?patient=${patient.uuid}`)}
              >
                زيارة جديدة
              </Button>
            )}
            <Button
              onClick={() => navigate(`/appointments/new?patient=${patient.uuid}`)}
            >
              حجز موعد
            </Button>
            <Button variant="ghost" onClick={() => navigate(`/patients/${uuid}/edit`)}>
              تعديل
            </Button>
          </>
        }
      />

      <div className="patient__layout">
        <div className="patient__main ui-stack">
          <Card>
            <CardBody flush>
              <div style={{ padding: '0 var(--s4)' }}>
                <Tabs items={tabs} active={tab} onChange={setTab} />
              </div>
              <div style={{ padding: 'var(--s5)' }}>
                {tab === 'timeline' ? (
                  <PatientTimeline uuid={uuid} />
                ) : (
                  <DescriptionList
                    columns={2}
                    items={[
                      { label: 'الاسم', value: patient.name },
                      { label: 'رقم الملف', value: patient.serial_number },
                      { label: 'النوع', value: GENDER[patient.gender] },
                      {
                        label: 'الحالة الاجتماعية',
                        value: MARITAL[patient.marital_status],
                      },
                      {
                        label: 'تاريخ الميلاد',
                        value: patient.birth_date
                          ? `${formatDate(patient.birth_date)} (${patient.age} سنة)`
                          : null,
                      },
                      { label: 'الرقم القومي', value: patient.national_id },
                      {
                        label: 'الهاتف',
                        value: patient.phone1 ? (
                          <a href={`tel:${patient.phone1}`} dir="ltr">
                            {patient.phone1}
                          </a>
                        ) : null,
                      },
                      {
                        label: 'هاتف آخر',
                        value: patient.phone2 ? (
                          <span dir="ltr">{patient.phone2}</span>
                        ) : null,
                      },
                      { label: 'البريد الإلكتروني', value: patient.email },
                      {
                        label: t('intake.whatsapp'),
                        value: patient.whatsapp ? <span dir="ltr">{patient.whatsapp}</span> : null,
                      },
                      {
                        label: t('intake.governorate'),
                        value: [patient.governorate, patient.area].filter(Boolean).join(' — ') || null,
                      },
                      {
                        label: t('intake.emergency_title'),
                        value:
                          [patient.emergency_contact_name, patient.emergency_contact_relation, patient.emergency_contact_phone]
                            .filter(Boolean)
                            .join(' · ') || null,
                      },
                      {
                        label: t('patient.referral'),
                        value: patient.referral_source
                          ? [t(`choices.referral_source.${patient.referral_source}`), patient.referring_doctor_name, patient.referral_detail]
                              .filter(Boolean)
                              .join(' — ')
                          : null,
                      },
                      { label: t('patient.recommended_doctor'), value: patient.recommended_doctor_name },
                      {
                        label: t('patient.contact_prefs'),
                        value:
                          ['phone', 'whatsapp', 'sms', 'email']
                            .filter((channel) => patient[`contact_by_${channel}`])
                            .map((channel) => t(`intake.contact_${channel}`))
                            .join('، ') || null,
                      },
                      {
                        label: t('patient.consent'),
                        value: patient.consent_data_processing_at
                          ? formatDate(patient.consent_data_processing_at)
                          : t('patient.consent_missing'),
                      },
                      { label: 'الفرع', value: patient.branch_name },
                      { label: 'العنوان', value: patient.address, span: 2 },
                      { label: 'ملاحظات', value: patient.notes, span: 2 },
                      {
                        label: 'تاريخ التسجيل',
                        value: formatDate(patient.created_at),
                      },
                    ]}
                  />
                )}
              </div>
            </CardBody>
          </Card>
          {permissions.view_clinical && <MedicalHistoryCard patientUuid={uuid} />}
        </div>

        <aside className="patient__side ui-stack">
          {permissions.view_clinical && <AllergyPanel patientUuid={uuid} />}
          <PortalCard patientUuid={uuid} hasPhone={Boolean(patient.phone1)} />
          <PatientSummary uuid={uuid} canViewClinical={permissions.view_clinical} />
        </aside>
      </div>
    </>
  )
}

/** Counts and quick links, from the lists the user is allowed to see. */
function PatientSummary({ uuid, canViewClinical }) {
  return (
    <Card>
      <CardHeader title="روابط سريعة" />
      <CardBody>
        <div className="patient__links">
          <Link to={`/appointments?patient=${uuid}`}>المواعيد</Link>
          <Link to={`/payments?patient=${uuid}`}>الدفعات</Link>
          {canViewClinical && (
            <>
              <Link to={`/visits?patient=${uuid}`}>الزيارات</Link>
              <Link to={`/prescriptions?patient=${uuid}`}>الروشتات</Link>
              <Link to={`/treatment-plans?patient=${uuid}`}>خطط العلاج</Link>
              <Link to={`/procedures?patient=${uuid}`}>الإجراءات</Link>
              <Link to={`/lab-results?patient=${uuid}`}>التحاليل</Link>
              <Link to={`/attachments?patient=${uuid}`}>المستندات</Link>
            </>
          )}
        </div>
      </CardBody>
    </Card>
  )
}
