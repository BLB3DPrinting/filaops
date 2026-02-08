import { useState } from "react";
import { useToast } from "../../components/Toast";
import { useCRUD } from "../../hooks/useCRUD";
import { Badge, Button, Input, Select } from "../../components/ui";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  TableEmpty,
} from "../../components/ui";

const TYPE_OPTIONS = [
  { value: "warehouse", label: "Warehouse", badge: "info" },
  { value: "shelf", label: "Shelf", badge: "success" },
  { value: "bin", label: "Bin", badge: "warning" },
  { value: "staging", label: "Staging Area", badge: "purple" },
  { value: "quality", label: "Quality/QC", badge: "warning" },
];

const TYPE_SELECT_OPTIONS = TYPE_OPTIONS.map(({ value, label }) => ({
  value,
  label,
}));

function getTypeBadgeVariant(type) {
  const found = TYPE_OPTIONS.find((t) => t.value === type);
  return found ? found.badge : "neutral";
}

function getTypeLabel(type) {
  const found = TYPE_OPTIONS.find((t) => t.value === type);
  return found ? found.label : type;
}

const PlusIcon = () => (
  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
  </svg>
);

const EditIcon = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
    />
  </svg>
);

const TrashIcon = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
    />
  </svg>
);

const RefreshIcon = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
    />
  </svg>
);

export default function AdminLocations() {
  const toast = useToast();
  const [showModal, setShowModal] = useState(false);
  const [editingLocation, setEditingLocation] = useState(null);
  const [includeInactive, setIncludeInactive] = useState(false);

  const { items: locations, loading, error, fetchAll, create, update, remove } = useCRUD(
    "/api/v1/admin/locations",
    { extractKey: null }
  );

  const refetch = () => {
    const params = includeInactive ? { include_inactive: "true" } : {};
    fetchAll(params).catch(() => {});
  };

  // Refetch when includeInactive changes
  useState(() => { refetch(); });

  const handleSave = async (locationData) => {
    try {
      if (editingLocation) {
        await update(editingLocation.id, locationData);
        toast.success("Location updated");
      } else {
        await create(locationData);
        toast.success("Location created");
      }
      setShowModal(false);
      setEditingLocation(null);
      refetch();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleDelete = async (location) => {
    if (location.code === "MAIN") {
      toast.error("Cannot delete the main warehouse");
      return;
    }
    if (!confirm(`Deactivate location "${location.name}"?`)) return;

    try {
      await remove(location.id);
      toast.success("Location deactivated");
      refetch();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleReactivate = async (location) => {
    try {
      await update(location.id, { active: true });
      toast.success("Location reactivated");
      refetch();
    } catch (err) {
      toast.error(err.message);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Inventory Locations</h1>
          <p className="text-gray-400 mt-1">
            Manage warehouses, shelves, and storage locations
          </p>
        </div>
        <Button
          variant="primary"
          icon={<PlusIcon />}
          onClick={() => {
            setEditingLocation(null);
            setShowModal(true);
          }}
        >
          Add Location
        </Button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2 text-gray-400">
          <input
            type="checkbox"
            checked={includeInactive}
            onChange={(e) => {
              setIncludeInactive(e.target.checked);
              const params = e.target.checked ? { include_inactive: "true" } : {};
              fetchAll(params).catch(() => {});
            }}
            className="rounded bg-gray-800 border-gray-700 text-blue-500 focus:ring-blue-500"
          />
          Show inactive locations
        </label>
      </div>

      {/* Locations Table */}
      <div className="overflow-x-auto">
      <Table className="min-w-[640px]">
        <TableHeader>
          <TableRow>
            <TableHead>Code</TableHead>
            <TableHead>Name</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Parent</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {locations.length === 0 ? (
            <TableEmpty colSpan={6}>
              No locations found. Click &quot;Add Location&quot; to create one.
            </TableEmpty>
          ) : (
            locations.map((location) => {
              const parent = locations.find((l) => l.id === location.parent_id);
              return (
                <TableRow
                  key={location.id}
                  className={!location.active ? "opacity-50" : ""}
                >
                  <TableCell className="font-mono">{location.code}</TableCell>
                  <TableCell>{location.name}</TableCell>
                  <TableCell>
                    <Badge variant={getTypeBadgeVariant(location.type)}>
                      {getTypeLabel(location.type)}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-gray-400">
                    {parent ? parent.code : "\u2014"}
                  </TableCell>
                  <TableCell>
                    <Badge variant={location.active ? "success" : "neutral"}>
                      {location.active ? "Active" : "Inactive"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => {
                          setEditingLocation(location);
                          setShowModal(true);
                        }}
                        className="text-gray-400 hover:text-white p-1"
                        title="Edit"
                      >
                        <EditIcon />
                      </button>
                      {location.active ? (
                        <button
                          onClick={() => handleDelete(location)}
                          className="text-gray-400 hover:text-red-400 p-1"
                          title="Deactivate"
                          disabled={location.code === "MAIN"}
                        >
                          <TrashIcon />
                        </button>
                      ) : (
                        <button
                          onClick={() => handleReactivate(location)}
                          className="text-gray-400 hover:text-green-400 p-1"
                          title="Reactivate"
                        >
                          <RefreshIcon />
                        </button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              );
            })
          )}
        </TableBody>
      </Table>
      </div>

      {/* Modal */}
      {showModal && (
        <LocationModal
          location={editingLocation}
          locations={locations}
          onSave={handleSave}
          onClose={() => {
            setShowModal(false);
            setEditingLocation(null);
          }}
        />
      )}
    </div>
  );
}

function LocationModal({ location, locations, onSave, onClose }) {
  const [formData, setFormData] = useState({
    code: location?.code || "",
    name: location?.name || "",
    type: location?.type || "warehouse",
    parent_id: location?.parent_id || null,
  });

  const parentOptions = locations
    .filter((l) => l.id !== location?.id)
    .map((l) => ({ value: String(l.id), label: `${l.code} - ${l.name}` }));

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!formData.code.trim() || !formData.name.trim()) {
      return;
    }
    onSave(formData);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-gray-900 rounded-lg border border-gray-800 w-full max-w-md mx-4 p-6">
        <h2 className="text-xl font-bold text-white mb-4">
          {location ? "Edit Location" : "Add Location"}
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Code *"
            type="text"
            value={formData.code}
            onChange={(e) =>
              setFormData({ ...formData, code: e.target.value.toUpperCase() })
            }
            placeholder="e.g., SHELF-A"
            required
          />
          <Input
            label="Name *"
            type="text"
            value={formData.name}
            onChange={(e) =>
              setFormData({ ...formData, name: e.target.value })
            }
            placeholder="e.g., Shelf A - Filament Storage"
            required
          />
          <Select
            label="Type"
            options={TYPE_SELECT_OPTIONS}
            value={formData.type}
            onChange={(e) =>
              setFormData({ ...formData, type: e.target.value })
            }
          />
          <Select
            label="Parent Location"
            options={parentOptions}
            placeholder="None (Top Level)"
            value={formData.parent_id ? String(formData.parent_id) : ""}
            onChange={(e) =>
              setFormData({
                ...formData,
                parent_id: e.target.value ? parseInt(e.target.value) : null,
              })
            }
          />
          <div className="flex justify-end gap-3 pt-4">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button variant="primary" type="submit">
              {location ? "Save Changes" : "Create Location"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
