import { EmptyState, ErrorState, Loading } from '@/components/ui'
import { serverUrl } from '@/lib/config'
import { useAsync } from '@/hooks/useApi'

import { usePortal } from './PortalContext'

/**
 * The clinic's branches — where they are, how to reach them, when they open,
 * what they offer, and the doctors who agreed to be shown. The same panel is the
 * "About" tab inside the portal and the body of the public page a visitor sees
 * before signing in. What it shows is written by the group's Owner and each
 * branch's Admin (Admin › About the clinic); the specialties are worked out from
 * the branch's doctors, and a logo or cover appears only once the Owner approved it.
 */
export function PortalAbout({ data: given }) {
  const { api } = usePortal()
  const fetched = useAsync(() => (given ? Promise.resolve(given) : api.about()), [api, given])
  const { data, loading, error, reload } = fetched

  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />
  const branches = data?.branches ?? []
  if (branches.length === 0) return <EmptyState title="لم تُضف العيادة بياناتها بعد" />

  return (
    <div className="portal-about">
      {branches.map((branch) => (
        <BranchSection key={branch.name} branch={branch} />
      ))}
    </div>
  )
}

function BranchSection({ branch }) {
  return (
    <section className="portal-card portal-about__branch">
      {branch.cover && (
        <img className="portal-about__cover" src={serverUrl(branch.cover)} alt="" loading="lazy" />
      )}
      <div className="portal-about__title">
        {branch.logo && (
          <img className="portal-about__logo" src={serverUrl(branch.logo)} alt="" loading="lazy" />
        )}
        <h2 className="portal-about__name">{branch.name}</h2>
      </div>
      {branch.about_text && <p className="portal-about__text">{branch.about_text}</p>}

      <dl className="portal-about__facts">
        {branch.address && (
          <>
            <dt>العنوان</dt>
            <dd>
              {branch.address}
              {branch.map_url && (
                <>
                  {' '}
                  <a href={branch.map_url} target="_blank" rel="noopener noreferrer">
                    الموقع على الخريطة
                  </a>
                </>
              )}
            </dd>
          </>
        )}
        {!branch.address && branch.map_url && (
          <>
            <dt>العنوان</dt>
            <dd>
              <a href={branch.map_url} target="_blank" rel="noopener noreferrer">
                الموقع على الخريطة
              </a>
            </dd>
          </>
        )}
        {branch.phone && (
          <>
            <dt>الهاتف</dt>
            <dd>
              <a href={`tel:${branch.phone}`} dir="ltr">
                {branch.phone}
              </a>
            </dd>
          </>
        )}
        {branch.working_hours && (
          <>
            <dt>مواعيد العمل</dt>
            <dd className="portal-about__text">{branch.working_hours}</dd>
          </>
        )}
      </dl>

      {branch.links?.length > 0 && (
        <ul className="portal-about__links">
          {branch.links.map((link) => (
            <li key={link.kind}>
              <a href={link.url} target="_blank" rel="noopener noreferrer">
                {link.label}
              </a>
            </li>
          ))}
        </ul>
      )}

      {branch.specializations.length > 0 && (
        <div>
          <strong>التخصصات</strong>
          <ul className="portal-about__chips">
            {branch.specializations.map((specialty) => (
              <li key={specialty.name} title={specialty.description || undefined}>
                {specialty.name}
              </li>
            ))}
          </ul>
        </div>
      )}

      {branch.doctors?.length > 0 && (
        <div>
          <strong>الأطباء</strong>
          <ul className="portal-about__doctors">
            {branch.doctors.map((doctor) => (
              <li key={doctor.name} className="portal-doctor">
                <span className="portal-doctor__name">د. {doctor.name}</span>
                {doctor.specializations.length > 0 && (
                  <span className="portal-doctor__specialties">{doctor.specializations.join('، ')}</span>
                )}
                {doctor.tagline && <span className="portal-doctor__tagline">{doctor.tagline}</span>}
                {doctor.links?.length > 0 && (
                  <span className="portal-doctor__links">
                    {doctor.links.map((link) => (
                      <a key={link.kind} href={link.url} target="_blank" rel="noopener noreferrer">
                        {link.label}
                      </a>
                    ))}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
