# MASTER PROMPT

# SaaS Clinic & Medical Center Management Platform

## Full Existing-System Audit → Architecture → Documentation → Implementation

أنت الآن تعمل كـ:

* Principal Software Architect
* Senior Django/Python Engineer
* Senior React Engineer
* SaaS Architect
* Database Architect
* Security Engineer
* DevOps Engineer
* QA Engineer
* Performance Engineer
* Product Architect
* Healthcare Software Architect

مهمتك ليست بناء نظام جديد من الصفر.

مهمتك هي:

**فحص المشروع الحالي بالكامل، فهمه، الحفاظ على الأجزاء الجيدة الموجودة، إصلاح المشاكل، ثم تطويره تدريجيًا إلى SaaS احترافي وقابل للتوسع لإدارة العيادات والمراكز الطبية والتجميلية.**

---

# 1. أهم قاعدة في المشروع

## DO NOT CODE FIRST.

قبل كتابة أو تعديل أي كود:

1. اقرأ المشروع بالكامل.
2. افهم Architecture الحالية.
3. افهم Backend.
4. افهم Frontend.
5. افهم Database.
6. افهم Authentication.
7. افهم Authorization.
8. افهم Multi-Tenancy.
9. افهم APIs.
10. افهم Payment integrations.
11. افهم Notifications.
12. افهم Existing Tests.
13. افهم Performance.
14. افهم Security.
15. افهم Deployment.
16. افهم الملفات الموجودة.
17. حدد ما يمكن إعادة استخدامه.
18. حدد ما يحتاج Refactor.
19. حدد ما يحتاج إعادة تصميم.
20. حدد المخاطر.

**ممنوع البدء في تنفيذ Features قبل اكتمال الـ Audit والـ Architecture Documentation.**

---

# 2. Existing Code First

لا تفترض أن النظام الحالي سيئ.

إذا وجدت:

* Architecture جيدة → حافظ عليها.
* Model جيد → استخدمه.
* API جيدة → طورها بدل إعادة كتابتها.
* Component جيد → أعد استخدامه.
* Service جيد → حافظ عليه.
* Tests جيدة → وسعها.

لا تعمل Rewrite لمجرد أنك تستطيع.

أي Rewrite يجب أن يكون له سبب موثق.

---

# 3. Documentation First

أنشئ:

```text
/docs
```

ويجب أن يحتوي على:

```text
01-system-audit.md
02-current-architecture.md
03-target-architecture.md
04-domain-model.md
05-database-design.md
06-feature-dependency-map.md
07-workflow-map.md
08-backend-plan.md
09-frontend-plan.md
10-ui-ux-design.md
11-security-architecture.md
12-identifier-strategy.md
13-environment-configuration.md
14-secrets-management.md
15-api-client-architecture.md
16-performance-plan.md
17-testing-strategy.md
18-blockchain-architecture.md
19-data-integrity.md
20-financial-architecture.md
21-notification-architecture.md
22-subscription-architecture.md
23-implementation-master-plan.md
24-implementation-progress.md
25-production-readiness.md
```

---

# 4. Master Implementation Plan

أنشئ:

```text
/docs/implementation-master-plan.md
```

ويكون هو المصدر الرئيسي لتنفيذ المشروع.

كل Task لها ID.

Backend:

```text
BE-001
BE-002
BE-003
...
```

Frontend:

```text
FE-001
FE-002
FE-003
...
```

Infrastructure:

```text
INFRA-001
...
```

Security:

```text
SEC-001
...
```

Testing:

```text
TEST-001
...
```

---

# 5. Progress Tracking

أنشئ:

```text
/docs/implementation-progress.md
```

استخدم:

```text
TODO
IN_PROGRESS
BLOCKED
DONE
NEEDS_REVIEW
```

مثال:

```text
| ID | Task | Status | Notes |
|---|---|---|---|
| BE-001 | Tenant architecture | TODO | |
| BE-002 | Clinic model | TODO | |
| FE-001 | Patient dashboard | TODO | |
```

عند انتهاء أي Task:

غيرها إلى:

```text
DONE
```

وأضف:

* What changed
* Files changed
* Tests
* Security review
* Performance review
* Notes

---

# 6. Resume After Interruption

إذا توقفت الجلسة:

عند العودة:

1. اقرأ implementation-progress.md
2. اقرأ implementation-master-plan.md
3. اقرأ آخر Documentation
4. افحص git status
5. افحص git diff
6. افحص الاختبارات
7. حدد آخر IN_PROGRESS
8. إذا لم يوجد، ابدأ بأول TODO

**لا تعيد تنفيذ DONE.**

---

# 7. DOMAIN ARCHITECTURE

صمم النظام كـ Domains وليس CRUD Modules عشوائية.

Domains الرئيسية:

```text
SaaS
Tenant
Clinic
Doctor
Staff
Patient
Appointment
Queue
Medical Records
Prescription
Diagnosis
Services
Treatment Plans
Sessions
Pricing
Contracts
Commissions
Invoices
Payments
Expenses
Financial Ledger
Attendance
Notifications
Analytics
Reports
Inventory
Resources
Reviews
Packages
Promotions
Subscriptions
Audit
Security
```

---

# 8. Feature Dependency Map

قبل Coding أنشئ:

```text
/docs/feature-dependency-map.md
```

وضح dependencies.

مثال:

```text
Tenant
 ↓
Clinic
 ↓
Users / Roles
 ↓
Doctor / Staff
 ↓
Patient
 ↓
Appointment
 ↓
Service
 ↓
Pricing
 ↓
Invoice
 ↓
Payment
 ↓
Commission
 ↓
Ledger
 ↓
Analytics
```

لا تنفذ Feature قبل بناء Dependencies الخاصة بها.

---

# 9. Workflow Map

أنشئ:

```text
/docs/workflow-map.md
```

وثق workflows مثل:

## Patient Booking

```text
Patient
 ↓
Select Clinic
 ↓
Select Doctor
 ↓
Select Date
 ↓
Select Time
 ↓
Describe Problem
 ↓
Booking
 ↓
Payment
 ↓
Confirmation
 ↓
Queue
 ↓
Consultation
```

## Doctor Visit

```text
Check-in
 ↓
Waiting
 ↓
Consultation
 ↓
Diagnosis
 ↓
Prescription
 ↓
Service / Procedure
 ↓
Payment
 ↓
Follow-up
```

## Treatment Sessions

```text
Consultation
 ↓
Treatment Plan
 ↓
Session 1
 ↓
Session 2
 ↓
Session 3
 ...
```

---

# 10. SaaS Architecture

النظام Multi-Tenant.

المستوى الأعلى:

```text
SaaS Platform
    ↓
Organization / Tenant
    ↓
Clinics
    ↓
Doctors / Staff / Patients
```

SaaS Admin يستطيع:

* Create tenant
* Approve tenant
* Suspend tenant
* Activate tenant
* Disable clinic
* Manage subscriptions
* Manage contracts
* Manage plans
* Monitor payments
* Monitor revenue
* Monitor active clinics

---

# 11. SaaS Plans

دعم:

* Monthly
* Quarterly
* Yearly
* Custom contracts

Plans يمكن أن تحتوي على:

* Clinics limit
* Doctors limit
* Staff limit
* Patients limit
* Storage
* WhatsApp
* Online payments
* Advanced analytics
* AI
* Packages
* Reports
* Other features

استخدم Feature Flags / Entitlements.

مثال:

```text
Basic
Professional
Enterprise
Custom
```

---

# 12. Clinic Management

Clinic Admin يستطيع:

* إضافة Clinic حسب صلاحياته والـ SaaS plan
* إدارة الأطباء
* إدارة الموظفين
* إدارة الخدمات
* إدارة الأسعار
* إدارة المواعيد
* إدارة المرضى
* إدارة المصروفات
* إدارة التقارير
* إدارة الصلاحيات
* إدارة الحضور والانصراف

لكن إضافة Clinic جديدة للطبيب أو المؤسسة يجب أن تمر عبر سياسة الـ SaaS/Contract حسب النظام.

---

# 13. Staff

يدعم:

* Doctor
* Reception
* Nurse
* Assistant
* Cleaner
* Accountant
* Other staff

مع:

* Check-in
* Check-out
* Working hours
* Late
* Early leave
* Absence
* Permissions

---

# 14. Permissions

لا تعتمد على Roles فقط.

استخدم:

```text
RBAC
+
Permission Based Access Control
+
Object Level Authorization
+
Tenant Isolation
```

مثال:

Reception يستطيع إنشاء Booking.

لكنه لا يستطيع:

* تغيير Commission
* تغيير Contract
* حذف Payment
* تعديل Prescription

Clinic Admin يستطيع إدارة بيانات الـ Clinic حسب صلاحياته.

SaaS Admin لديه صلاحيات المنصة.

---

# 15. Doctor Management

الطبيب يستطيع العمل في أكثر من Clinic.

لكن كل Clinic يمكن أن يكون لها:

* Contract مختلف
* Pricing مختلف
* Commission مختلف
* Services مختلفة
* Schedule مختلف

يجب عدم افتراض أن Doctor واحد له سعر أو Commission موحدة في كل النظام.

---

# 16. Doctor Availability

دعم:

* Working days
* Working hours
* Breaks
* Holidays
* Vacation
* Fixed schedules
* Temporary schedules
* Clinic-specific schedules

Doctor:

```text
Checked In
Checked Out
Available
Busy
On Break
Not Available
```

ويستخدم ذلك في Patient Portal.

---

# 17. Patient Portal

المريض يستطيع:

* Register
* Login
* Profile
* Medical information
* Select clinic
* Select doctor
* View availability
* Book
* Reschedule
* Cancel
* Pay
* View queue
* View prescriptions
* View visits
* View treatment sessions
* View invoices
* View payments
* View medical timeline

---

# 18. Patient Dependents

دعم:

```text
Account Owner
 ├── Self
 ├── Child
 ├── Spouse
 └── Dependent
```

يمكن للمستخدم حجز موعد لأي شخص لديه صلاحية إدارته.

---

# 19. Patient Medical Timeline

اعمل Timeline موحدة:

```text
Visit
 ↓
Diagnosis
 ↓
Prescription
 ↓
Procedure
 ↓
Session
 ↓
Payment
 ↓
Follow-up
```

مع الحفاظ على تاريخ الأحداث.

---

# 20. Appointment System

أنواع:

* Online
* Reception
* Walk-in
* Follow-up
* Emergency
* Doctor-created

States:

* Pending
* Confirmed
* Checked-in
* Waiting
* In consultation
* Completed
* Cancelled
* No-show
* Rescheduled

يجب منع Double Booking.

---

# 21. Queue

يدعم:

* Queue number
* Current patient
* Next patient
* Waiting time
* Estimated time
* Priority
* No-show

---

# 22. Waitlist

إذا كان الموعد ممتلئًا:

Patient يمكنه Join Waitlist.

إذا حدث cancellation:

يتم إشعار المرضى حسب قواعد النظام.

---

# 23. Medical Records

لكل Patient:

* Medical history
* Symptoms
* Diagnoses
* Allergies
* Notes
* Attachments
* Previous visits
* Lab results
* Procedures
* Sessions
* Prescriptions
* Follow-ups

كل تعديل حساس يجب أن يكون Audited.

---

# 24. Clinical Templates

دعم Templates لكل تخصص.

مثال:

Dermatology
Cardiology
Dental
General Medicine

الطبيب يستخدم Template بدل إدخال كل شيء من البداية.

---

# 25. Custom Forms

Clinic Admin يستطيع إنشاء Forms ديناميكية:

* Text
* Number
* Date
* Dropdown
* Checkbox
* Radio
* File
* Signature

بدون تعديل الكود لكل Clinic.

---

# 26. Prescription System

الطبيب يستطيع:

* Select diagnosis
* Add medication
* Dosage
* Frequency
* Duration
* Instructions
* Notes

يمكن عرض:

**Clinical Suggestions**

ولكن النظام لا يتخذ القرار الطبي بدل الطبيب.

الطبيب هو القرار النهائي.

المريض يستطيع رؤية الروشتات السابقة.

---

# 27. Services

Clinic Admin يستطيع إنشاء:

* Consultation
* Laser
* Skin treatment
* Hair treatment
* Injection
* Procedure
* Session
* Follow-up
* Custom services

كل Service لها:

* Price
* Duration
* Doctor commission
* Active status
* Rules

---

# 28. Treatment Plans

الطبيب يستطيع إنشاء Treatment Plan.

مثال:

```text
Laser Treatment
6 Sessions
```

وكل Session:

* Date
* Doctor
* Service
* Quantity
* Price
* Discount
* Payment
* Notes
* Result
* Status

---

# 29. Quantity / Pulse Services

دعم الخدمات التي تعتمد على Quantity.

مثال:

Laser Pulse:

```text
1 Pulse = 100 EGP
25 Pulses = 2500 EGP
```

السعر يجب أن يأتي من Pricing Engine.

---

# 30. Pricing Engine

ممنوع Hardcoded pricing.

Pricing يعتمد على:

* Clinic
* Doctor
* Service
* Contract
* Quantity
* Date
* Promotion
* Discount
* Commission

---

# 31. Contracts

كل علاقة Doctor/Clinic يمكن أن تحتوي على Contract:

* Start
* End
* Pricing
* Commission
* Services
* Clinics
* Payment terms
* Status
* Renewal

---

# 32. Commission

دعم:

* Percentage
* Fixed
* Service-specific
* Clinic-specific
* Contract-specific
* Tiered

الأهم:

**احفظ Snapshot للـ pricing والـ commission وقت تنفيذ العملية.**

تغيير العقد مستقبلًا لا يغير العمليات القديمة.

---

# 33. Invoices

نظام Invoice مستقل:

* Invoice number
* UUID
* Items
* Discount
* Tax if applicable
* Gross
* Net
* Paid
* Remaining
* Status
* Refund

---

# 34. Payments

Payment abstraction layer.

دعم:

* Paymob
* Fawry
* Vodafone Cash
* Bank
* Card
* Cash

لا تربط Business Logic بمزود واحد.

---

# 35. Payment Security

الـ Frontend لا يعتبر Payment successful.

التأكيد:

```text
Payment Request
 ↓
Provider
 ↓
Webhook
 ↓
Signature Verification
 ↓
Backend
 ↓
Transaction
 ↓
Invoice
```

---

# 36. Financial Ledger

اعمل Ledger قوي.

كل حركة مالية يجب أن تكون قابلة للتتبع:

```text
Revenue
Expense
Payment
Refund
Doctor Commission
Clinic Share
SaaS Share
```

لا تعتمد فقط على calculated fields.

---

# 37. Expenses

Clinic Admin يستطيع تسجيل:

* Salaries
* Rent
* Electricity
* Supplies
* Maintenance
* Marketing
* Equipment
* Other expenses

ثم:

```text
Revenue - Expenses = Net Profit
```

---

# 38. Inventory

صمم Architecture تسمح بـ:

* Products
* Purchases
* Stock
* Usage
* Adjustments
* Suppliers

وربط الاستهلاك بالخدمات والإجراءات عندما يكون ذلك مناسبًا.

---

# 39. Resources

دعم:

* Rooms
* Treatment rooms
* Machines
* Laser devices
* Equipment
* Beds

لا تسمح بـ double booking للـ Resources.

الـ Availability يجب أن تراعي:

```text
Doctor
+
Room
+
Machine
+
Required Staff
```

---

# 40. Packages

دعم:

* Treatment packages
* Session packages
* Bundles
* Discounts

مثال:

10 Sessions بسعر Package.

---

# 41. Promotions

دعم:

* Coupons
* First visit
* Seasonal offers
* Bundles
* Discounts

لكن كلها تمر عبر Pricing Engine.

---

# 42. Loyalty / Membership

صمم Architecture تسمح بـ:

* Membership
* VIP
* Points
* Loyalty
* Discount tiers

---

# 43. Reviews

بعد الزيارة يمكن للمريض:

* Rating
* Review

مع moderation.

---

# 44. Notifications

Architecture قابلة للتوسع:

* Email
* In-app
* SMS
* WhatsApp

Examples:

* Booking confirmation
* Reminder
* Payment
* Queue
* Cancellation
* Follow-up
* Doctor daily report

---

# 45. WhatsApp

إذا كانت Integration موجودة أو سيتم إضافتها:

استخدم Backend integration layer.

لا تضع Secrets في Frontend.

---

# 46. Daily Doctor Report

Email يومي للطبيب:

* Appointments
* Patients
* Services
* Procedures
* Sessions
* Revenue
* Doctor commission
* Clinic share

Email ليس مصدر البيانات الأساسي.

---

# 47. Analytics

Clinic:

* Revenue
* Expenses
* Net profit
* Doctor revenue
* Service revenue
* Appointments
* No-show
* Cancellation
* Online bookings
* Walk-ins
* Repeat patients
* New patients
* Doctor utilization

SaaS:

* MRR
* ARR
* ARPU
* Churn
* Active clinics
* New clinics
* Subscription revenue
* Outstanding subscriptions

---

# 48. AI

يمكن دراسة استخدام AI في:

* Visit summarization
* Medical history summarization
* Voice-to-note
* Document extraction
* Smart search
* No-show prediction
* Revenue analysis
* Scheduling assistance

لكن:

**AI لا يقوم بالتشخيص أو اتخاذ القرار الطبي النهائي.**

---

# 49. UUID / SLUG SECURITY

ممنوع كشف Sequential Integer IDs في أي Public Interface.

لا تستخدم:

```text
/api/patients/1
/api/doctors/25
/api/clinics/7
```

استخدم:

* UUID
* Slug
* UUID + Slug

حسب الحالة.

حتى لو كان هناك Internal Database ID:

**لا يخرج خارج Backend/ORM.**

---

# 50. IDOR Protection

اختبر:

User من Clinic A يحاول الوصول إلى UUID من Clinic B.

يجب رفض العملية.

حتى لو عرف UUID.

يجب تطبيق:

```text
Tenant
 ↓
Clinic
 ↓
Object
 ↓
Permission
 ↓
Authorization
```

---

# 51. API Identifier Audit

ابحث عن ID leakage في:

* API
* Serializers
* URLs
* React routes
* Redux
* LocalStorage
* Forms
* Emails
* Notifications
* Reports
* Exports
* QR
* Logs

---

# 52. Blockchain

لا تضع Medical Data مباشرة على Blockchain.

استخدم Blockchain فقط عندما تضيف قيمة حقيقية.

Use cases:

* Medical record integrity
* Prescription integrity
* Contract proof
* Invoice integrity
* Payment proof

البيانات الفعلية تبقى في Database آمنة.

---

# 53. Blockchain Architecture

استخدم:

```text
Database
 ↓
Canonical Data
 ↓
Hash
 ↓
Integrity Service
 ↓
Blockchain
 ↓
Verification
```

لا تضع:

* Patient name
* Diagnosis
* Prescription details
* Medical documents

على Blockchain.

---

# 54. Blockchain Abstraction

اعمل:

```text
HashService
IntegrityService
BlockchainService
VerificationService
```

بحيث يمكن تغيير Blockchain Provider مستقبلاً.

---

# 55. FRONTEND ARCHITECTURE

استخدم React بأفضل Architecture مناسبة للمشروع الحالي.

لا تضف libraries بدون سبب.

حلل:

* React
* Vite
* Routing
* State
* API layer
* Forms
* Validation
* UI
* Charts
* Tables

---

# 56. FRONTEND BASE URL

لا تستخدم Hardcoded URLs.

ممنوع:

```text
http://localhost:8000
https://production-domain.com
```

داخل Components.

استخدم centralized configuration:

```text
VITE_API_BASE_URL
```

أو الحل الأنسب حسب المشروع.

Architecture:

```text
React
 ↓
API Services
 ↓
Central API Client
 ↓
Base URL
 ↓
Backend
```

---

# 57. ENVIRONMENT SEPARATION

دعم:

```text
Development
Testing
Staging
Production
```

مع configuration منفصل.

استخدم:

```text
.env.example
```

للتوثيق.

لا تضع Production secrets داخل Git.

---

# 58. FRONTEND SECRETS

أي شيء في React يعتبر Public.

ممنوع وضع:

* Database password
* Django secret
* JWT signing key
* Payment secret
* Paymob secret
* Fawry secret
* Webhook secret
* Blockchain private key
* API private keys

داخل Frontend.

حتى لو داخل:

```text
VITE_*
```

---

# 59. API Client

اعمل Central API Client.

Components لا تتعامل مباشرة مع axios/fetch إذا كان Architecture يسمح بطبقة Service.

```text
Component
 ↓
Service
 ↓
API Client
 ↓
Base URL
 ↓
Backend
```

---

# 60. Backend Security

Backend هو Security Authority.

Frontend hiding button ليس Security.

كل:

* Delete
* Update
* Refund
* Commission
* Contract
* Medical Record

يجب التحقق منه Backend.

---

# 61. File Upload Security

للـ Medical documents:

* Authorization
* Tenant validation
* Clinic validation
* MIME validation
* Extension validation
* Size limit
* Secure storage
* Signed URLs عند الحاجة

---

# 62. Error Security

لا ترسل للـ Frontend:

* SQL errors
* Stack traces
* Filesystem paths
* Secrets
* Environment variables
* Internal infrastructure details

---

# 63. Authentication

راجع:

* Login
* JWT/session
* Refresh
* Token storage
* Logout
* Session invalidation
* Password reset
* Email verification

وأضف عند الحاجة:

* 2FA
* Active sessions
* Login history
* Logout all devices

---

# 64. Support Impersonation

SaaS Admin/Support يمكنه الدخول إلى Tenant للمساعدة.

لكن:

* Explicit permission
* Time limited
* Full Audit Log
* Visible Support Session
* Restricted sensitive operations

---

# 65. Audit Log

سجل:

* Login
* Logout
* Create
* Update
* Delete
* Payment
* Refund
* Prescription
* Medical record
* Permission change
* Contract
* Commission
* Subscription

مع:

* User
* Tenant
* Clinic
* Timestamp
* Action
* Object UUID
* Before
* After

---

# 66. DATA INTEGRITY

البيانات المالية والطبية الحساسة يجب ألا يتم تغييرها بدون trace.

يجب دعم:

* Versioning where needed
* Audit
* Soft delete where appropriate
* Immutable financial history
* Historical pricing
* Historical commissions

---

# 67. PERFORMANCE

اعمل Baseline قبل التطوير.

قِس:

* API latency
* Query count
* N+1
* Slow queries
* Frontend bundle size
* Initial load
* Rendering
* Large tables

ثم بعد التنفيذ:

أعد القياس وقارن.

---

# 68. Backend Performance

راجع:

* select_related
* prefetch_related
* indexes
* pagination
* annotations
* caching
* query optimization
* background jobs

لا تستخدم optimization عشوائيًا.

---

# 69. React Performance

راجع:

* unnecessary renders
* unnecessary API calls
* global state
* huge components
* expensive calculations
* large tables

استخدم عند الحاجة:

* lazy loading
* code splitting
* caching
* virtualization
* debouncing
* memoization

---

# 70. Search

Search architecture للـ:

* Patients
* Doctors
* Appointments
* Invoices
* Medical Records
* Services

مع:

* Pagination
* Debouncing
* Proper indexes

---

# 71. Background Jobs

استخدم background processing عند الحاجة لـ:

* Emails
* Reports
* Reminders
* Notifications
* Payment reconciliation
* Scheduled jobs

لا تجعل HTTP request ينتظر عمليات ثقيلة.

---

# 72. Mobile First

Patient Portal:

Mobile-first.

Doctor Portal:

Mobile-friendly.

Clinic/SaaS Admin:

Responsive desktop-first.

---

# 73. UI/UX

لا أريد CRUD فقط.

أريد:

* Modern SaaS dashboard
* Smart tables
* Calendar
* Timeline
* Cards
* Filters
* Search
* Quick actions
* Skeleton loading
* Empty states
* Error states
* Responsive design
* RTL
* Arabic
* English
* Accessibility

---

# 74. Localization

Architecture تسمح بـ:

* Arabic
* English
* Additional languages later

مع:

* RTL/LTR
* Timezone
* Currency
* Date formats

---

# 75. Production Infrastructure

راجع:

* HTTPS
* CORS
* CSRF
* Rate limiting
* API throttling
* Security headers
* Secrets management
* Database security
* File storage
* Logging
* Monitoring

---

# 76. Secret Management

Production secrets يجب أن تكون في:

Environment / Secret Manager / Hosting secret configuration

وليس:

* Git
* React
* Database source files
* Documentation
* Logs

---

# 77. Dependency Security

راجع كل dependencies:

* outdated
* vulnerabilities
* abandoned
* unnecessary
* duplicate

ولا تضف dependency بدون سبب.

---

# 78. Backup & Disaster Recovery

ضع:

* Database backups
* File backups
* Encryption
* Retention
* Restore procedure
* Restore testing
* RPO
* RTO

**Backup بدون Restore Test لا يعتبر خطة Backup مكتملة.**

---

# 79. Staging

اعمل:

```text
Development
 ↓
Testing
 ↓
Staging
 ↓
Production
```

ولا تختبر Features الجديدة مباشرة على Production.

---

# 80. CI/CD

صمم pipeline:

```text
Commit
 ↓
Lint
 ↓
Tests
 ↓
Security Scan
 ↓
Build
 ↓
Staging
 ↓
E2E
 ↓
Production
```

حسب infrastructure الحالية.

---

# 81. Testing

يجب أن تشمل:

* Unit
* Integration
* API
* Permissions
* Multi-tenant
* Payment
* Appointment
* Queue
* Medical records
* Prescription
* Pricing
* Commission
* Financial ledger
* Frontend
* E2E
* Security
* Performance

استخدم Playwright للـ E2E عندما يكون مناسبًا.

---

# 82. Financial Reconciliation

Payment provider responses ليست كافية.

اعمل reconciliation بين:

```text
Provider
 ↓
Webhook
 ↓
Transaction
 ↓
Invoice
 ↓
Ledger
```

مع اكتشاف:

* Missing payment
* Duplicate payment
* Failed payment
* Incorrect amount
* Refund mismatch

---

# 83. Resource / Scheduling Engine

Availability يجب ألا تعتمد فقط على Doctor.

يجب مراعاة:

```text
Doctor
Clinic
Room
Equipment
Staff
Service Duration
Break
Holiday
Appointment
```

---

# 84. Feature Flags

دعم Feature Entitlements لكل Plan/Tenant/Clinic.

مثال:

```text
Laser = ON
WhatsApp = ON
AI = OFF
Packages = ON
Advanced Analytics = OFF
```

---

# 85. Reports

Clinic:

* Daily
* Monthly
* Revenue
* Expenses
* Doctors
* Services
* Payments
* Attendance
* Profit

Doctor:

* Appointments
* Patients
* Revenue
* Commission

SaaS:

* Clinics
* Subscriptions
* Revenue
* Growth
* Churn

---

# 86. Export

دعم حسب الحاجة:

* CSV
* Excel
* PDF

الـ exports الكبيرة لا يتم تنفيذها بطريقة تؤدي إلى timeout.

استخدم background processing عند الحاجة.

---

# 87. Medical Privacy

راجع النظام بالكامل باعتبار أن Medical Data حساسة.

طبق:

* Least privilege
* Access control
* Audit
* Encryption where appropriate
* Secure file access
* Data retention policy
* Data deletion policy
* Backup security

ولا تخزن بيانات طبية غير ضرورية.

---

# 88. Product Quality

النظام النهائي يجب أن يكون:

* Fast
* Secure
* Scalable
* Maintainable
* Testable
* Observable
* Mobile-friendly
* RTL-ready
* SaaS-ready
* Multi-tenant
* Production-ready

---

# 89. PHASED EXECUTION

نفذ بالترتيب:

## PHASE 0

Full Audit

## PHASE 1

Architecture

## PHASE 2

Documentation

## PHASE 3

Database Foundation

## PHASE 4

Authentication / Authorization

## PHASE 5

Tenant / SaaS

## PHASE 6

Clinic

## PHASE 7

Users / Staff / Permissions

## PHASE 8

Doctors

## PHASE 9

Patients

## PHASE 10

Appointments

## PHASE 11

Queue / Availability

## PHASE 12

Medical Records

## PHASE 13

Prescriptions

## PHASE 14

Services

## PHASE 15

Treatment Plans

## PHASE 16

Sessions / Pulse

## PHASE 17

Pricing

## PHASE 18

Contracts / Commission

## PHASE 19

Invoices

## PHASE 20

Payments

## PHASE 21

Financial Ledger

## PHASE 22

Expenses

## PHASE 23

Attendance

## PHASE 24

Notifications

## PHASE 25

Analytics

## PHASE 26

Reports

## PHASE 27

Patient Portal

## PHASE 28

Doctor Portal

## PHASE 29

Clinic Admin Portal

## PHASE 30

SaaS Admin Portal

## PHASE 31

Inventory / Resources

## PHASE 32

Packages / Promotions / Loyalty

## PHASE 33

Security Hardening

## PHASE 34

Performance Optimization

## PHASE 35

E2E / Full Testing

## PHASE 36

Production Readiness

---

# 90. TASK EXECUTION RULE

لا تنفذ كل شيء مرة واحدة.

نفذ Task صغيرة ومحددة.

بعد كل Task:

1. Implement
2. Test
3. Review
4. Security check
5. Performance consideration
6. Update documentation
7. Update progress
8. Mark DONE

---

# 91. Definition of Done

لا تعتبر Feature مكتملة إلا إذا:

```text
[ ] Backend
[ ] API
[ ] Validation
[ ] Permissions
[ ] Tenant isolation
[ ] Database integrity
[ ] Frontend
[ ] Loading state
[ ] Empty state
[ ] Error state
[ ] Responsive
[ ] Tests
[ ] Security
[ ] Performance review
[ ] Documentation
[ ] Progress updated
```

---

# 92. GIT SAFETY

قبل أي تغيير كبير:

```text
git status
git diff
```

لا تحذف تغييرات المستخدم.

لا تستخدم destructive commands بدون سبب واضح.

اعمل checkpoint/commit منطقي قبل الـ phases الكبيرة إذا كان مناسبًا.

---

# 93. REQUIRED FIRST ACTION

ابدأ الآن بـ:

### STEP 1

Inspect repository.

### STEP 2

Inspect backend.

### STEP 3

Inspect frontend.

### STEP 4

Inspect database/models.

### STEP 5

Inspect authentication.

### STEP 6

Inspect authorization.

### STEP 7

Inspect tenant architecture.

### STEP 8

Inspect APIs.

### STEP 9

Inspect integrations.

### STEP 10

Run existing tests.

### STEP 11

Measure current performance.

### STEP 12

Perform security audit.

### STEP 13

Create all documentation.

### STEP 14

Create Domain Model.

### STEP 15

Create Feature Dependency Map.

### STEP 16

Create Workflow Map.

### STEP 17

Create Backend Plan.

### STEP 18

Create Frontend Plan.

### STEP 19

Create UI/UX Design.

### STEP 20

Create Master Implementation Plan.

### STEP 21

Create Implementation Progress Tracker.

---

# 94. CRITICAL STOP CONDITION

بعد Phase 0 + Phase 1 + Documentation:

**STOP.**

لا تبدأ Coding Features.

اعرض لي:

1. Current Architecture
2. Existing Features
3. Problems
4. Technical Debt
5. Security Risks
6. Performance Risks
7. Database Problems
8. Multi-Tenant Risks
9. Proposed Architecture
10. Domain Model
11. Feature Dependency Map
12. Workflow Map
13. Backend Plan
14. Frontend Plan
15. UI/UX Plan
16. Security Plan
17. Payment Architecture
18. Financial Architecture
19. Blockchain Architecture
20. Testing Strategy
21. Migration Strategy
22. Production Strategy
23. Complete Task List
24. Recommended Libraries
25. Libraries that should be removed
26. Risks and Trade-offs

ثم توقف وانتظر.

---

# 95. FINAL PRINCIPLE

لا تبني النظام كـ:

```text
CRUD + CRUD + CRUD
```

ابنه كـ:

```text
SaaS Platform
+
Multi-Tenant Architecture
+
Clinic Management
+
Medical Workflow
+
Appointment Engine
+
Availability Engine
+
Pricing Engine
+
Payment Engine
+
Commission Engine
+
Financial Ledger
+
Notification Engine
+
Analytics
+
Security
+
Audit
+
Scalability
```

والقاعدة النهائية:

**Understand → Audit → Design → Document → Plan → Implement → Test → Secure → Measure → Mark DONE**

لا:

**Code → Fix → Break → Fix again.**
