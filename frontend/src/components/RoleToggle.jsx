function RoleToggle({ role, onChange }) {
  const roles = [
    { value: "customer", label: "Customer" },
    { value: "reviewer", label: "Reviewer" },
  ];

  return (
    <div className="role-toggle inline-flex rounded-xl border border-gray-200 bg-gray-100 p-1" aria-label="Workspace role">
      {roles.map((r) => (
        <button
          key={r.value}
          type="button"
          onClick={() => onChange(r.value)}
          aria-pressed={role === r.value}
          className={`px-3.5 py-2 text-sm font-semibold rounded-lg transition-colors ${
            role === r.value
              ? "bg-white shadow-sm text-emerald-800"
              : "text-gray-500 hover:text-gray-900"
          }`}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
}

export default RoleToggle;
