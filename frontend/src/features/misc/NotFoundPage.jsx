import { Link } from 'react-router-dom'

import { EmptyState } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDebounce'

export function NotFoundPage() {
  useDocumentTitle('الصفحة غير موجودة')
  return (
    <EmptyState
      icon="🧭"
      title="الصفحة غير موجودة"
      message="ربما تغيّر الرابط أو لم يعد هذا السجل متاحاً لك."
      action={<Link to="/">العودة للرئيسية</Link>}
    />
  )
}
