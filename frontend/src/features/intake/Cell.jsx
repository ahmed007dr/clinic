/** One cell of the shared `.form-grid`; `span={2}` for a full-width field. */
export function Cell({ span = 1, children }) {
  return (
    <div className="form-grid__cell" style={{ gridColumn: `span ${span}` }}>
      {children}
    </div>
  )
}
