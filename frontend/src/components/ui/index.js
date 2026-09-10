/**
 * The shared component vocabulary.
 *
 *   import { Button, Card, Table, Modal } from '@/components/ui'
 *
 * One import per screen instead of one per component, and every screen reaches
 * the same pieces — which is what keeps the application looking like one
 * application rather than fifteen. The stylesheet is imported here, once, so a
 * screen can never render a primitive with its styles missing.
 */

import './ui.css'
// Form layout (`.form-grid`, `.form-error`, `.form-actions`) is used by screens
// that never import FormFields — the login page, the prescription modal —
// and screens load lazily, so a stylesheet imported by one component is
// missing from every chunk that does not include it. Loaded here, once, with
// the rest of the shared vocabulary.
import '../form/form.css'

export { Button } from './Button'
export { Field } from './Field'
export { Input, Textarea, Select, Checkbox } from './Input'
export { Card, CardHeader, CardBody } from './Card'
export {
  Badge,
  APPOINTMENT_TONES,
  LAB_TONES,
  LAB_STATUS_TONES,
  PLAN_TONES,
  PROCEDURE_TONES,
  SESSION_TONES,
} from './Badge'
export { Table } from './Table'
export { Pagination } from './Pagination'
export { Modal, ConfirmDialog } from './Modal'
export { Spinner } from './Spinner'
export { Loading, EmptyState, ErrorState, TableSkeleton } from './State'
export { SearchInput } from './SearchInput'
export { Tabs } from './Tabs'
export { Toasts } from './Toasts'
export { Avatar } from './Avatar'
export { StatTile } from './StatTile'
export { BarChart } from './BarChart'
export { DescriptionList } from './DescriptionList'
