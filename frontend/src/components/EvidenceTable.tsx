import { useMemo, useState } from 'react'
import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table'

import { metricLabel } from '../lib/format'
import type { EvidencePage } from '../lib/types'

type Row = Record<string, unknown>

export default function EvidenceTable({ page }: { page: EvidencePage }) {
  const [sorting, setSorting] = useState<SortingState>([])

  const columns = useMemo<ColumnDef<Row>[]>(
    () =>
      page.columns
        .filter((c) => c !== 'row_id')
        .map((key) => ({
          accessorKey: key,
          header: metricLabel(key),
          cell: (info) => {
            const value = info.getValue()
            const text = value === null || value === undefined ? '-' : String(value)
            const isLong = text.length > 60
            return (
              <span
                className={isLong ? 'block max-w-[420px] whitespace-pre-wrap' : 'whitespace-nowrap'}
                title={isLong ? text : undefined}
              >
                {text}
              </span>
            )
          },
        })),
    [page.columns],
  )

  const table = useReactTable({
    data: page.rows as Row[],
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 15 } },
  })

  if (!page.rows.length) {
    return <p className="text-sm text-ink-500">No evidence rows available for this finding.</p>
  }

  return (
    <div>
      {page.note && <p className="mb-2 text-xs text-ink-500">{page.note}</p>}
      <div className="overflow-x-auto rounded-md border border-ink-100">
        <table className="w-full">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((header) => (
                  <th
                    key={header.id}
                    className="th cursor-pointer select-none"
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {{ asc: ' ▲', desc: ' ▼' }[header.column.getIsSorted() as string] ?? ''}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="hover:bg-ink-50/60">
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="td mono">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-ink-500">
        <span>
          Showing {table.getRowModel().rows.length} of {page.rows.length} loaded rows
          {page.total > page.rows.length && ` (${page.total.toLocaleString()} in total)`}
        </span>
        <span className="flex items-center gap-2">
          <button
            className="btn-ghost"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            Previous
          </button>
          <span className="tabular-nums">
            Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()}
          </span>
          <button
            className="btn-ghost"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            Next
          </button>
        </span>
      </div>
    </div>
  )
}
