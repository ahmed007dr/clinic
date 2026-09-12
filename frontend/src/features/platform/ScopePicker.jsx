import { api } from '@/api'
import { Select } from '@/components/ui'
import { useAsync } from '@/hooks/useApi'

/**
 * Where a setting belongs: the whole platform, one owner group, or one clinic
 * of a group. `value` is `{ scope, customer, branch }`; `scopes` limits the
 * choice (a mailbox has no platform scope, cPanel has only the platform).
 */
export function ScopePicker({ value, onChange, scopes = ['platform', 'group', 'clinic'] }) {
  const groups = useAsync(() => api.platform.tenants(), [])
  const branches = useAsync(
    () => (value.customer ? api.platform.branches(value.customer) : Promise.resolve([])),
    [value.customer],
  )
  const labels = { platform: 'المنصة كلها', group: 'مجموعة (أونر)', clinic: 'عيادة واحدة' }

  return (
    <div className="scope-picker">
      <Select
        id="scope-level"
        label="المستوى"
        options={scopes.map((scope) => ({ value: scope, label: labels[scope] }))}
        value={value.scope}
        onChange={(event) => onChange({ scope: event.target.value, customer: value.customer, branch: '' })}
      />
      {value.scope !== 'platform' && (
        <Select
          id="scope-group"
          label="المجموعة"
          placeholder={groups.loading ? 'جارٍ التحميل…' : 'اختر المجموعة'}
          options={(groups.data?.results ?? []).map((group) => ({ value: group.uuid, label: group.name }))}
          value={value.customer}
          onChange={(event) => onChange({ ...value, customer: event.target.value, branch: '' })}
        />
      )}
      {value.scope === 'clinic' && (
        <Select
          id="scope-clinic"
          label="العيادة"
          placeholder={!value.customer ? 'اختر المجموعة أولاً' : 'اختر العيادة'}
          options={(branches.data ?? []).map((branch) => ({
            value: String(branch.id),
            label: branch.is_active ? branch.name : `${branch.name} (موقوفة)`,
          }))}
          value={value.branch}
          onChange={(event) => onChange({ ...value, branch: event.target.value })}
          disabled={!value.customer}
        />
      )}
    </div>
  )
}

/** Whether the picker names a complete place yet. */
export function scopeReady(value) {
  if (value.scope === 'platform') return true
  if (value.scope === 'group') return Boolean(value.customer)
  return Boolean(value.customer && value.branch)
}
