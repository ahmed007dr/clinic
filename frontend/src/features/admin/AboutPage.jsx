import { api } from '@/api'
import { Badge } from '@/components/ui'
import { CrudPage } from '@/components/data/CrudPage'

/**
 * What the patient portal tells the public about each branch — its "About the
 * clinic" tab, seen by patients and by new visitors before they sign in.
 *
 * The group's Owner edits every branch; a branch's Admin only their own (the
 * server lists just those). Nothing is created or deleted here: branches
 * themselves are the Owner's, on the Clinics screen. The specialties shown come
 * from the branch's doctors and are only displayed here, not typed.
 */
export function AboutPage() {
  return (
    <CrudPage
      title="عن العيادة"
      subtitle="ما يراه المرضى والزوار في تبويب «عن العيادة» في بوابة المرضى: العنوان والهاتف والخريطة ومواعيد العمل"
      resource={api.about}
      canCreate={false}
      canDelete={false}
      searchPlaceholder="ابحث باسم الفرع أو عنوانه…"
      columns={[
        { key: 'name', header: 'الفرع' },
        { key: 'address', header: 'العنوان', render: (row) => row.address || '—' },
        {
          key: 'phone',
          header: 'الهاتف',
          render: (row) => (row.phone ? <span dir="ltr">{row.phone}</span> : '—'),
        },
        { key: 'working_hours', header: 'مواعيد العمل', render: (row) => row.working_hours || '—' },
        {
          key: 'map_url',
          header: 'الخريطة',
          render: (row) => (row.map_url ? <Badge tone="ok">مضاف</Badge> : <Badge tone="neutral">لا</Badge>),
        },
        {
          key: 'specializations',
          header: 'التخصصات (تلقائي من الأطباء)',
          render: (row) =>
            row.specializations.length ? row.specializations.map((s) => s.name).join('، ') : '—',
        },
      ]}
      fields={[
        { name: 'address', label: 'العنوان', type: 'textarea', span: 2 },
        { name: 'phone', label: 'الهاتف', type: 'tel' },
        {
          name: 'map_url',
          label: 'رابط الموقع على الخريطة',
          dir: 'ltr',
          hint: 'رابط يبدأ بـ https:// (من خرائط جوجل مثلاً).',
        },
        {
          name: 'working_hours',
          label: 'مواعيد العمل',
          type: 'textarea',
          span: 2,
          hint: 'مثال: السبت إلى الخميس ٩ ص – ٥ م، والجمعة إجازة.',
        },
        {
          name: 'about_text',
          label: 'نبذة عن الفرع',
          type: 'textarea',
          span: 2,
          hint: 'بضع جمل تظهر أعلى بيانات الفرع.',
        },
      ]}
      emptyMessage="لا فروع لتعديلها."
    />
  )
}
