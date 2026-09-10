import { Component } from 'react'

import { ErrorState } from '@/components/ui'

/**
 * The last line: a render error shows a message and a way back instead of a
 * blank white page — which, at a front desk, reads as "the system is down".
 * Also catches a lazy screen whose chunk failed to load after a deploy, which
 * a reload fixes.
 */
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('Unhandled render error', error, info)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <ErrorState
        title="حدث خطأ في عرض الصفحة"
        error="أعد تحميل الصفحة. إذا تكرر الخطأ، أبلغ مدير النظام."
        onRetry={() => window.location.reload()}
      />
    )
  }
}
