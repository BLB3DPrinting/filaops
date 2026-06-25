/**
 * NextActionLane — one axis's worth of next-actions (UX Foundation F4, #808).
 *
 * A lane = an axis (Production / Fulfillment / Payment / ...). The header shows
 * the axis Badge + a count; the body is severity-sorted NextActionCards (the
 * sort happens upstream in mergeByAxis). An empty lane renders a quiet
 * "all clear" line rather than disappearing, so a lane the caller chooses to
 * show never collapses into nothing.
 */
import { Badge } from "../ui";
import NextActionCard from "./NextActionCard";
import { axisLabel, axisTone } from "./axisMeta";

function LaneHeader({ axis, count }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <Badge variant={axisTone(axis)} size="sm">
        {axisLabel(axis)}
      </Badge>
      <span className="text-xs text-gray-500">{count}</span>
    </div>
  );
}

export default function NextActionLane({ axis, actions = [] }) {
  const list = Array.isArray(actions) ? actions : [];

  return (
    <div data-testid={`next-action-lane-${axis}`}>
      <LaneHeader axis={axis} count={list.length} />
      {list.length === 0 ? (
        <p className="text-sm text-gray-500 px-1">Nothing needs attention here.</p>
      ) : (
        <div className="space-y-3">
          {list.map((action, i) => (
            <NextActionCard
              key={`${action.axis}-${action.target?.id ?? i}-${action.verb || action.label}`}
              action={action}
            />
          ))}
        </div>
      )}
    </div>
  );
}
