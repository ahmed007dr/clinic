# واجهة العيادة — React

تطبيق React منفصل تماماً عن الباك إند. لا يشارك Django إلا في شيئين: يطلب البيانات من
`/api/`، ويُخدَم ملفه المبني من `/app/`. لا قوالب Django هنا، ولا كود Python.

```
frontend/                ← الفرونت إند كله، ولا شيء غيره
  src/
    lib/                 ← أدوات بلا واجهة: http.js (الاتصال)، format.js (التواريخ والمبالغ)
    api/                 ← كل طلب للخادم، مجمّعة حسب المورد
    hooks/               ← useAuth، useApi، useToast، useDebounce
    components/
      ui/                ← المكونات الصغيرة المشتركة: Button, Table, Modal, Badge …
      form/              ← useForm و FormFields
      data/              ← ResourceTable، RelationSelect، CrudPage
      layout/            ← الإطار: الشريط الجانبي، الرأس، الحراسة
    features/            ← الشاشات، مجلد لكل قسم
    routes.jsx           ← كل الشاشات في قائمة واحدة
  dist/spa/              ← الناتج المبني (يُرفع على git — انظر «النشر»)
```

---

## التشغيل أثناء التطوير

نافذتان:

```bash
# 1) الباك إند
python manage.py runserver

# 2) الفرونت إند
cd frontend
npm install        # أول مرة فقط
npm run dev        # http://localhost:5173/app/
```

Vite يمرّر `/api` و `/media` إلى `127.0.0.1:8000`، فالتطبيق يعمل من نفس الأصل
(same-origin) في التطوير كما في الإنتاج. **لا يوجد CORS ولا يجب إضافته** — كوكي الجلسة
يعمل كما هو، ولا توجد إعدادات CORS يمكن أن تُضبط خطأً.

حسابات التجربة بعد `python manage.py seed_demo --reset`:
`admin@dr-ahmed.local` · `doctor@dr-ahmed.local` · `reception@dr-ahmed.local`
وكلمة المرور `demo-clinic-2026`. الدخول بالبريد، لا باسم المستخدم.

---

## القواعد

هذه القواعد هي ما يُبقي كل ملف صغيراً والتطبيق متماسكاً. كل واحدة منها موجودة لأن مخالفتها
تنتج خطأً محدداً.

### 1. المكونات تُستدعى من مكان واحد

```jsx
import { Button, Card, Table, Modal, Badge } from '@/components/ui'
import { ResourceTable } from '@/components/data/ResourceTable'
import { api } from '@/api'
```

`@` يشير إلى `src/`، فالاستيراد واحد من أي عمق — لا `../../../`. إذا احتجت شيئاً مرتين
في شاشتين، مكانه `components/`، لا نسخة ثانية.

### 2. `fetch` في ملف واحد فقط: `lib/http.js`

كل طلب يمرّ عبر `api/*`، وهي تمرّ عبر `lib/http.js`. هناك يُضاف رمز CSRF، وتُقرأ
أخطاء الحقول، ويُكتشف انتهاء الجلسة. أي `fetch` آخر هو مكان ثانٍ يمكن أن ينسى رمز
CSRF — والنتيجة فورم «معطّل» لا يُحفظ.

### 3. لا ألوان مكتوبة يدوياً

كل لون متغيّر في `styles/tokens.css`. استخدم `var(--primary)`، `var(--urgent)` …
لا `#0e6e63`. بهذا يعمل الوضع الداكن تلقائياً.

البرتقالي (`--urgent`) مخصّص لشيء واحد: ما يحتاج تدخّل إنسان (تحليل حرج، حالة لم يحضر).
إذا ظهر في الزينة يفقد معناه حيث يهم.

### 4. الصلاحيات في الواجهة للعرض فقط

`permissions.view_clinical` وأخواتها تقرر **ما يُرسم**، لا **ما يُسمح به**. الخادم يعيد
التحقق من كل طلب؛ من يغيّر هذه القيم في المتصفح يحصل على 403، لا على البيانات.
إخفاء زر مجاملة، وليس حماية. **لا تعتمد على الواجهة لمنع أي شيء.**

### 5. المعرّفات دائماً UUID

لا أرقام متسلسلة في أي رابط أو طلب. `/patients/<uuid>`، و`row.uuid` في كل مكان.

### 6. لا `tenant` في أي طلب

الخادم يحدد العيادة من المستخدم المسجّل. لا ترسل حقل `tenant` ولا تقرأه — الـ serializers
لا تحتوي عليه أصلاً.

### 7. الملفات الطبية لا تُعرض برابط مباشر

المستندات خارج مجلد الويب. التنزيل عبر `api.attachments.download(uuid, name)` فقط، وهو
طلب مُصرّح به. أي `<a href>` مباشر لملف مريض يتجاوز كل الصلاحيات.

### 8. الأرقام بأرقام لاتينية، والهواتف `dir="ltr"`

`formatMoney`، `formatDate` … من `lib/format.js`. الأرقام لاتينية لأن العيادات المصرية
تقرأ الإيصالات هكذا. رقم الهاتف داخل نص عربي يُعاد ترتيبه بدون `dir="ltr"` فلا يمكن
الاتصال به.

---

## إضافة شاشة جديدة

### قائمة بسيطة (اسم ووصف ونحوه)

ملف واحد، بلا markup:

```jsx
import { api } from '@/api'
import { CrudPage } from '@/components/data/CrudPage'

export function RoomListPage() {
  return (
    <CrudPage
      title="الغرف"
      resource={api.rooms}
      createLabel="إضافة غرفة"
      columns={[{ key: 'name', header: 'الغرفة' }]}
      fields={[{ name: 'name', label: 'اسم الغرفة', required: true }]}
    />
  )
}
```

`CrudPage` يتكفّل بالبحث، والترقيم، والحالات الفارغة والخطأ، ونافذة الإضافة/التعديل،
وأخطاء الحقول من الخادم، وتأكيد الحذف.

أنواع الحقول: `text` `textarea` `number` `money` `date` `datetime` `select`
`relation` `checkbox` `file` `email` `tel` `password`.

### شاشة لها سلوك خاص

اكتبها صراحة، مستخدماً `ResourceTable` و`FormFields` و`useMutation`. انظر
`features/clinical/LabResultListPage.jsx` (زر «تسجيل الاطلاع») أو
`PrescriptionListPage.jsx` (أسطر الأدوية المتداخلة). لا تُجبر شاشة معقّدة على المرور
عبر `CrudPage` — هكذا يصبح المكون العام غير مقروء.

### ثم

1. أضف المورد في `src/api/index.js` إن كان جديداً: `export const rooms = createResource('rooms')`
2. أضف الشاشة في `src/routes.jsx`، مع `permission` إن لزم.
3. أضف الرابط في `components/layout/Sidebar.jsx`.
4. في الباك إند: viewset في `api/views/` يرث `ClinicViewSet`، وسطر في `api/urls.py`،
   **واختبار عزل** في `api/tests/` — أن عيادة أخرى تحصل على 404.

---

## البناء والنشر

```bash
cd frontend
npm ci
npm run build          # → frontend/dist/spa/
git add dist && git commit
```

**`dist/` يُرفع على git عمداً.** استضافة cPanel المشتركة لا تضمن وجود Node على
الخادم، فالنشر يبقى كما هو: `git pull` ثم `collectstatic`. Django يضيف
`frontend/dist` إلى `STATICFILES_DIRS`، فيجمع الملفات مع باقي الملفات الثابتة.

**أعد البناء بعد أي تغيير في `src/` وارفع `dist/` معه.** بناء قديم يعني أن الخادم يعرض
الواجهة القديمة.

`index.html` يُخدَم من Django (`api/spa.py`) بـ `Cache-Control: no-store`، لأنه يسمّي
ملفات الإصدار الحالي المُجزّأة؛ أما ملفات `assets/` فأسماؤها تتغير مع كل بناء فيمكن
تخزينها للأبد.

الحجم: التطبيق الأساسي ~30 ك.ب، React ~164 ك.ب (مخزّن منفصلاً)، وكل شاشة تُحمَّل
عند فتحها فقط (0.3–5 ك.ب لكل منها). موظف الاستقبال لا يحمّل شاشات الأطباء أبداً.

---

## الشاشات القديمة

قوالب Django ما زالت تعمل على روابطها (`/patients/`، `/appointments/` …). التطبيق
الجديد على `/app/`. يمكن الانتقال شاشة بشاشة، ولا يتعطل شيء أثناء ذلك.
