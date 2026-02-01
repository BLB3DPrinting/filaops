/**
 * ReceiveModal - Enhanced receive items workflow
 *
 * Features:
 * - Prominent product SKU and name display
 * - Large, touch-friendly quantity inputs
 * - "Receive All" quick button per line
 * - Running total of items being received
 * - Visual indicators for partial/full receipt
 * - Auto-generate lot number option
 */
import { useState, useMemo } from "react";
import { useToast } from "../Toast";
import Modal from "../Modal";

export default function ReceiveModal({ po, onClose, onReceive }) {
  const toast = useToast();
  const [lines, setLines] = useState(
    po.lines
      ?.filter(
        (l) => parseFloat(l.quantity_received) < parseFloat(l.quantity_ordered)
      )
      .map((l) => ({
        line_id: l.id,
        line_number: l.line_number,
        quantity_to_receive:
          parseFloat(l.quantity_ordered) - parseFloat(l.quantity_received),
        quantity_ordered: parseFloat(l.quantity_ordered),
        quantity_already_received: parseFloat(l.quantity_received),
        remaining:
          parseFloat(l.quantity_ordered) - parseFloat(l.quantity_received),
        product_sku: l.product_sku,
        product_name: l.product_name,
        purchase_unit: l.purchase_unit || l.product_unit || "KG", // Purchase unit (for receive quantities)
        product_unit: l.product_unit || l.purchase_unit || "KG", // Product unit (for display/conversion)
        lot_number: "",
        notes: "",
        // Spool creation fields
        create_spools: false,
        is_material:
          l.product_sku?.startsWith("MAT-") ||
          l.product_unit === "KG" ||
          l.product_unit === "G",
        spools: [
          {
            weight_input: "",
            weight_g: 0,
            supplier_lot_number: "",
            expiry_date: "",
            notes: "",
          },
        ],
      })) || []
  );
  const [notes, setNotes] = useState("");
  const [autoGenerateLot, setAutoGenerateLot] = useState(false);
  // Received date defaults to today - user can change if items were received earlier
  const [receivedDate, setReceivedDate] = useState(
    new Date().toISOString().slice(0, 10)
  );

  // Calculate running totals
  const totals = useMemo(() => {
    const itemsToReceive = lines.filter(
      (l) => parseFloat(l.quantity_to_receive) > 0
    ).length;
    const totalQty = lines.reduce(
      (sum, l) => sum + (parseFloat(l.quantity_to_receive) || 0),
      0
    );
    return { itemsToReceive, totalQty };
  }, [lines]);

  const updateLine = (index, field, value) => {
    const newLines = [...lines];
    newLines[index] = { ...newLines[index], [field]: value };
    setLines(newLines);
  };

  const receiveAll = (index) => {
    const newLines = [...lines];
    newLines[index].quantity_to_receive = newLines[index].remaining;
    setLines(newLines);
  };

  const receiveNone = (index) => {
    const newLines = [...lines];
    newLines[index].quantity_to_receive = 0;
    setLines(newLines);
  };

  const receiveAllLines = () => {
    setLines(lines.map((l) => ({ ...l, quantity_to_receive: l.remaining })));
  };

  const generateLotNumber = (lineNumber) => {
    const today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    return `${po.po_number}-L${lineNumber}-${today}`;
  };

  // UOM Conversion Functions
  const convertToGrams = (value, unit) => {
    const val = parseFloat(value);
    if (isNaN(val)) return 0;

    const upperUnit = (unit || "G").toUpperCase();
    switch (upperUnit) {
      case "G":
        return val;
      case "KG":
        return val * 1000;
      case "LB":
        return val * 453.59237;
      case "OZ":
        return val * 28.34952;
      default:
        return val; // Assume grams if unknown
    }
  };

  const convertFromGrams = (grams, unit) => {
    const upperUnit = (unit || "G").toUpperCase();
    switch (upperUnit) {
      case "G":
        return grams;
      case "KG":
        return grams / 1000;
      case "LB":
        return grams / 453.59237;
      case "OZ":
        return grams / 28.34952;
      default:
        return grams;
    }
  };

  // Spool Management Functions
  const addSpool = (lineIndex) => {
    const newLines = [...lines];
    newLines[lineIndex].spools.push({
      weight_input: "",
      weight_g: 0,
      supplier_lot_number: "",
      expiry_date: "",
      notes: "",
    });
    setLines(newLines);
  };

  const removeSpool = (lineIndex, spoolIndex) => {
    const newLines = [...lines];
    newLines[lineIndex].spools.splice(spoolIndex, 1);
    setLines(newLines);
  };

  const updateSpoolField = (lineIndex, spoolIndex, field, value) => {
    const newLines = [...lines];
    newLines[lineIndex].spools[spoolIndex][field] = value;
    setLines(newLines);
  };

  const getSpoolWeightSum = (lineIndex) => {
    return lines[lineIndex].spools.reduce(
      (sum, s) => sum + (parseFloat(s.weight_g) || 0),
      0
    );
  };

  const getSpoolWeightSumDisplay = (lineIndex) => {
    const sumGrams = getSpoolWeightSum(lineIndex);
    const line = lines[lineIndex];
    // Display in purchase_unit for consistency
    return convertFromGrams(sumGrams, line.purchase_unit).toFixed(3);
  };

  const getSpoolWeightClass = (lineIndex) => {
    const sumGrams = getSpoolWeightSum(lineIndex);
    const line = lines[lineIndex];
    // Convert from purchase_unit to grams for comparison
    const targetGrams = convertToGrams(
      line.quantity_to_receive,
      line.purchase_unit
    );
    const diff = Math.abs(sumGrams - targetGrams);

    if (diff < 0.1) return "text-green-400 font-medium";
    if (diff < targetGrams * 0.1) return "text-yellow-400";
    return "text-red-400";
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    // Validate spool weights
    for (const l of lines) {
      if (l.create_spools && parseFloat(l.quantity_to_receive) > 0) {
        // Convert from purchase_unit to grams for spool validation
        const targetGrams = convertToGrams(
          l.quantity_to_receive,
          l.purchase_unit
        );
        const spoolSumGrams = l.spools.reduce(
          (sum, s) => sum + (parseFloat(s.weight_g) || 0),
          0
        );

        if (Math.abs(spoolSumGrams - targetGrams) > 0.1) {
          // 0.1g tolerance
          toast.error(
            `Spool weights for ${l.product_sku} must equal received quantity. ` +
              `Expected: ${targetGrams.toFixed(
                1
              )}g, Got: ${spoolSumGrams.toFixed(1)}g`
          );
          return;
        }

        // Filter out empty spools
        const validSpools = l.spools.filter((s) => parseFloat(s.weight_g) > 0);

        if (validSpools.length === 0) {
          toast.warning(
            `Please specify at least one spool weight for ${l.product_sku}`
          );
          return;
        }
      }
    }

    const receiveData = {
      lines: lines
        .filter((l) => parseFloat(l.quantity_to_receive) > 0)
        .map((l) => ({
          line_id: l.line_id,
          quantity_received: parseFloat(l.quantity_to_receive),
          lot_number:
            autoGenerateLot && !l.lot_number
              ? generateLotNumber(l.line_number)
              : l.lot_number || null,
          notes: l.notes || null,
          create_spools: l.create_spools,
          spools: l.create_spools
            ? l.spools
                .filter((s) => parseFloat(s.weight_g) > 0)
                .map((s) => ({
                  weight_g: parseFloat(s.weight_g),
                  supplier_lot_number: s.supplier_lot_number || null,
                  expiry_date: s.expiry_date || null,
                  notes: s.notes || null,
                }))
            : null,
        })),
      notes: notes || null,
      received_date: receivedDate,  // User-entered date (when items were actually received)
    };

    if (receiveData.lines.length === 0) {
      toast.warning("Please enter quantities to receive");
      return;
    }

    onReceive(receiveData);
  };

  const getProgressPercent = (line) => {
    const total =
      line.quantity_already_received +
      (parseFloat(line.quantity_to_receive) || 0);
    return Math.min(100, (total / line.quantity_ordered) * 100);
  };

  return (
    <Modal isOpen={true} onClose={onClose} title="Receive Items" className="max-w-4xl w-full mx-auto p-6 max-h-[90vh] overflow-y-auto">
          {/* Header */}
          <div className="flex justify-between items-start mb-6">
            <div>
              <h3 className="text-xl font-semibold text-white flex items-center gap-2">
                <svg
                  className="w-6 h-6 text-green-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M20 7l-8 8-4-4M4 12l4-4 4 4"
                  />
                </svg>
                Receive Items
              </h3>
              <p className="text-gray-400 mt-1">
                {po.po_number} • {po.vendor_name}
              </p>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white p-1"
            >
              <svg
                className="w-6 h-6"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>

          {/* Quick Actions Bar */}
          {lines.length > 0 && (
            <div className="flex items-center justify-between mb-4 p-3 bg-gray-800/50 rounded-lg">
              <div className="flex items-center gap-4">
                <button
                  type="button"
                  onClick={receiveAllLines}
                  className="px-3 py-1.5 bg-green-600/20 hover:bg-green-600/30 text-green-400 rounded-lg text-sm font-medium transition-colors"
                >
                  Receive All Items
                </button>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="autoLot"
                    checked={autoGenerateLot}
                    onChange={(e) => setAutoGenerateLot(e.target.checked)}
                    className="rounded bg-gray-700 border-gray-600 text-blue-600"
                  />
                  <label htmlFor="autoLot" className="text-sm text-gray-400">
                    Auto-generate lot numbers
                  </label>
                </div>
                {/* Received Date Picker */}
                <div className="flex items-center gap-2 border-l border-gray-700 pl-4">
                  <label htmlFor="receivedDate" className="text-sm text-gray-400">
                    Received:
                  </label>
                  <input
                    type="date"
                    id="receivedDate"
                    value={receivedDate}
                    onChange={(e) => setReceivedDate(e.target.value)}
                    max={new Date().toISOString().slice(0, 10)}
                    className="bg-gray-700 border border-gray-600 rounded-lg px-2 py-1 text-white text-sm"
                  />
                </div>
              </div>
              <div className="text-sm text-gray-400">
                <span className="text-white font-medium">
                  {totals.itemsToReceive}
                </span>{" "}
                items •
                <span className="text-white font-medium ml-1">
                  {totals.totalQty.toFixed(2)}
                </span>{" "}
                qty
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {lines.length === 0 ? (
              <div className="text-center py-12">
                <svg
                  className="w-16 h-16 mx-auto text-green-400 mb-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <p className="text-gray-300 text-lg">
                  All items have been received
                </p>
                <p className="text-gray-500 mt-1">
                  This purchase order is fully received
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {lines.map((line, index) => {
                  const progress = getProgressPercent(line);
                  const isFullyReceiving =
                    parseFloat(line.quantity_to_receive) >=
                    line.remaining - 0.001;
                  const isPartiallyReceiving =
                    parseFloat(line.quantity_to_receive) > 0 &&
                    !isFullyReceiving;
                  const isNotReceiving =
                    parseFloat(line.quantity_to_receive) === 0;

                  return (
                    <div
                      key={line.line_id}
                      className={`bg-gray-800/50 rounded-xl overflow-hidden transition-all ${
                        isNotReceiving ? "opacity-60" : ""
                      }`}
                    >
                      {/* Progress Bar */}
                      <div className="h-1 bg-gray-700">
                        <div
                          className={`h-full transition-all ${
                            progress >= 100
                              ? "bg-green-500"
                              : progress > 0
                              ? "bg-blue-500"
                              : "bg-gray-600"
                          }`}
                          style={{ width: `${progress}%` }}
                        />
                      </div>

                      <div className="p-4">
                        {/* Product Info Row */}
                        <div className="flex justify-between items-start mb-4">
                          <div className="flex-1">
                            <div className="text-lg font-semibold text-white">
                              {line.product_sku}
                            </div>
                            <div className="text-gray-400">
                              {line.product_name}
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="text-sm text-gray-400">
                              {line.quantity_already_received.toFixed(2)} of{" "}
                              {line.quantity_ordered.toFixed(2)}{" "}
                              {line.purchase_unit} received
                            </div>
                            <div
                              className={`text-sm font-medium ${
                                isFullyReceiving
                                  ? "text-green-400"
                                  : isPartiallyReceiving
                                  ? "text-yellow-400"
                                  : "text-gray-500"
                              }`}
                            >
                              {line.remaining.toFixed(2)} {line.purchase_unit}{" "}
                              remaining
                            </div>
                          </div>
                        </div>

                        {/* Input Row */}
                        <div className="grid grid-cols-12 gap-3 items-end">
                          {/* Quantity Input - Large and prominent */}
                          <div className="col-span-4">
                            <label className="block text-xs text-gray-400 mb-1">
                              Qty to Receive
                            </label>
                            <div className="flex items-center gap-2">
                              <input
                                type="number"
                                value={line.quantity_to_receive}
                                onChange={(e) =>
                                  updateLine(
                                    index,
                                    "quantity_to_receive",
                                    e.target.value
                                  )
                                }
                                min="0"
                                max={line.remaining}
                                step="0.01"
                                placeholder={`Max: ${line.remaining.toFixed(
                                  2
                                )} ${line.purchase_unit}`}
                                className="w-full bg-gray-700 border-2 border-gray-600 focus:border-blue-500 rounded-lg px-4 py-3 text-white text-lg font-medium"
                              />
                              <span className="text-gray-400 text-sm whitespace-nowrap">
                                {line.purchase_unit}
                              </span>
                            </div>
                          </div>

                          {/* Quick Actions */}
                          <div className="col-span-2 flex flex-col gap-1">
                            <button
                              type="button"
                              onClick={() => receiveAll(index)}
                              className={`px-2 py-1.5 rounded text-xs font-medium transition-colors ${
                                isFullyReceiving
                                  ? "bg-green-600/30 text-green-400"
                                  : "bg-gray-700 hover:bg-green-600/20 text-gray-300 hover:text-green-400"
                              }`}
                            >
                              All ({line.remaining.toFixed(0)})
                            </button>
                            <button
                              type="button"
                              onClick={() => receiveNone(index)}
                              className={`px-2 py-1.5 rounded text-xs font-medium transition-colors ${
                                isNotReceiving
                                  ? "bg-gray-600/30 text-gray-400"
                                  : "bg-gray-700 hover:bg-gray-600 text-gray-300"
                              }`}
                            >
                              None
                            </button>
                          </div>

                          {/* Lot Number */}
                          <div className="col-span-3">
                            <label className="block text-xs text-gray-400 mb-1">
                              Lot Number
                            </label>
                            <input
                              type="text"
                              value={line.lot_number}
                              onChange={(e) =>
                                updateLine(index, "lot_number", e.target.value)
                              }
                              placeholder={
                                autoGenerateLot ? "(auto)" : "Optional"
                              }
                              disabled={autoGenerateLot}
                              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2.5 text-white disabled:opacity-50 disabled:cursor-not-allowed"
                            />
                          </div>

                          {/* Notes */}
                          <div className="col-span-3">
                            <label className="block text-xs text-gray-400 mb-1">
                              Notes
                            </label>
                            <input
                              type="text"
                              value={line.notes}
                              onChange={(e) =>
                                updateLine(index, "notes", e.target.value)
                              }
                              placeholder="Optional"
                              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2.5 text-white"
                            />
                          </div>
                        </div>

                        {/* Spool Creation Section - Only for materials */}
                        {line.is_material &&
                          parseFloat(line.quantity_to_receive) > 0 && (
                            <div className="mt-3 pt-3 border-t border-gray-700">
                              <div className="flex items-center gap-2 mb-2">
                                <input
                                  type="checkbox"
                                  id={`create-spools-${index}`}
                                  checked={line.create_spools}
                                  onChange={(e) =>
                                    updateLine(
                                      index,
                                      "create_spools",
                                      e.target.checked
                                    )
                                  }
                                  className="rounded bg-gray-700 border-gray-600 text-blue-600"
                                />
                                <label
                                  htmlFor={`create-spools-${index}`}
                                  className="text-sm text-gray-300 font-medium flex items-center gap-2"
                                >
                                  <svg
                                    className="w-4 h-4 text-blue-400"
                                    fill="none"
                                    stroke="currentColor"
                                    viewBox="0 0 24 24"
                                  >
                                    <path
                                      strokeLinecap="round"
                                      strokeLinejoin="round"
                                      strokeWidth={2}
                                      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                                    />
                                  </svg>
                                  Create Material Spools
                                  <span className="text-xs text-gray-500">
                                    (Enables lot-level traceability)
                                  </span>
                                </label>
                              </div>

                              {line.create_spools && (
                                <div className="ml-6 space-y-3 bg-gray-900/50 rounded-lg p-3">
                                  <div className="flex items-center justify-between text-xs">
                                    <span className="text-gray-400">
                                      Total to allocate:{" "}
                                      <span className="font-mono text-white">
                                        {line.quantity_to_receive}
                                      </span>{" "}
                                      {line.purchase_unit}
                                    </span>
                                    <span className="text-gray-400">
                                      ={" "}
                                      <span className="font-mono text-white">
                                        {convertToGrams(
                                          line.quantity_to_receive,
                                          line.purchase_unit
                                        ).toFixed(1)}
                                      </span>{" "}
                                      g
                                    </span>
                                  </div>

                                  {line.spools.map((spool, spoolIdx) => (
                                    <div
                                      key={spoolIdx}
                                      className="grid grid-cols-12 gap-2 items-end bg-gray-800/50 rounded p-2"
                                    >
                                      {/* Spool Number Preview */}
                                      <div className="col-span-3">
                                        <label className="block text-xs text-gray-400 mb-1">
                                          Spool #
                                        </label>
                                        <div className="px-2 py-1.5 bg-gray-700/50 rounded text-xs font-mono text-gray-300 border border-gray-600">
                                          {po.po_number}-L{line.line_number}-
                                          {String(spoolIdx + 1).padStart(
                                            3,
                                            "0"
                                          )}
                                        </div>
                                      </div>

                                      {/* Weight Input */}
                                      <div className="col-span-2">
                                        <label className="block text-xs text-gray-400 mb-1">
                                          Weight ({line.purchase_unit})
                                        </label>
                                        <input
                                          type="number"
                                          value={spool.weight_input || ""}
                                          onChange={(e) => {
                                            const newLines = [...lines];
                                            newLines[index].spools[
                                              spoolIdx
                                            ].weight_input = e.target.value;
                                            newLines[index].spools[
                                              spoolIdx
                                            ].weight_g = convertToGrams(
                                              e.target.value,
                                              line.purchase_unit
                                            );
                                            setLines(newLines);
                                          }}
                                          step="0.001"
                                          min="0"
                                          placeholder="1.000"
                                          className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-white text-sm font-mono"
                                        />
                                      </div>

                                      {/* Grams Display */}
                                      <div className="col-span-2">
                                        <label className="block text-xs text-gray-400 mb-1">
                                          Grams
                                        </label>
                                        <div className="px-2 py-1.5 bg-gray-900 rounded text-xs font-mono text-green-400 border border-gray-700">
                                          {(spool.weight_g || 0).toFixed(1)}g
                                        </div>
                                      </div>

                                      {/* Lot Number */}
                                      <div className="col-span-2">
                                        <label className="block text-xs text-gray-400 mb-1">
                                          Lot #
                                        </label>
                                        <input
                                          type="text"
                                          value={spool.supplier_lot_number}
                                          onChange={(e) =>
                                            updateSpoolField(
                                              index,
                                              spoolIdx,
                                              "supplier_lot_number",
                                              e.target.value
                                            )
                                          }
                                          placeholder="Optional"
                                          className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-white text-xs"
                                        />
                                      </div>

                                      {/* Expiry */}
                                      <div className="col-span-2">
                                        <label className="block text-xs text-gray-400 mb-1">
                                          Expiry
                                        </label>
                                        <input
                                          type="date"
                                          value={spool.expiry_date || ""}
                                          onChange={(e) =>
                                            updateSpoolField(
                                              index,
                                              spoolIdx,
                                              "expiry_date",
                                              e.target.value
                                            )
                                          }
                                          className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-white text-xs"
                                        />
                                      </div>

                                      {/* Remove Button */}
                                      {line.spools.length > 1 && (
                                        <div className="col-span-1">
                                          <button
                                            type="button"
                                            onClick={() =>
                                              removeSpool(index, spoolIdx)
                                            }
                                            className="w-full px-2 py-1.5 text-red-400 hover:bg-red-500/10 rounded"
                                            title="Remove spool"
                                          >
                                            <svg
                                              className="w-4 h-4 mx-auto"
                                              fill="none"
                                              stroke="currentColor"
                                              viewBox="0 0 24 24"
                                            >
                                              <path
                                                strokeLinecap="round"
                                                strokeLinejoin="round"
                                                strokeWidth={2}
                                                d="M6 18L18 6M6 6l12 12"
                                              />
                                            </svg>
                                          </button>
                                        </div>
                                      )}
                                    </div>
                                  ))}

                                  {/* Footer: Add Spool + Validation */}
                                  <div className="flex items-center justify-between pt-2 border-t border-gray-700">
                                    <button
                                      type="button"
                                      onClick={() => addSpool(index)}
                                      className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
                                    >
                                      <svg
                                        className="w-4 h-4"
                                        fill="none"
                                        stroke="currentColor"
                                        viewBox="0 0 24 24"
                                      >
                                        <path
                                          strokeLinecap="round"
                                          strokeLinejoin="round"
                                          strokeWidth={2}
                                          d="M12 6v6m0 0v6m0-6h6m-6 0H6"
                                        />
                                      </svg>
                                      Add Another Spool
                                    </button>

                                    <div className="text-xs">
                                      <span className="text-gray-400">
                                        Total:{" "}
                                      </span>
                                      <span
                                        className={getSpoolWeightClass(index)}
                                      >
                                        {getSpoolWeightSumDisplay(index)} /{" "}
                                        {line.quantity_to_receive}{" "}
                                        {line.purchase_unit}
                                      </span>
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Receipt Notes */}
            {lines.length > 0 && (
              <div className="border-t border-gray-800 pt-4">
                <label className="block text-sm text-gray-400 mb-1">
                  Receipt Notes (applies to all items)
                </label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={2}
                  placeholder="Optional notes for this receipt transaction"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>
            )}

            {/* Footer */}
            <div className="flex justify-between items-center pt-4 border-t border-gray-800">
              <div className="text-sm text-gray-400">
                {totals.itemsToReceive > 0 && (
                  <>
                    Receiving{" "}
                    <span className="text-white font-medium">
                      {totals.itemsToReceive}
                    </span>{" "}
                    line items, total qty:{" "}
                    <span className="text-white font-medium">
                      {totals.totalQty.toFixed(2)}
                    </span>
                  </>
                )}
              </div>
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={totals.itemsToReceive === 0}
                  className="px-6 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-white font-medium flex items-center gap-2"
                >
                  <svg
                    className="w-5 h-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                  Receive Items
                </button>
              </div>
            </div>
          </form>
    </Modal>
  );
}
