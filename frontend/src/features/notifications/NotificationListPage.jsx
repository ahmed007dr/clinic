import { useState } from 'react'

import { api } from '@/api'
import { Badge, Button, Checkbox } from '@/components/ui'
import { ResourceTable } from '@/components/data/ResourceTable'
import { PageHeader } from '@/components/layout/PageHeader'
import { useMutation } from '@/hooks/useApi'
import { useToast } from '@/hooks/useToast'
import { formatDateTime } from '@/lib/format'

const TYPE_TONES = {
  system: 'neutral',
  reminder: 'info',
  warning: 'warn',
  appointment: 'primary',
  payment: 'ok',
}

/**
 * The signed-in user's own notifications.
 *
 * Marking one read is a POST, not a link. The server-rendered screen did it
 * with a plain `<a href>` on a GET (WIRE-009), which meant anything able to
 * make the browser fetch that URL — an image in an email, a prefetch — could
 * change state. The API has no GET that writes.
 */
export function NotificationListPage() {
  const toast = useToast()
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const refresh = () => setRefreshKey((value) => value + 1)

  const markRead = useMutation((uuid) => api.notifications.markRead(uuid))
  const markAll = useMutation(() => api.notifications.markAllRead())

  const columns = [
    {
      key: 'type',
      header: 'النوع',
      render: (row) => <Badge tone={TYPE_TONES[row.type] ?? 'neutral'}>{row.type_label}</Badge>,
    },
    {
      key: 'title',
      header: 'الإشعار',
      render: (row) => (
        <div style={{ opacity: row.is_read ? 0.65 : 1 }}>
          <strong>{row.title}</strong>
          <div className="ui-muted" style={{ fontSize: 'var(--text-sm)' }}>
            {row.message}
          </div>
        </div>
      ),
    },
    { key: 'created_at', header: 'التاريخ', render: (row) => formatDateTime(row.created_at) },
    {
      key: '__actions',
      actions: true,
      render: (row) =>
        row.is_read ? (
          <span className="ui-muted">مقروء</span>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            disabled={markRead.submitting}
            onClick={async () => {
              try {
                await markRead.run(row.uuid)
                refresh()
              } catch (error) {
                toast.error(error.message)
              }
            }}
          >
            تحديد كمقروء
          </Button>
        ),
    },
  ]

  return (
    <>
      <PageHeader
        title="الإشعارات"
        actions={
          <Button
            loading={markAll.submitting}
            onClick={async () => {
              try {
                const result = await markAll.run()
                toast.success(`تم تحديد ${result.updated} إشعار كمقروء`)
                refresh()
              } catch (error) {
                toast.error(error.message)
              }
            }}
          >
            تحديد الكل كمقروء
          </Button>
        }
      />
      <ResourceTable
        resource={api.notifications}
        columns={columns}
        searchable={false}
        refreshKey={refreshKey}
        params={{ unread: unreadOnly ? '1' : undefined }}
        filters={
          <Checkbox
            label="غير المقروءة فقط"
            checked={unreadOnly}
            onChange={(event) => setUnreadOnly(event.target.checked)}
          />
        }
        empty={{ title: 'لا توجد إشعارات', message: 'ستظهر هنا التنبيهات الموجّهة إليك.' }}
      />
    </>
  )
}
