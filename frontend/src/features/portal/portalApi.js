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
    appointment: (uuid) => get(`appointments/${uuid}/`),
    cancelAppointment: (uuid) => http.post(`${base}/appointments/${uuid}/cancel/`),
    /** Ask for another time; the clinic settles it by phone (docs/15 Phase 6). */
    rescheduleAppointment: (uuid, body) => http.post(`${base}/appointments/${uuid}/reschedule/`, body),
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
    /** The group's running branches: address, phone, map, hours, specialties. Public. */
    about: () => get('about/'),
    /** The group's clinics' public social/contact links (portal footer). */
    links: () => get('links/'),
    register: (body) => http.post(`${base}/register/`, body),
    /** The public catalogue (docs/15 Phase 3): services → the clinics that offer one → its doctors. */
    catalogServices: () => get('catalog/services/'),
    catalogBranches: (service) => get(`catalog/services/${service}/branches/`),
    /** Coming days with a free time, and the times on one day (docs/15 Phase 4). */
    catalogDays: (choice) => http.get(`${base}/catalog/availability/days/`, choice),
    catalogSlots: (choice, date) => http.get(`${base}/catalog/availability/`, { ...choice, date }),
    catalogDoctors: (service, branch) => get(`catalog/services/${service}/branches/${branch}/doctors/`),
    /** Creating an account, proved by a code (docs/15 Phase 2): the form, then the code. */
    accountStart: (body) => http.post(`${base}/account/start/`, body),
    accountVerify: (ticket, code) => http.post(`${base}/account/verify/`, { ticket, code }),
    /** The patient's own contact details; a new e-mail address is proved by a code first. */
    profile: () => get('me/profile/'),
    saveProfile: (body) => http.patch(`${base}/me/profile/`, body),
    changeEmail: (email) => http.post(`${base}/me/email/`, { email }),
    verifyEmail: (ticket, code) => http.post(`${base}/me/email/verify/`, { ticket, code }),
    /** Creating an account, proved by a code (docs/15 Phase 2): the form, then the code. */
    accountStart: (body) => http.post(`${base}/account/start/`, body),
    accountVerify: (ticket, code) => http.post(`${base}/account/verify/`, { ticket, code }),
    /** The patient's own contact details; a new e-mail address is proved by a code first. */
    profile: () => get('me/profile/'),
    saveProfile: (body) => http.patch(`${base}/me/profile/`, body),
    changeEmail: (email) => http.post(`${base}/me/email/`, { email }),
    verifyEmail: (ticket, code) => http.post(`${base}/me/email/verify/`, { ticket, code }),
  }
}
