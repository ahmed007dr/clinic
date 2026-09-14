import { useState } from 'react'

import { api } from '@/api'
import { Tabs } from '@/components/ui'
import { CrudPage } from '@/components/data/CrudPage'
import { PageHeader } from '@/components/layout/PageHeader'
import { useAuth } from '@/hooks/useAuth'

import { PortalSettings } from './PortalSettings'

/**
 * The five short reference lists, behind one set of tabs.
 *
 * Each is a name and a description. Five separate screens in the sidebar would
 * be five entries that are opened once when the clinic is set up and never
 * again — and would push the things people use daily further down the menu.
 */

const PURPOSE_OPTIONS = [
  { value: 'ticket', label: 'تذاكر الانتظار' },
  { value: 'payment', label: 'إيصالات الدفع' },
  { value: 'expense', label: 'إيصالات المصروفات' },
]

const PRINTER_FIELDS = [
  { name: 'branch', label: 'الفرع', type: 'relation', resource: api.branches, required: true },
  { name: 'name', label: 'اسم الطابعة', required: true, hint: 'مثل: طابعة الاستقبال' },
  { name: 'purpose', label: 'الغرض', type: 'select', options: PURPOSE_OPTIONS, required: true },
  { name: 'is_default', label: 'الطابعة الافتراضية لهذا الغرض في هذا الفرع', type: 'checkbox' },
  { name: 'is_active', label: 'نشطة', type: 'checkbox', default: true },
  { name: 'ip_address', label: 'عنوان IP', dir: 'ltr' },
  { name: 'mac_address', label: 'عنوان MAC', dir: 'ltr', placeholder: '00:1A:2B:3C:4D:5E' },
  { name: 'subnet_mask', label: 'Subnet Mask', dir: 'ltr' },
  { name: 'gateway', label: 'Gateway', dir: 'ltr' },
  { name: 'dhcp', label: 'DHCP مفعّل', type: 'checkbox', default: true },
  { name: 'port', label: 'المنفذ (Port)', type: 'number', min: 1, max: 65535, hint: 'الافتراضي 9100' },
  { name: 'notes', label: 'ملاحظات', type: 'textarea', span: 2 },
]

const PRINTER_COLUMNS = [
  { key: 'name', header: 'الاسم' },
  { key: 'branch_name', header: 'الفرع' },
  { key: 'purpose_display', header: 'الغرض' },
  { key: 'ip_address', header: 'IP', render: (row) => row.ip_address || '—' },
  { key: 'mac_address', header: 'MAC', render: (row) => row.mac_address || '—' },
  { key: 'is_default', header: 'افتراضية', render: (row) => (row.is_default ? '✓' : '—') },
  { key: 'is_active', header: 'نشطة', render: (row) => (row.is_active ? '✓' : 'موقوفة') },
]

const SECTIONS = {
  'expense-categories': {
    label: 'بنود المصروفات',
    resource: api.expenseCategories,
    createLabel: 'إضافة بند',
  },
  'payment-methods': {
    label: 'طرق الدفع',
    resource: api.paymentMethods,
    createLabel: 'إضافة طريقة',
  },
  specializations: {
    label: 'التخصصات',
    resource: api.specializations,
    createLabel: 'إضافة تخصص',
  },
  'employee-types': {
    label: 'أنواع الوظائف',
    resource: api.employeeTypes,
    createLabel: 'إضافة نوع',
    note: 'النوع «Doctor» مطلوب لحجز المواعيد مع الأطباء — لا تحذفه.',
  },
  portal: { label: 'بوابة المرضى' },
  'salary-types': {
    label: 'أنواع الرواتب',
    resource: api.salaryTypes,
    createLabel: 'إضافة نوع',
    fields: [{ name: 'name', label: 'الاسم', required: true }],
    columns: [{ key: 'name', header: 'الاسم' }],
  },
  printers: {
    label: 'الطابعات',
    resource: api.printers,
    createLabel: 'إضافة طابعة',
    note:
      'سجلّ مرجعي فقط — يطبع المتصفح على الطابعة المضافة في نظام التشغيل بنفس عنوان IP، وليس على هذا السجل مباشرة.',
    fields: PRINTER_FIELDS,
    columns: PRINTER_COLUMNS,
  },
}

const DEFAULT_COLUMNS = [
  { key: 'name', header: 'الاسم' },
  {
    key: 'description',
    header: 'الوصف',
    render: (row) => row.description || '—',
  },
]

const DEFAULT_FIELDS = [
  { name: 'name', label: 'الاسم', required: true },
  { name: 'description', label: 'الوصف', type: 'textarea', span: 2 },
]

export function SettingsPage() {
  const { permissions } = useAuth()
  const [tab, setTab] = useState('expense-categories')
  const section = SECTIONS[tab]

  return (
    <>
      <PageHeader title="الإعدادات" subtitle="القوائم المرجعية للعيادة" />

      <div style={{ marginBottom: 'var(--s4)' }}>
        <Tabs
          // Portal settings are group-wide, so the tab is the Owner's alone
          // (the API refuses anyone else regardless).
          items={Object.entries(SECTIONS)
            .filter(([id]) => id !== 'portal' || permissions.is_owner)
            .map(([id, entry]) => ({
            id,
            label: entry.label,
          }))}
          active={tab}
          onChange={setTab}
        />
      </div>

      {/* Keyed so switching tabs remounts the page: without it the previous
          section's rows stay on screen while the new ones load, and for a
          moment the wrong list is shown under the right heading. */}
      {tab === 'portal' ? (
        <PortalSettings />
      ) : (
      <CrudPage
        key={tab}
        title={section.label}
        subtitle={section.note}
        resource={section.resource}
        columns={section.columns ?? DEFAULT_COLUMNS}
        fields={section.fields ?? DEFAULT_FIELDS}
        createLabel={section.createLabel}
        emptyMessage="لا توجد عناصر بعد."
      />
      )}
    </>
  )
}
