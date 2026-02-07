import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../../components/Toast";
import Modal from "../../components/Modal";

// Role options
const ROLE_OPTIONS = [
  {
    value: "admin",
    label: "Admin",
    color: "purple",
    description: "Full access to all features",
  },
  {
    value: "operator",
    label: "Operator",
    color: "blue",
    description: "Production floor access",
  },
];

// Status options
const STATUS_OPTIONS = [
  { value: "active", label: "Active", color: "green" },
  { value: "inactive", label: "Inactive", color: "gray" },
  { value: "suspended", label: "Suspended", color: "red" },
];

export default function AdminUsers() {
  const toast = useToast();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({
    search: "",
    role: "all",
    includeInactive: false,
  });

  // Modal states
  const [showUserModal, setShowUserModal] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [showResetPasswordModal, setShowResetPasswordModal] = useState(false);
  const [resetPasswordUser, setResetPasswordUser] = useState(null);
  const [savingUser, setSavingUser] = useState(false);
  const [resettingPassword, setResettingPassword] = useState(false);

  useEffect(() => {
    fetchUsers();
  }, [filters.role, filters.includeInactive]);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("limit", "200");
      if (filters.role !== "all") params.set("account_type", filters.role);
      if (filters.includeInactive) params.set("include_inactive", "true");

      const res = await fetch(`${API_URL}/api/v1/admin/users?${params}`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error("Failed to fetch users");
      const data = await res.json();
      setUsers(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const filteredUsers = users.filter((user) => {
    if (!filters.search) return true;
    const search = filters.search.toLowerCase();
    return (
      user.email?.toLowerCase().includes(search) ||
      user.full_name?.toLowerCase().includes(search)
    );
  });

  // Stats calculations
  const stats = {
    total: users.length,
    admins: users.filter(
      (u) => u.account_type === "admin" && u.status === "active"
    ).length,
    operators: users.filter(
      (u) => u.account_type === "operator" && u.status === "active"
    ).length,
    inactive: users.filter((u) => u.status !== "active").length,
  };

  const getRoleStyle = (role) => {
    const found = ROLE_OPTIONS.find((r) => r.value === role);
    if (!found) return "bg-gray-500/20 text-gray-400";
    return {
      purple: "bg-purple-500/20 text-purple-400",
      blue: "bg-blue-500/20 text-blue-400",
    }[found.color];
  };

  const getStatusStyle = (status) => {
    const found = STATUS_OPTIONS.find((s) => s.value === status);
    if (!found) return "bg-gray-500/20 text-gray-400";
    return {
      green: "bg-green-500/20 text-green-400",
      gray: "bg-gray-500/20 text-gray-400",
      red: "bg-red-500/20 text-red-400",
    }[found.color];
  };

  // Save user
  const handleSaveUser = async (userData) => {
    setSavingUser(true);
    try {
      const url = editingUser
        ? `${API_URL}/api/v1/admin/users/${editingUser.id}`
        : `${API_URL}/api/v1/admin/users`;
      const method = editingUser ? "PATCH" : "POST";

      const res = await fetch(url, {
        method,
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(userData),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to save user");
      }

      toast.success(editingUser ? "User updated" : "User created");
      setShowUserModal(false);
      setEditingUser(null);
      fetchUsers();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSavingUser(false);
    }
  };

  // Deactivate user
  const handleDeactivate = async (user) => {
    if (
      !confirm(
        `Deactivate ${user.email}? They will no longer be able to log in.`
      )
    )
      return;

    try {
      const res = await fetch(`${API_URL}/api/v1/admin/users/${user.id}`, {
        method: "DELETE",
        credentials: "include",
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to deactivate user");
      }

      toast.success("User deactivated");
      fetchUsers();
    } catch (err) {
      toast.error(err.message);
    }
  };

  // Reactivate user
  const handleReactivate = async (user) => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/users/${user.id}/reactivate`,
        {
          method: "POST",
          credentials: "include",
        }
      );

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to reactivate user");
      }

      toast.success("User reactivated");
      fetchUsers();
    } catch (err) {
      toast.error(err.message);
    }
  };

  // Reset password
  const handleResetPassword = async (newPassword) => {
    if (!resetPasswordUser) return;

    setResettingPassword(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/users/${resetPasswordUser.id}/reset-password`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ new_password: newPassword }),
        }
      );

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to reset password");
      }

      setShowResetPasswordModal(false);
      setResetPasswordUser(null);
      toast.success("Password reset successfully. User will need to log in with the new password.");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setResettingPassword(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white">Team Members</h1>
          <p className="text-gray-400 mt-1">
            Manage admin and operator access to FilaOps
          </p>
        </div>
        <button
          onClick={() => {
            setEditingUser(null);
            setShowUserModal(true);
          }}
          className="px-4 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500"
        >
          + Add User
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <p className="text-gray-400 text-sm">Total Active</p>
          <p className="text-2xl font-bold text-white">
            {stats.admins + stats.operators}
          </p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <p className="text-gray-400 text-sm">Admins</p>
          <p className="text-2xl font-bold text-purple-400">{stats.admins}</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <p className="text-gray-400 text-sm">Operators</p>
          <p className="text-2xl font-bold text-blue-400">{stats.operators}</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <p className="text-gray-400 text-sm">Inactive</p>
          <p className="text-2xl font-bold text-gray-500">{stats.inactive}</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-4 bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div className="flex-1">
          <input
            type="text"
            placeholder="Search by email or name..."
            value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500"
          />
        </div>
        <select
          value={filters.role}
          onChange={(e) => setFilters({ ...filters, role: e.target.value })}
          className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
        >
          <option value="all">All Roles</option>
          {ROLE_OPTIONS.map((role) => (
            <option key={role.value} value={role.value}>
              {role.label}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-gray-400 cursor-pointer">
          <input
            type="checkbox"
            checked={filters.includeInactive}
            onChange={(e) =>
              setFilters({ ...filters, includeInactive: e.target.checked })
            }
            className="rounded bg-gray-800 border-gray-700"
          />
          Show Inactive
        </label>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      )}

      {/* Users Table */}
      {!loading && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-800/50">
              <tr>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  User
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Email
                </th>
                <th className="text-center py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Role
                </th>
                <th className="text-center py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Status
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Last Login
                </th>
                <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((user) => (
                <tr
                  key={user.id}
                  className={`border-b border-gray-800 hover:bg-gray-800/50 ${
                    user.status !== "active" ? "opacity-60" : ""
                  }`}
                >
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center text-white text-sm font-medium">
                        {user.first_name?.[0] || user.email?.[0]?.toUpperCase() || "?"}
                      </div>
                      <span className="text-white">
                        {user.full_name || "-"}
                      </span>
                    </div>
                  </td>
                  <td className="py-3 px-4 text-gray-300">{user.email}</td>
                  <td className="py-3 px-4 text-center">
                    <span
                      className={`px-2 py-1 rounded-full text-xs ${getRoleStyle(
                        user.account_type
                      )}`}
                    >
                      {ROLE_OPTIONS.find((r) => r.value === user.account_type)
                        ?.label || user.account_type}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-center">
                    <span
                      className={`px-2 py-1 rounded-full text-xs ${getStatusStyle(
                        user.status
                      )}`}
                    >
                      {STATUS_OPTIONS.find((s) => s.value === user.status)
                        ?.label || user.status}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-gray-400 text-sm">
                    {user.last_login_at
                      ? new Date(user.last_login_at).toLocaleDateString()
                      : "Never"}
                  </td>
                  <td className="py-3 px-4 text-right">
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => {
                          setEditingUser(user);
                          setShowUserModal(true);
                        }}
                        className="text-blue-400 hover:text-blue-300 text-sm"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => {
                          setResetPasswordUser(user);
                          setShowResetPasswordModal(true);
                        }}
                        className="text-gray-400 hover:text-white text-sm"
                      >
                        Reset PW
                      </button>
                      {user.status === "active" ? (
                        <button
                          onClick={() => handleDeactivate(user)}
                          className="text-red-400 hover:text-red-300 text-sm"
                        >
                          Deactivate
                        </button>
                      ) : (
                        <button
                          onClick={() => handleReactivate(user)}
                          className="text-green-400 hover:text-green-300 text-sm"
                        >
                          Reactivate
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {filteredUsers.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-gray-500">
                    No users found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Role Info */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <h3 className="text-sm font-medium text-gray-400 uppercase mb-3">
          Role Permissions
        </h3>
        <div className="grid grid-cols-2 gap-4">
          {ROLE_OPTIONS.map((role) => (
            <div key={role.value} className="flex items-start gap-3">
              <span
                className={`px-2 py-1 rounded-full text-xs ${getRoleStyle(
                  role.value
                )}`}
              >
                {role.label}
              </span>
              <span className="text-gray-400 text-sm">{role.description}</span>
            </div>
          ))}
        </div>
      </div>

      {/* User Create/Edit Modal */}
      {showUserModal && (
        <UserModal
          user={editingUser}
          onSave={handleSaveUser}
          onClose={() => {
            setShowUserModal(false);
            setEditingUser(null);
          }}
          saving={savingUser}
        />
      )}

      {/* Reset Password Modal */}
      {showResetPasswordModal && resetPasswordUser && (
        <ResetPasswordModal
          user={resetPasswordUser}
          onReset={handleResetPassword}
          onClose={() => {
            setShowResetPasswordModal(false);
            setResetPasswordUser(null);
          }}
          saving={resettingPassword}
        />
      )}
    </div>
  );
}

// User Create/Edit Modal
function UserModal({ user, onSave, onClose, saving }) {
  const toast = useToast();
  const [form, setForm] = useState({
    email: user?.email || "",
    password: "",
    first_name: user?.first_name || "",
    last_name: user?.last_name || "",
    account_type: user?.account_type || "operator",
    status: user?.status || "active",
  });
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();

    // Validation
    if (!user && form.password.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }

    // Build payload - exclude password if editing and not changed
    const payload = { ...form };
    if (user && !form.password) {
      delete payload.password;
    }

    onSave(payload);
  };

  return (
    <Modal isOpen={true} onClose={onClose} title={user ? "Edit User" : "Add New User"} disableClose={saving}>
      <div className="p-6 border-b border-gray-800">
        <h2 className="text-xl font-bold text-white">
          {user ? "Edit User" : "Add New User"}
        </h2>
        {!user && (
          <p className="text-gray-400 text-sm mt-1">
            User will need this password to log in for the first time
          </p>
        )}
      </div>

      <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Email *</label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
            />
          </div>

          {!user && (
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Temporary Password *
              </label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={form.password}
                  onChange={(e) =>
                    setForm({ ...form, password: e.target.value })
                  }
                  required
                  minLength={8}
                  placeholder="Min 8 characters"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
                >
                  {showPassword ? (
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
                        d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"
                      />
                    </svg>
                  ) : (
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
                        d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                      />
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                      />
                    </svg>
                  )}
                </button>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                First Name
              </label>
              <input
                type="text"
                value={form.first_name}
                onChange={(e) =>
                  setForm({ ...form, first_name: e.target.value })
                }
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Last Name
              </label>
              <input
                type="text"
                value={form.last_name}
                onChange={(e) =>
                  setForm({ ...form, last_name: e.target.value })
                }
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Role *</label>
              <select
                value={form.account_type}
                onChange={(e) =>
                  setForm({ ...form, account_type: e.target.value })
                }
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              >
                {ROLE_OPTIONS.map((role) => (
                  <option key={role.value} value={role.value}>
                    {role.label}
                  </option>
                ))}
              </select>
            </div>
            {user && (
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Status
                </label>
                <select
                  value={form.status}
                  onChange={(e) => setForm({ ...form, status: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                >
                  {STATUS_OPTIONS.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* Role Description */}
          <div className="bg-gray-800/50 rounded-lg p-3">
            <p className="text-sm text-gray-400">
              <span className="text-white font-medium">
                {ROLE_OPTIONS.find((r) => r.value === form.account_type)?.label}
                :
              </span>{" "}
              {
                ROLE_OPTIONS.find((r) => r.value === form.account_type)
                  ?.description
              }
            </p>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-4 pt-4 border-t border-gray-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-400 hover:text-white"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500"
            >
              {user ? "Save Changes" : "Create User"}
            </button>
          </div>
      </form>
    </Modal>
  );
}

// Reset Password Modal
function ResetPasswordModal({ user, onReset, onClose, saving }) {
  const toast = useToast();
  const [newPassword, setNewPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (newPassword.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    onReset(newPassword);
  };

  const generatePassword = () => {
    const chars =
      "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789!@#$%";
    let password = "";
    for (let i = 0; i < 12; i++) {
      password += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    setNewPassword(password);
    setShowPassword(true);
  };

  return (
    <Modal isOpen={true} onClose={onClose} title="Reset Password" className="w-full max-w-md" disableClose={saving}>
      <div className="p-6 border-b border-gray-800">
        <h2 className="text-xl font-bold text-white">Reset Password</h2>
        <p className="text-gray-400 text-sm mt-1">
          Reset password for {user.email}
        </p>
      </div>

      <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              New Password *
            </label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={8}
                placeholder="Min 8 characters"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white pr-10"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
              >
                {showPassword ? (
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
                      d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"
                    />
                  </svg>
                ) : (
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
                      d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                    />
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                    />
                  </svg>
                )}
              </button>
            </div>
          </div>

          <button
            type="button"
            onClick={generatePassword}
            className="text-sm text-blue-400 hover:text-blue-300"
          >
            Generate random password
          </button>

          <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3">
            <p className="text-yellow-400 text-sm">
              ⚠️ This will invalidate the user's current session. They will need
              to log in again with the new password.
            </p>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-4 pt-4 border-t border-gray-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-400 hover:text-white"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-gradient-to-r from-orange-600 to-red-600 text-white rounded-lg hover:from-orange-500 hover:to-red-500"
            >
              Reset Password
            </button>
          </div>
      </form>
    </Modal>
  );
}
