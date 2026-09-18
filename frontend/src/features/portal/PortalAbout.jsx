import { EmptyState, ErrorState, Loading } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'

import { usePortal } from './PortalContext'

/**
 * The clinic's branches — where they are, how to reach them, when they open, and
 * what they offer. The same panel is the "About" tab inside the portal and the
 * body of the public page a visitor sees before signing in. What it shows is
 * written by the group's Owner and each branch's Admin (Admin › About the
 * clinic); the specialties are worked out from the branch's doctors.
 */
export function PortalAbout() {
  const { api } = usePortal()
  const { data, loading, error, reload } = useAsync(() => api.about(), [api])

  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />
  const branches = data?.branches ?? []
  if (branches.length === 0) return <EmptyState title="لم تُضف العيادة بياناتها بعد" />

  return (
    <div className="portal-about">
      {branches.map((branch) => (
        <section key={branch.name} className="portal-card portal-about__branch">
          <h2 className="portal-about__name">{branch.name}</h2>
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
        </section>
      ))}
    </div>
  )
}
