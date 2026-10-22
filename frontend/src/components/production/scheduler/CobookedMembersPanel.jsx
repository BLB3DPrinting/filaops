/**
 * CobookedMembersPanel — member list for a co-booked board block (print-batch S4).
 *
 * Several operations booked into one window on one machine draw as ONE block
 * on the Scheduler board; clicking it opens this panel so every member stays
 * reachable. Choosing a member opens the usual scheduler modal for it.
 *
 * Rendered below the Gantt table rather than as a popover: the table sits in
 * an overflow container that would clip an absolutely positioned list.
 */
import { parseDateTime } from "../../../utils/formatting";
import { describeMember } from "./groupOperationBlocks";

const fmt = (d) =>
  d.toLocaleString(undefined, {
    month: "numeric",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });

export default function CobookedMembersPanel({ group, laneCode, onSelect, onClose }) {
  const { members, primary } = group;
  return (
    <div
      data-testid="cobooked-members"
      className="bg-[var(--paper)] border border-[var(--rule-hair)] rounded-xl p-3 shadow-[var(--shadow-pop)]"
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0">
          <div className="text-sm font-medium text-[var(--ink)]">
            Co-booked on {laneCode} · {members.length} operations
          </div>
          <div className="text-xs text-[var(--ink-3)]">
            One run, {fmt(parseDateTime(primary.scheduled_start))} →{" "}
            {fmt(parseDateTime(primary.scheduled_end))}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close member list"
          className="shrink-0 px-2 py-0.5 text-[var(--ink-3)] hover:text-[var(--ink)] text-sm"
        >
          ✕
        </button>
      </div>
      <ul className="space-y-1">
        {members.map((op) => (
          <li key={op.id}>
            <button
              type="button"
              data-testid={`cobooked-member-${op.id}`}
              onClick={() => onSelect(op)}
              className="w-full text-left px-2 py-1.5 bg-[var(--paper-sunk)] border border-[var(--rule-hair)] rounded-lg text-xs text-[var(--ink-2)] hover:text-[var(--ink)]"
            >
              {describeMember(op)}
              <span className="ml-2 text-[10px] text-[var(--ink-4)]">
                {op.operation_name || op.operation_code} · {op.status.replace(/_/g, " ")}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
