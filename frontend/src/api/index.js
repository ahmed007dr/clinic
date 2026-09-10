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
export const visits = createResource('visits')
export const prescriptions = createResource('prescriptions')
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
  changePassword: (currentPassword, newPassword) =>
    http.post('/auth/password/', {
      current_password: currentPassword,
      new_password: newPassword,
    }),
}

export const subscription = {
  get: () => http.get('/subscription/'),
}

export const platform = {
  tenants: (params) => http.get('/platform/tenants/', params),
  tenant: (uuid) => http.get(`/platform/tenants/${uuid}/`),
  createTenant: (body) => http.post('/platform/tenants/', body),
  setStatus: (uuid, status) => http.post(`/platform/tenants/${uuid}/status/`, { status }),
  setPlan: (uuid, plan) => http.post(`/platform/tenants/${uuid}/plan/`, { plan }),
  plans: () => http.get('/platform/plans/'),
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
  clinicSettings,
  meta,
  intake,
  intakes,
  owner,
  attendance,
}

export default api
