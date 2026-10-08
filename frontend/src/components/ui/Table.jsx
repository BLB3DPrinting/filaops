import { forwardRef } from "react";

const Table = forwardRef(function Table(
  { children, className = "", ...rest },
  ref
) {
  return (
    <div className={`bg-paper rounded-lg border border-hair overflow-hidden shadow-[var(--shadow-pop)] ${className}`}>
      <table ref={ref} className="w-full" {...rest}>
        {children}
      </table>
    </div>
  );
});

const TableHeader = forwardRef(function TableHeader(
  { children, className = "", ...rest },
  ref
) {
  return (
    <thead ref={ref} className={`bg-paper-sunk ${className}`} {...rest}>
      {children}
    </thead>
  );
});

const TableBody = forwardRef(function TableBody(
  { children, className = "", ...rest },
  ref
) {
  return (
    <tbody ref={ref} className={`divide-y divide-hair ${className}`} {...rest}>
      {children}
    </tbody>
  );
});

const TableRow = forwardRef(function TableRow(
  { children, className = "", ...rest },
  ref
) {
  return (
    <tr ref={ref} className={`hover:bg-paper-sunk ${className}`} {...rest}>
      {children}
    </tr>
  );
});

const TableHead = forwardRef(function TableHead(
  { children, className = "", ...rest },
  ref
) {
  return (
    <th
      ref={ref}
      className={`px-4 py-3 text-left text-xs font-medium text-ink-3 uppercase tracking-wider ${className}`}
      {...rest}
    >
      {children}
    </th>
  );
});

const TableCell = forwardRef(function TableCell(
  { children, className = "", ...rest },
  ref
) {
  return (
    <td ref={ref} className={`px-4 py-3 text-ink ${className}`} {...rest}>
      {children}
    </td>
  );
});

const TableEmpty = forwardRef(function TableEmpty(
  { colSpan = 1, children, className = "", ...rest },
  ref
) {
  return (
    <tr ref={ref} {...rest}>
      <td
        colSpan={colSpan}
        className={`px-4 py-8 text-center text-ink-3 ${className}`}
      >
        {children}
      </td>
    </tr>
  );
});

export { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableEmpty };
