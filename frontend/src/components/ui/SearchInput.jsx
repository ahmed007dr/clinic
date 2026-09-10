import { Input } from './Input'

/**
 * A search box with a clear button.
 *
 * `type="search"` rather than `text` so mobile keyboards show a search key and
 * the browser offers previous queries. The clear button is explicit because
 * the native one is invisible in several engines and absent in Firefox, and a
 * filter a user cannot see how to remove is a list that looks broken.
 */
export function SearchInput({
  value,
  onChange,
  placeholder = 'بحث…',
  autoFocus = false,
  className = '',
  ...rest
}) {
  return (
    <div className={`ui-search ${className}`}>
      <Input
        type="search"
        className="ui-search__input"
        value={value}
        placeholder={placeholder}
        autoFocus={autoFocus}
        onChange={(event) => onChange(event.target.value)}
        aria-label={placeholder}
        {...rest}
      />
      {value && (
        <button
          type="button"
          className="ui-search__clear"
          onClick={() => onChange('')}
          aria-label="مسح البحث"
        >
          ✕
        </button>
      )}
    </div>
  )
}
