/**
 * Every server call the application can make, in one object.
 *
 *   import { api } from '@/api'
 *   const page = await api.patients.list({ search: 'أحمد' })
 *
 * Grouped by the thing rather than by the screen, so two screens that need the
 * same data call the same function instead of each growing their own copy.
 */

import { http } from '@/lib/http'
import { createResource } from './resource'

/* Reference data */
export const branches = createResource('branches')
export const services = createResource('services')
export const employeeTypes = createResource('employee-types')
export const specializations = createResource('specializations')
export const salaryTypes = createResource('salary-types')
export const employees = createResource('employees')
export const doctors = createResource('doctors')

/* People */
export const patients = {
  ...createResource('patients'),
  /** §19 — the unified history the system never had a screen for. */
  timeline: (uuid) => http.get(`/patients/${uuid}/timeline/`),
  portalStatus: (uuid) => http.get(`/patients/${uuid}/portal/`),
  portalInvite: (uuid) => http.post(`/patients/${uuid}/portal-invite/`),
  portalRevoke: (uuid) => http.post(`/patients/${uuid}/portal-revoke/`),
  /** The history the patient reported — clinical roles only. */
  history: (uuid) => http.get(`/patients/${uuid}/history/`),
  saveHistory: (uuid, body) => http.put(`/patients/${uuid}/history/`, body),
  /** Self-registrations waiting for the front desk. */
  review: (uuid) => http.get(`/patients/${uuid}/review/`),
  confirmRegistration: (uuid) => http.post(`/patients/${uuid}/confirm-registration/`),
  mergeInto: (uuid, target) => http.post(`/patients/${uuid}/merge-into/`, { target }),
  rejectRegistration: (uuid) => http.post(`/patients/${uuid}/reject-registration/`),
}

export const appointments = {
  ...createResource('appointments'),
  today: (params) => http.get('/appointments/today/', params),
  waiting: (params) => http.get('/appointments/waiting/', params),
  setStatus: (uuid, status) => http.post(`/appointments/${uuid}/status/`, { status }),
  /** The follow-up date on the visit this booking opened (front desk). */
  followUp: (uuid, date) => http.post(`/appointments/${uuid}/follow-up/`, { date }),
  /** This booking's prescriptions, as print links only. */
  prescriptions: (uuid) => http.get(`/appointments/${uuid}/prescriptions/`),
}

/* Money */
export const payments = createResource('payments')
export const paymentMethods = createResource('payment-methods')
export const expenses = createResource('expenses')
export const expenseCategories = createResource('expense-categories')
export const financialReport = {
  get: (params) => http.get('/financial-report/', params),
}

/* Clinical */
export const visits = {
  ...createResource('visits'),
  /** Patients sent in to the signed-in doctor today, with their visits. */
  inRoom: () => http.get('/visits/in-room/'),
}
export const prescriptions = {
  ...createResource('prescriptions'),
  /** A new prescription for `visit`'s patient with this one's medicines. */
  copy: (uuid, visit) => http.post(`/prescriptions/${uuid}/copy/`, { visit }),
}
export const treatmentPlans = createResource('treatment-plans')
export const treatmentSessions = createResource('treatment-sessions')
export const procedures = createResource('procedures')
export const labResults = {
  ...createResource('lab-results'),
  acknowledge: (uuid) => http.post(`/lab-results/${uuid}/acknowledge/`),
  release: (uuid, released) => http.post(`/lab-results/${uuid}/release/`, { released }),
}
export const allergies = createResource('allergies')
export const attachments = {
  ...createResource('attachments'),
  /** The file is streamed by an authenticated view — the storage has no URL. */
  download: (uuid, filename) =>
    http.download(`/attachments/${uuid}/download/`, filename),
  release: (uuid, released) => http.post(`/attachments/${uuid}/release/`, { released }),
}

/* Administration */
export const staff = createResource('staff')
export const roles = createResource('roles')

/* Personal */
export const notifications = {
  ...createResource('notifications'),
  unreadCount: () => http.get('/notifications/unread-count/'),
  markRead: (uuid) => http.post(`/notifications/${uuid}/read/`),
  markAllRead: () => http.post('/notifications/read-all/'),
}

/* Session */
export const auth = {
  session: () => http.get('/auth/session/'),
  login: (email, password) => http.post('/auth/login/', { email, password }),
  logout: () => http.post('/auth/logout/'),
  /** The second step of a platform sign-in: authenticator or recovery code. */
  twoFactor: (code) => http.post('/auth/two-factor/', { code }),
  /** Leave a developer's "login as" support session. */
  endSupport: () => http.post('/auth/support/end/'),
  changePassword: (currentPassword, newPassword) =>
    http.post('/auth/password/', {
      current_password: currentPassword,
      new_password: newPassword,
    }),
  /** A doctor linked to several clinics picks the one they are looking at. */
  setBranch: (branch) => http.post('/auth/branch/', { branch }),
}

/* Cash shifts: your own through `current`/`open`/`close`; management lists,
   reviews and reopens (billing/shifts.py on the server). */
export const shifts = {
  ...createResource('shifts'),
  current: () => http.get('/shifts/current/'),
  open: (body) => http.post('/shifts/open/', body),
  close: (uuid, notes) => http.post(`/shifts/${uuid}/close/`, { notes }),
  reopen: (uuid) => http.post(`/shifts/${uuid}/reopen/`),
}

/** Asking to open a clinic group (public). */
export const signup = {
  options: () => http.get('/signup/options/'),
  submit: (body) => http.post('/signup/', body),
}

export const subscription = {
  get: () => http.get('/subscription/'),
  /* The group's invoices from the platform, and paying one online. */
  invoices: () => http.get('/subscription/invoices/'),
  pay: (id, body) => http.post(`/subscription/invoices/${id}/pay/`, body),
}

export const platform = {
  tenants: (params) => http.get('/platform/tenants/', params),
  tenant: (uuid) => http.get(`/platform/tenants/${uuid}/`),
  createTenant: (body) => http.post('/platform/tenants/', body),
  setStatus: (uuid, status) => http.post(`/platform/tenants/${uuid}/status/`, { status }),
  setPlan: (uuid, plan) => http.post(`/platform/tenants/${uuid}/plan/`, { plan }),
  plans: () => http.get('/platform/plans/'),
  /* Developer portal — monitoring (platform_admin/monitoring.py). */
  overview: () => http.get('/platform/overview/'),
  online: () => http.get('/platform/online/'),
  analytics: (params) => http.get('/platform/analytics/', params),
  /* Backups, exports and imports (api/platform_backups.py). */
  backups: () => http.get('/platform/backups/'),
  startBackup: () => http.post('/platform/backups/'),
  setBackupPolicy: (body) => http.patch('/platform/backups/policy/', body),
  cpanelBackup: () => http.post('/platform/backups/cpanel/'),
  downloadBackup: (id, name) => http.download(`/platform/backups/${id}/download/`, name),
  exportGroup: (uuid, name, files = true) =>
    http.download(`/platform/tenants/${uuid}/export/${files ? '' : '?files=0'}`, name),
  importGroup: (formData) => http.post('/platform/imports/', formData),
  people: (uuid) => http.get(`/platform/tenants/${uuid}/people/`),
  branches: (uuid) => http.get(`/platform/tenants/${uuid}/branches/`),
  /* Full control over a group (api/platform_control.py). */
  editTenant: (uuid, body) => http.patch(`/platform/tenants/${uuid}/edit/`, body),
  addOwner: (uuid, body) => http.post(`/platform/tenants/${uuid}/owners/`, body),
  setBranchActive: (uuid, id, active) => http.post(`/platform/tenants/${uuid}/branches/${id}/active/`, { active }),
  accountAction: (uuid, action) => http.post(`/platform/accounts/${uuid}/${action}/`),
  entitlements: (uuid) => http.get(`/platform/tenants/${uuid}/entitlements/`),
  setEntitlements: (uuid, body) => http.patch(`/platform/tenants/${uuid}/entitlements/`, body),
  supportSessions: (uuid) => http.get(`/platform/tenants/${uuid}/support/`),
  startSupport: (uuid, body) => http.post(`/platform/tenants/${uuid}/support/`, body),
  /* Keys and passwords — entered here only, returned masked (platform_admin/vault.py). */
  integrations: (params) => http.get('/platform/integrations/', params),
  saveIntegration: (body) => http.post('/platform/integrations/', body),
  updateIntegration: (id, body) => http.patch(`/platform/integrations/${id}/`, body),
  removeIntegration: (id) => http.delete(`/platform/integrations/${id}/`),
  testIntegration: (id, mode) => http.post(`/platform/integrations/${id}/test/`, { mode }),
  mailboxes: (params) => http.get('/platform/mailboxes/', params),
  createMailbox: (body) => http.post('/platform/mailboxes/', body),
  /* Subscriptions billing (platform_admin/billing.py). */
  balances: () => http.get('/platform/billing/'),
  billing: (uuid) => http.get(`/platform/tenants/${uuid}/billing/`),
  setTerms: (uuid, body) => http.patch(`/platform/tenants/${uuid}/billing/`, body),
  addDiscount: (uuid, body) => http.post(`/platform/tenants/${uuid}/billing/discounts/`, body),
  removeDiscount: (uuid, id) => http.delete(`/platform/tenants/${uuid}/billing/discounts/`, { params: { id } }),
  issueInvoice: (uuid, body) => http.post(`/platform/tenants/${uuid}/billing/invoices/`, body),
  voidInvoice: (id, reason) => http.post(`/platform/billing/invoices/${id}/void/`, { reason }),
  recordPayment: (uuid, body) => http.post(`/platform/tenants/${uuid}/billing/payments/`, body),
  markLate: (uuid, note) => http.post(`/platform/tenants/${uuid}/billing/late/`, { note }),
  clearLate: (uuid) => http.delete(`/platform/tenants/${uuid}/billing/late/`),
  /* Requests to open a clinic group (api/signup.py). */
  signups: (params) => http.get('/platform/signups/', params),
  approveSignup: (id, body) => http.post(`/platform/signups/${id}/approve/`, body),
  rejectSignup: (id, body) => http.post(`/platform/signups/${id}/reject/`, body),
  /* The plan catalogue. */
  managePlans: () => http.get('/platform/plans/manage/'),
  createPlan: (body) => http.post('/platform/plans/manage/', body),
  updatePlan: (id, body) => http.patch(`/platform/plans/${id}/`, body),
}

export const clinicSettings = {
  get: () => http.get('/clinic-settings/'),
  update: (body) => http.patch('/clinic-settings/', body),
}

export const dashboard = {
  get: () => http.get('/dashboard/'),
}

/* The codes behind every choice list, fetched once per page load: they only
   change with a deployment. A failed fetch is forgotten so the next caller retries. */
let choicesRequest = null
export const meta = {
  choices: () =>
    (choicesRequest ??= http.get('/meta/choices/').catch((error) => {
      choicesRequest = null
      throw error
    })),
}

/* First-visit intake */
export const intake = {
  register: (body) => http.post('/intake/register/', body),
  duplicates: (params) => http.get('/intake/duplicates/', params),
}
export const intakes = createResource('intakes')

/* The group owner's overview of every clinic */
export const owner = {
  overview: (params) => http.get('/owner/overview/', params),
}

export const attendance = {
  ...createResource('attendance'),
  sheet: (params) => http.get('/attendance/sheet/', params),
  saveSheet: (body) => http.post('/attendance/sheet/', body),
}

/* Doctor contracts (management writes; a doctor reads their own) and the
   doctor's share of every payment (billing/commissions.py). */
export const doctorRates = {
  ...createResource('doctor-rates'),
  /** The price a booking with this doctor and service gets. */
  quote: (doctor, service) => http.get('/doctor-rates/quote/', { doctor, service }),
}
export const commissions = {
  ...createResource('commissions'),
  summary: (params) => http.get('/commissions/summary/', params),
  settle: (uuids) => http.post('/commissions/settle/', { uuids }),
}

/* A clinic's printed look: letterhead and intake form (branches/printing.py). */
export const printSettings = {
  get: (branch) => http.get(`/branches/${branch}/print-settings/`),
  update: (branch, body) => http.patch(`/branches/${branch}/print-settings/`, body),
  uploadLogo: (branch, file) => {
    const body = new FormData()
    body.append('logo', file)
    return http.patch(`/branches/${branch}/print-settings/`, body)
  },
}

/* A doctor's own footer line and links: they write, the clinic approves. */
export const doctorProfile = {
  mine: () => http.get('/me/doctor-profile/'),
  save: (body) => http.put('/me/doctor-profile/', body),
  list: (params) => http.get('/doctor-profiles/', params),
  approve: (doctor) => http.post(`/doctor-profiles/${doctor}/approve/`),
  reject: (doctor, note) => http.post(`/doctor-profiles/${doctor}/reject/`, { note }),
}

export const api = {
  branches,
  services,
  employeeTypes,
  specializations,
  salaryTypes,
  employees,
  doctors,
  patients,
  appointments,
  payments,
  paymentMethods,
  expenses,
  expenseCategories,
  financialReport,
  visits,
  prescriptions,
  treatmentPlans,
  treatmentSessions,
  procedures,
  labResults,
  attachments,
  allergies,
  staff,
  roles,
  notifications,
  auth,
  dashboard,
  subscription,
  platform,
  signup,
  clinicSettings,
  meta,
  intake,
  intakes,
  owner,
  attendance,
  shifts,
  doctorRates,
  commissions,
  printSettings,
  doctorProfile,
}

export default api
