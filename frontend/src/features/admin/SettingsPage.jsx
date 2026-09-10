import { useState } from 'react'

import { api } from '@/api'
import { Tabs } from '@/components/ui'
import { CrudPage } from '@/components/data/CrudPage'
import { PageHeader } from '@/components/layout/PageHeader'

import { PortalSettings } from './PortalSettings'

/**
 * The five short reference lists, behind one set of tabs.
 *
 * Each is a name and a description. Five separate screens in the sidebar would
 * be five entries that are opened once when the clinic is set up and never
 * again — and would push the things people use daily further down the menu.
 */

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
  const [tab, setTab] = useState('expense-categories')
  const section = SECTIONS[tab]

  return (
    <>
      <PageHeader title="الإعدادات" subtitle="القوائم المرجعية للعيادة" />

      <div style={{ marginBottom: 'var(--s4)' }}>
        <Tabs
          items={Object.entries(SECTIONS).map(([id, entry]) => ({
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
