import Badge from "./Badge.jsx";
import { getDescriptor } from "../../lib/statusDescriptors.js";

/**
 * Renders a status value as a Badge using the per-axis descriptor registry
 * (UX Foundation, epic #808). The (model, field, value) triple resolves to a
 * consistent label + tone everywhere, replacing per-screen status→color maps.
 *
 * @param {Object} props
 * @param {string} props.model - e.g. 'production_order'
 * @param {string} [props.field='status'] - the status axis (e.g. 'qc_status')
 * @param {string|null|undefined} props.value
 * @param {boolean} [props.dot]
 * @param {'sm'|'md'} [props.size]
 * @param {string} [props.className]
 */
export default function StatusBadge({
  model,
  field = "status",
  value,
  dot = false,
  size,
  className,
}) {
  const { label, tone } = getDescriptor(model, field, value);
  return (
    <Badge variant={tone} dot={dot} size={size} className={className}>
      {label}
    </Badge>
  );
}
