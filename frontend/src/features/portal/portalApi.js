/**
 * The patient portal's server calls. Everything is under `/api/portal/<slug>/`
 * and authenticated by the portal's own cookie — never the staff session.
 */

import { http } from '@/lib/http'

export function portalApi(slug) {
  const base = `/portal/${slug}`
  const get = (path) => http.get(`${base}/${path}`)
  return {
    me: () => get('me/'),
    login: (phone, password) => http.post(`${base}/auth/login/`, { phone, password }),
    acceptInvite: (token, password) => http.post(`${base}/auth/accept-invite/`, { token, password }),
    logout: () => http.post(`${base}/auth/logout/`),
    appointments: () => get('appointments/'),
    requestAppointment: (body) => http.post(`${base}/appointments/`, body),
    visits: () => get('visits/'),
    prescriptions: () => get('prescriptions/'),
    labResults: () => get('lab-results/'),
    attachments: () => get('attachments/'),
    downloadAttachment: (uuid, name) => http.download(`${base}/attachments/${uuid}/download/`, name),
    payments: () => get('payments/'),
    plans: () => get('treatment-plans/'),
    allergies: () => get('allergies/'),
    /** New-patient self-registration, when the group has turned it on. */
    registerOptions: () => get('register/options/'),
    register: (body) => http.post(`${base}/register/`, body),
  }
}
