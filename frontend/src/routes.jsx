/**
 * Every screen in the application, and who may open it.
 *
 * One flat list, so "where is the page for X" is answered by reading this file
 * rather than by following imports. Screens load lazily: the clinical and
 * administrative sections are most of the code, and a receptionist never opens
 * them, so they are not in the bundle that loads at the front desk.
 *
 * `permission` only decides what renders. The API re-authorises every call.
 */

import { lazy } from 'react'

const page = (loader, name) =>
  lazy(() => loader().then((module) => ({ default: module[name] })))

const DashboardPage = page(() => import('@/features/dashboard/DashboardPage'), 'DashboardPage')
const PatientListPage = page(() => import('@/features/patients/PatientListPage'), 'PatientListPage')
const PatientFormPage = page(() => import('@/features/patients/PatientFormPage'), 'PatientFormPage')
const PatientDetailPage = page(() => import('@/features/patients/PatientDetailPage'), 'PatientDetailPage')
const AppointmentListPage = page(() => import('@/features/appointments/AppointmentListPage'), 'AppointmentListPage')
const AppointmentFormPage = page(() => import('@/features/appointments/AppointmentFormPage'), 'AppointmentFormPage')
const QueuePage = page(() => import('@/features/appointments/QueuePage'), 'QueuePage')
const PaymentListPage = page(() => import('@/features/billing/PaymentListPage'), 'PaymentListPage')
const PaymentFormPage = page(() => import('@/features/billing/PaymentFormPage'), 'PaymentFormPage')
const ExpenseListPage = page(() => import('@/features/billing/ExpenseListPage'), 'ExpenseListPage')
const FinancialReportPage = page(() => import('@/features/billing/FinancialReportPage'), 'FinancialReportPage')
const VisitListPage = page(() => import('@/features/clinical/VisitListPage'), 'VisitListPage')
const PrescriptionListPage = page(() => import('@/features/clinical/PrescriptionListPage'), 'PrescriptionListPage')
const TreatmentPlanListPage = page(() => import('@/features/clinical/TreatmentPlanListPage'), 'TreatmentPlanListPage')
const TreatmentSessionListPage = page(() => import('@/features/clinical/TreatmentSessionListPage'), 'TreatmentSessionListPage')
const ProcedureListPage = page(() => import('@/features/clinical/ProcedureListPage'), 'ProcedureListPage')
const LabResultListPage = page(() => import('@/features/clinical/LabResultListPage'), 'LabResultListPage')
const AttachmentListPage = page(() => import('@/features/clinical/AttachmentListPage'), 'AttachmentListPage')
const StaffListPage = page(() => import('@/features/admin/StaffListPage'), 'StaffListPage')
const EmployeeListPage = page(() => import('@/features/admin/EmployeeListPage'), 'EmployeeListPage')
const BranchListPage = page(() => import('@/features/admin/BranchListPage'), 'BranchListPage')
const ServiceListPage = page(() => import('@/features/admin/ServiceListPage'), 'ServiceListPage')
const SettingsPage = page(() => import('@/features/admin/SettingsPage'), 'SettingsPage')
const SubscriptionPage = page(() => import('@/features/admin/SubscriptionPage'), 'SubscriptionPage')
const AccountPage = page(() => import('@/features/account/AccountPage'), 'AccountPage')
const NotificationListPage = page(() => import('@/features/notifications/NotificationListPage'), 'NotificationListPage')
const NotFoundPage = page(() => import('@/features/misc/NotFoundPage'), 'NotFoundPage')

export const routes = [
  { index: true, element: DashboardPage },

  { path: 'patients', element: PatientListPage },
  { path: 'patients/new', element: PatientFormPage },
  { path: 'patients/:uuid', element: PatientDetailPage },
  { path: 'patients/:uuid/edit', element: PatientFormPage },

  { path: 'appointments', element: AppointmentListPage },
  { path: 'appointments/new', element: AppointmentFormPage },
  { path: 'appointments/:uuid/edit', element: AppointmentFormPage },
  { path: 'queue', element: QueuePage },

  { path: 'payments', element: PaymentListPage },
  { path: 'payments/new', element: PaymentFormPage },
  { path: 'payments/:uuid/edit', element: PaymentFormPage },
  { path: 'expenses', element: ExpenseListPage, permission: 'manage_billing' },
  { path: 'reports/financial', element: FinancialReportPage },

  { path: 'visits', element: VisitListPage, permission: 'view_clinical' },
  { path: 'visits/new', element: VisitListPage, permission: 'view_clinical' },
  { path: 'prescriptions', element: PrescriptionListPage, permission: 'view_clinical' },
  { path: 'treatment-plans', element: TreatmentPlanListPage, permission: 'view_clinical' },
  { path: 'treatment-sessions', element: TreatmentSessionListPage, permission: 'view_clinical' },
  { path: 'procedures', element: ProcedureListPage, permission: 'view_clinical' },
  { path: 'lab-results', element: LabResultListPage, permission: 'view_clinical' },
  { path: 'attachments', element: AttachmentListPage, permission: 'view_clinical' },

  { path: 'staff', element: StaffListPage, permission: 'is_admin' },
  { path: 'employees', element: EmployeeListPage, permission: 'is_admin' },
  { path: 'branches', element: BranchListPage, permission: 'is_admin' },
  { path: 'services', element: ServiceListPage, permission: 'is_admin' },
  { path: 'settings', element: SettingsPage, permission: 'is_admin' },
  { path: 'subscription', element: SubscriptionPage, permission: 'is_admin' },

  { path: 'settings/account', element: AccountPage },
  { path: 'notifications', element: NotificationListPage },

  { path: '*', element: NotFoundPage },
]

/* The owner portal — a separate section with its own frame, loaded only by
   platform operators. */
export const PlatformShell = page(() => import('@/features/platform/PlatformShell'), 'PlatformShell')
const PlatformTenantsPage = page(() => import('@/features/platform/PlatformTenantsPage'), 'PlatformTenantsPage')
const PlatformTenantPage = page(() => import('@/features/platform/PlatformTenantPage'), 'PlatformTenantPage')

export const platformRoutes = [
  { index: true, element: PlatformTenantsPage },
  { path: 'tenants/:uuid', element: PlatformTenantPage },
]

/* The patient portal — patients only, mobile-first. */
export const PortalApp = page(() => import('@/features/portal/PortalApp'), 'PortalApp')
