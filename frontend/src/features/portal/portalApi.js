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
    /** A one-time code emailed to the patient; the phone or the email identifies who. */
    requestCode: (identifier) => http.post(`${base}/auth/otp/request/`, { identifier }),
    verifyCode: (identifier, code) => http.post(`${base}/auth/otp/verify/`, { identifier, code }),
    logout: () => http.post(`${base}/auth/logout/`),
    /** Specialties, the patient's clinic's doctors and, per doctor, contracted services + price. */
    bookingOptions: () => get('booking/options/'),
    appointments: () => get('appointments/'),
    requestAppointment: (body) => http.post(`${base}/appointments/`, body),
    visits: () => get('visits/'),
    prescriptions: () => get('prescriptions/'),
    labResults: () => get('lab-results/'),
    attachments: () => get('attachments/'),
    downloadAttachment: (uuid, name) => http.download(`${base}/attachments/${uuid}/download/`, name),
    payments: () => get('payments/'),
    /** Online payment with the clinic's own gateway keys (empty when none). */
    payOptions: () => get('pay/options/'),
    payAppointment: (uuid, body) => http.post(`${base}/appointments/${uuid}/pay/`, body),
    plans: () => get('treatment-plans/'),
    allergies: () => get('allergies/'),
    /** New-patient self-registration, when the group has turned it on. */
    registerOptions: () => get('register/options/'),
    /** The group's clinics' public social/contact links (portal footer). */
    links: () => get('links/'),
    register: (body) => http.post(`${base}/register/`, body),
  }
}
