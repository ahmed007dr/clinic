import { Link } from 'react-router-dom'

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
 *
 * Each branch can be left out of the tab altogether, and chosen specialties of
 * it can be hidden — for a branch that is not ready to be announced, or a
 * service it does not want to advertise. Nothing about the clinic itself changes.
 */
export function AboutPage() {
  return (
    <CrudPage
      title="عن العيادة"
      subtitle="ما يراه المرضى والزوار في تبويب «عن العيادة» في بوابة المرضى: العنوان والهاتف والخريطة ومواعيد العمل"
      resource={api.about}
      canCreate={false}
      canDelete={false}
      beforeTable={
        <p className="ui-muted">
          الشعار وصورة الغلاف للصفحة العامة: <Link to="/about/media">إدارة الصور</Link>
        </p>
      }
      searchPlaceholder="ابحث باسم الفرع أو عنوانه…"
      columns={[
        { key: 'name', header: 'الفرع' },
        {
          key: 'about_visible',
          header: 'في «عن العيادة»',
          render: (row) =>
            row.about_visible ? <Badge tone="ok">ظاهر</Badge> : <Badge tone="warn">مخفي</Badge>,
        },
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
            row.specializations.length
              ? row.specializations.map((s) => (s.hidden ? `${s.name} (مخفي)` : s.name)).join('، ')
              : '—',
        },
      ]}
      fields={[
        {
          name: 'about_visible',
          label: 'إظهار هذا الفرع في تبويب «عن العيادة»',
          type: 'checkbox',
          span: 2,
        },
        {
          name: 'online_booking_confirms_at_once',
          label: 'تأكيد الحجز من الموقع فوراً',
          type: 'checkbox',
          span: 2,
          hint: 'مغلق: يصل الحجز كطلب وتتصل العيادة بالمريض لتحديد الموعد. مفتوح: يُؤكَّد الوقت المختار ويُحجز للمريض مباشرة.',
        },
        {
          name: 'online_cancel_notice_hours',
          label: 'مهلة إلغاء الحجز المؤكَّد من الموقع (ساعات)',
          type: 'number',
          default: 24,
          hint: 'يستطيع المريض إلغاء حجزه المؤكَّد أو طلب نقله حتى هذا العدد من الساعات قبل الموعد. ٠ = في أي وقت قبله. الطلب غير المؤكَّد يُسحب دائماً.',
        },
        // The branch's specialties come with the record and are only listed here
        // (they are worked out from its doctors); never sent back.
        { name: 'specializations', hide: true },
        {
          name: 'hidden_specializations',
          label: 'تخصصات تُخفى من التبويب',
          type: 'checklist',
          optionsFrom: 'specializations',
          emptyText: 'لا تخصصات لأطباء هذا الفرع بعد.',
          hint: 'علّم ما لا تريد عرضه للمرضى. الأطباء والحجز لا يتأثران.',
          span: 2,
        },
        { name: 'address', label: 'العنوان', type: 'textarea', span: 2 },
        {
          name: 'governorate',
          label: 'المحافظة',
          hint: 'يُستخدم لعرض أقرب عيادة للعميل (مثال: القاهرة، الإسكندرية، سوهاج).',
        },
        {
          name: 'latitude',
          label: 'خط العرض',
          type: 'number',
          step: 'any',
          dir: 'ltr',
          hint: 'اختياري وأدق من المحافظة: من خرائط جوجل اضغط مطولاً على موقع العيادة وانسخ الرقمين (مثال 30.0444 و 31.2357). اكتب الاثنين معاً.',
        },
        { name: 'longitude', label: 'خط الطول', type: 'number', step: 'any', dir: 'ltr' },
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
