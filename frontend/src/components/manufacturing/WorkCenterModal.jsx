/**
 * WorkCenterModal - Form for creating/editing work centers with overhead rate calculator.
 */
import { useState } from "react";
import { CENTER_TYPES } from "./constants";

export default function WorkCenterModal({ workCenter, onClose, onSave }) {
  const [form, setForm] = useState({
    code: workCenter?.code || "",
    name: workCenter?.name || "",
    description: workCenter?.description || "",
    center_type: workCenter?.center_type || "station",
    capacity_hours_per_day: workCenter?.capacity_hours_per_day ?? "",
    capacity_units_per_hour: workCenter?.capacity_units_per_hour ?? "",
    machine_rate_per_hour: workCenter?.machine_rate_per_hour ?? "",
    labor_rate_per_hour: workCenter?.labor_rate_per_hour ?? "",
    overhead_rate_per_hour: workCenter?.overhead_rate_per_hour ?? "",
    is_bottleneck: workCenter?.is_bottleneck ?? false,
    scheduling_priority: workCenter?.scheduling_priority ?? 50,
    is_active: workCenter?.is_active ?? true,
  });

  // Overhead calculator state
  const [showCalculator, setShowCalculator] = useState(false);
  const [calc, setCalc] = useState({
    printerCost: 1200,
    lifespanYears: 3,
    hoursPerDay: 20,
    daysPerYear: 350,
    electricityRate: 0.12,
    wattage: 150,
    annualMaintenance: 150,
  });

  // Calculate overhead rate from inputs
  const calculatedOverhead = (() => {
    const annualHours = calc.hoursPerDay * calc.daysPerYear;
    if (annualHours === 0) return 0;
    const depreciation = calc.printerCost / calc.lifespanYears / annualHours;
    const electricity = calc.electricityRate * (calc.wattage / 1000);
    const maintenance = calc.annualMaintenance / annualHours;
    return depreciation + electricity + maintenance;
  })();

  const applyCalculatedRate = () => {
    setForm({ ...form, overhead_rate_per_hour: calculatedOverhead.toFixed(3) });
    setShowCalculator(false);
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    // Convert empty strings to null for numeric fields (preserve zero values)
    const data = {
      ...form,
      capacity_hours_per_day: form.capacity_hours_per_day === "" ? null : form.capacity_hours_per_day,
      capacity_units_per_hour: form.capacity_units_per_hour === "" ? null : form.capacity_units_per_hour,
      machine_rate_per_hour: form.machine_rate_per_hour === "" ? null : form.machine_rate_per_hour,
      labor_rate_per_hour: form.labor_rate_per_hour === "" ? null : form.labor_rate_per_hour,
      overhead_rate_per_hour: form.overhead_rate_per_hour === "" ? null : form.overhead_rate_per_hour,
    };

    onSave(data);
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-lg border border-gray-700 w-full max-w-xl max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-gray-800">
          <h2 className="text-xl font-bold text-white">
            {workCenter ? "Edit Work Center" : "New Work Center"}
          </h2>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Code *</label>
              <input
                type="text"
                value={form.code}
                onChange={(e) =>
                  setForm({ ...form, code: e.target.value.toUpperCase() })
                }
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                placeholder="FDM-POOL"
                required
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Type</label>
              <select
                value={form.center_type}
                onChange={(e) =>
                  setForm({ ...form, center_type: e.target.value })
                }
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
              >
                {CENTER_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">Name *</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
              placeholder="FDM Printer Pool"
              required
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Description
            </label>
            <textarea
              value={form.description}
              onChange={(e) =>
                setForm({ ...form, description: e.target.value })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
              rows={2}
            />
          </div>

          <div className="border-t border-gray-800 pt-4">
            <h3 className="text-sm font-medium text-gray-300 mb-3">Capacity</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Hours/Day
                </label>
                <input
                  type="number"
                  step="0.5"
                  value={form.capacity_hours_per_day}
                  onChange={(e) =>
                    setForm({ ...form, capacity_hours_per_day: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                  placeholder="8"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Units/Hour
                </label>
                <input
                  type="number"
                  step="0.1"
                  value={form.capacity_units_per_hour}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      capacity_units_per_hour: e.target.value,
                    })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                  placeholder="10"
                />
              </div>
            </div>
          </div>

          <div className="border-t border-gray-800 pt-4">
            <h3 className="text-sm font-medium text-gray-300 mb-3">
              Hourly Rates ($)
            </h3>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Machine
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={form.machine_rate_per_hour}
                  onChange={(e) =>
                    setForm({ ...form, machine_rate_per_hour: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                  placeholder="2.00"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Labor
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={form.labor_rate_per_hour}
                  onChange={(e) =>
                    setForm({ ...form, labor_rate_per_hour: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                  placeholder="25.00"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Overhead
                  <button
                    type="button"
                    onClick={() => setShowCalculator(!showCalculator)}
                    className="ml-2 text-xs text-blue-400 hover:text-blue-300"
                  >
                    {showCalculator ? "Hide Calculator" : "Calculate"}
                  </button>
                </label>
                <input
                  type="number"
                  step="0.001"
                  value={form.overhead_rate_per_hour}
                  onChange={(e) =>
                    setForm({ ...form, overhead_rate_per_hour: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                  placeholder="0.09"
                />
              </div>
            </div>

            {/* Overhead Calculator */}
            {showCalculator && (
              <div className="mt-4 p-4 bg-gray-800 rounded-lg border border-blue-500/30">
                <h4 className="text-sm font-medium text-blue-400 mb-3">
                  Overhead Rate Calculator
                </h4>
                <p className="text-xs text-gray-500 mb-3">
                  Calculate machine overhead from depreciation + electricity +
                  maintenance
                </p>

                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">
                      Printer Cost ($)
                    </label>
                    <input
                      type="number"
                      value={calc.printerCost}
                      onChange={(e) =>
                        setCalc({
                          ...calc,
                          printerCost: parseFloat(e.target.value) || 0,
                        })
                      }
                      className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">
                      Lifespan (years)
                    </label>
                    <input
                      type="number"
                      value={calc.lifespanYears}
                      onChange={(e) =>
                        setCalc({
                          ...calc,
                          lifespanYears: parseFloat(e.target.value) || 1,
                        })
                      }
                      className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">
                      Hours/Day
                    </label>
                    <input
                      type="number"
                      value={calc.hoursPerDay}
                      onChange={(e) =>
                        setCalc({
                          ...calc,
                          hoursPerDay: parseFloat(e.target.value) || 0,
                        })
                      }
                      className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">
                      Days/Year
                    </label>
                    <input
                      type="number"
                      value={calc.daysPerYear}
                      onChange={(e) =>
                        setCalc({
                          ...calc,
                          daysPerYear: parseFloat(e.target.value) || 0,
                        })
                      }
                      className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">
                      Electricity ($/kWh)
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      value={calc.electricityRate}
                      onChange={(e) =>
                        setCalc({
                          ...calc,
                          electricityRate: parseFloat(e.target.value) || 0,
                        })
                      }
                      className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-400 mb-1">
                      Wattage (W)
                    </label>
                    <input
                      type="number"
                      value={calc.wattage}
                      onChange={(e) =>
                        setCalc({
                          ...calc,
                          wattage: parseFloat(e.target.value) || 0,
                        })
                      }
                      className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                    />
                  </div>
                  <div className="col-span-2">
                    <label className="block text-xs text-gray-400 mb-1">
                      Annual Maintenance ($)
                    </label>
                    <input
                      type="number"
                      value={calc.annualMaintenance}
                      onChange={(e) =>
                        setCalc({
                          ...calc,
                          annualMaintenance: parseFloat(e.target.value) || 0,
                        })
                      }
                      className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                    />
                  </div>
                </div>

                <div className="mt-4 flex items-center justify-between">
                  <div className="text-sm">
                    <span className="text-gray-400">Calculated rate: </span>
                    <span className="text-green-400 font-mono font-bold">
                      ${calculatedOverhead.toFixed(3)}/hr
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={applyCalculatedRate}
                    className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded"
                  >
                    Apply Rate
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="border-t border-gray-800 pt-4">
            <h3 className="text-sm font-medium text-gray-300 mb-3">
              Scheduling
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Priority (0-100)
                </label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={form.scheduling_priority}
                  onChange={(e) => {
                    const value = e.target.value;
                    setForm({
                      ...form,
                      scheduling_priority:
                        value === "" ? "" : parseInt(value, 10),
                    });
                  }}
                  className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                />
              </div>
              <div className="flex items-center gap-4 pt-6">
                <label className="flex items-center gap-2 text-sm text-gray-300">
                  <input
                    type="checkbox"
                    checked={form.is_bottleneck}
                    onChange={(e) =>
                      setForm({ ...form, is_bottleneck: e.target.checked })
                    }
                    className="rounded bg-gray-800 border-gray-700"
                  />
                  Bottleneck
                </label>
                <label className="flex items-center gap-2 text-sm text-gray-300">
                  <input
                    type="checkbox"
                    checked={form.is_active}
                    onChange={(e) =>
                      setForm({ ...form, is_active: e.target.checked })
                    }
                    className="rounded bg-gray-800 border-gray-700"
                  />
                  Active
                </label>
              </div>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-400 hover:text-white"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg"
            >
              {workCenter ? "Save Changes" : "Create Work Center"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
