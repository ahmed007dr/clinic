import { api } from '@/api'
import { Badge } from '@/components/ui'
import { CrudPage } from '@/components/data/CrudPage'

/**
 * Clinic user accounts.
 *
 * Deleting is deactivating — the server refuses to remove a user who is
 * referenced by the audit trail, appointments and expenses they created, and
 * an account that can no longer sign in is what "remove this person" actually
 * means for a clinic.
 */
export function StaffListPage() {
  return (
    <CrudPage
      title="المستخدمون"
      subtitle="حسابات الدخول إلى النظام"
      resource={api.staff}
      createLabel="إضافة مستخدم"
      searchPlaceholder="ابحث بالاسم أو البريد…"
      deleteWarning="سيُوقف الحساب ويخرج صاحبه من النظام فوراً. لا تُحذف سجلاته، ويمكن إعادة تشغيله من «تعديل». الأدمن يوقف حسابات الموظفين والأطباء في فرعه، وصاحب المجمع يوقف أي حساب."
      columns={[
        { key: 'username', header: 'اسم المستخدم' },
        { key: 'email', header: 'البريد', render: (row) => <span dir="ltr">{row.email}</span> },
        {
          key: 'role_name',
          header: 'الدور',
          render: (row) =>
            row.role_name ? (
              <Badge tone="primary">{row.role_name}</Badge>
            ) : (
              <Badge tone="warn">بلا دور</Badge>
            ),
        },
        {
          key: 'branch_name',
          header: 'الفرع',
          render: (row) => row.branch_name || '—',
        },
        {
          key: 'employee_name',
          header: 'سجل الطبيب',
          // An unlinked doctor account sees no patients at all — worth a flag.
          render: (row) =>
            row.employee_name ||
            (row.role_name === 'Doctor' ? <Badge tone="warn">غير مرتبط</Badge> : '—'),
        },
        {
          key: 'is_active',
          header: 'الحالة',
          render: (row) => (
            <Badge tone={row.is_active ? 'ok' : 'neutral'}>
              {row.is_active ? 'نشط' : 'معطّل'}
            </Badge>
          ),
        },
      ]}
      fields={[
        { name: 'username', label: 'اسم المستخدم', required: true },
        { name: 'email', label: 'البريد الإلكتروني', type: 'email', required: true },
        { name: 'first_name', label: 'الاسم الأول' },
        { name: 'last_name', label: 'اسم العائلة' },
        { name: 'role', label: 'الدور', type: 'relation', resource: api.roles },
        { name: 'branch', label: 'الفرع', type: 'relation', resource: api.branches },
        {
          name: 'employee',
          label: 'سجل الطبيب',
          type: 'relation',
          resource: api.doctors,
          span: 2,
          hint: 'لحسابات الأطباء فقط: الطبيب يرى مرضاه وزياراته هو فقط، وتُكتب باسمه.',
        },
        {
          name: 'password',
          label: 'كلمة المرور',
          type: 'password',
          span: 2,
          // Blank on edit leaves the existing password alone, so changing
          // someone's branch does not force a password reset.
          hint: 'اتركها فارغة عند التعديل للإبقاء على كلمة المرور الحالية. ٨ أحرف على الأقل.',
        },
        { name: 'is_active', label: 'الحساب نشط', type: 'checkbox', default: true },
      ]}
      emptyMessage="أضف حسابات لموظفي العيادة."
    />
  )
}
