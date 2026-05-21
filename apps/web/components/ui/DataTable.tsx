import type { ReactNode } from "react";

type DataTableProps = {
  columns: ReactNode[];
  children: ReactNode;
  empty?: ReactNode;
};

export function DataTable({ columns, children, empty }: DataTableProps) {
  return (
    <div className="table-wrap">
      <table className="t">
        <thead>
          <tr>
            {columns.map((column, index) => (
              <th key={index}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children ?? <tr><td className="t__empty" colSpan={columns.length}>{empty}</td></tr>}</tbody>
      </table>
    </div>
  );
}
