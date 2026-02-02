/**
 * CategoryNode - Recursive tree node for category sidebar.
 */
export default function CategoryNode({
  node,
  expandedCategories,
  selectedCategory,
  toggleExpand,
  setSelectedCategory,
  setEditingCategory,
  setShowCategoryModal,
  handleDeleteCategory,
  depth = 0,
}) {
  const hasChildren = node.children && node.children.length > 0;
  const isExpanded = expandedCategories.has(node.id);
  const isSelected = selectedCategory === node.id;

  return (
    <div>
      <div
        className={`flex items-center group ${
          isSelected
            ? "bg-blue-600/20 text-blue-400 border border-blue-500/30"
            : "text-gray-400 hover:bg-gray-800 hover:text-white"
        } rounded-lg transition-colors`}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
      >
        {/* Expand/collapse button */}
        {hasChildren ? (
          <button
            onClick={() => toggleExpand(node.id)}
            className="p-1 hover:text-white flex-shrink-0"
          >
            <svg
              className={`w-3 h-3 transition-transform ${
                isExpanded ? "rotate-90" : ""
              }`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5l7 7-7 7"
              />
            </svg>
          </button>
        ) : (
          <span className="w-5 flex-shrink-0" />
        )}

        {/* Category name */}
        <button
          onClick={() => setSelectedCategory(node.id)}
          className="flex-1 text-left py-2 text-sm truncate"
          title={node.name}
        >
          <span
            className={`${!node.is_active ? "line-through opacity-50" : ""}`}
          >
            {node.name}
          </span>
          {node.item_count > 0 && (
            <span className="text-xs text-gray-600 ml-1">
              ({node.item_count})
            </span>
          )}
        </button>

        {/* Actions */}
        <div className="flex gap-1 opacity-0 group-hover:opacity-100 pr-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setEditingCategory({
                id: node.id,
                code: node.code,
                name: node.name,
                description: node.description || "",
                parent_id: node.parent_id,
                sort_order: node.sort_order || 0,
                is_active: node.is_active,
              });
              setShowCategoryModal(true);
            }}
            className="text-gray-500 hover:text-blue-400 p-1"
            title="Edit category"
          >
            <svg
              className="w-3 h-3"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
              />
            </svg>
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleDeleteCategory(node);
            }}
            className="text-gray-500 hover:text-red-400 p-1"
            title="Delete category"
          >
            <svg
              className="w-3 h-3"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* Children */}
      {hasChildren && isExpanded && (
        <div>
          {node.children.map((child) => (
            <CategoryNode
              key={child.id}
              node={child}
              expandedCategories={expandedCategories}
              selectedCategory={selectedCategory}
              toggleExpand={toggleExpand}
              setSelectedCategory={setSelectedCategory}
              setEditingCategory={setEditingCategory}
              setShowCategoryModal={setShowCategoryModal}
              handleDeleteCategory={handleDeleteCategory}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}
