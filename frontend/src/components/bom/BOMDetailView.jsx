import { useState, useEffect } from "react";
import { useToast } from "../Toast";
import Modal from "../Modal";
import PurchaseRequestModal from "./PurchaseRequestModal";
import WorkOrderRequestModal from "./WorkOrderRequestModal";
import ExplodedBOMView from "./ExplodedBOMView";
import BOMLinesList from "./BOMLinesList";
import BOMAddLineForm from "./BOMAddLineForm";
import BOMRoutingSection from "./BOMRoutingSection";
import BOMCostRollupCard from "./BOMCostRollupCard";
import AddOperationMaterialForm from "./AddOperationMaterialForm";
import useRoutingManager from "./useRoutingManager";
import useBOMLines from "./useBOMLines";

export default function BOMDetailView({
  bom,
  onClose,
  onUpdate,
  onCreateProductionOrder,
}) {
  const toast = useToast();
  const [purchaseLine, setPurchaseLine] = useState(null);
  const [workOrderLine, setWorkOrderLine] = useState(null);
  const showProcessPath = true;

  const routing = useRoutingManager({ bom, toast });
  const bomLines = useBOMLines({ bom, toast, onUpdate });

  // Fetch all initial data on mount
  useEffect(() => {
    bomLines.fetchInitialLineData();
    routing.fetchInitialRoutingData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bom.id, bom.product_id]);

  return (
    <div className="space-y-6">
      {/* BOM Header Info */}
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <span className="text-gray-400">Code:</span>
          <span className="text-white ml-2">{bom.code}</span>
        </div>
        <div>
          <span className="text-gray-400">Version:</span>
          <span className="text-white ml-2">
            {bom.version} ({bom.revision})
          </span>
        </div>
        <div>
          <span className="text-gray-400">Product:</span>
          <span className="text-white ml-2">
            {bom.product_name || bom.product?.name || bom.product_id}
          </span>
        </div>
        <div>
          <span className="text-gray-400">
            {routing.productRouting ? "Material Cost:" : "Total Cost:"}
          </span>
          <span className="text-white ml-2">
            ${parseFloat(bom.total_cost || 0).toFixed(2)}
          </span>
          {routing.productRouting && (
            <>
              <span className="text-gray-400 ml-4">+ Labor:</span>
              <span className="text-amber-400 ml-1">
                ${routing.calculateProcessCost().toFixed(2)}
              </span>
              {routing.calculateOperationMaterialsCost() > 0 && (
                <>
                  <span className="text-gray-400 ml-4">+ Op Materials:</span>
                  <span className="text-blue-400 ml-1">
                    ${routing.calculateOperationMaterialsCost().toFixed(2)}
                  </span>
                </>
              )}
              <span className="text-gray-400 ml-4">= Total:</span>
              <span className="text-green-400 ml-1 font-semibold">
                $
                {(
                  parseFloat(bom.total_cost || 0) +
                  routing.calculateProcessCost() +
                  routing.calculateOperationMaterialsCost()
                ).toFixed(2)}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Cost Rollup Display */}
      <BOMCostRollupCard costRollup={bomLines.costRollup} />

      {/* Actions */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => bomLines.setShowAddLine(true)}
          disabled={bomLines.loading}
          className="px-3 py-1.5 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700 disabled:opacity-50"
        >
          Add Component
        </button>
        <button
          onClick={bomLines.fetchExploded}
          disabled={bomLines.loading}
          className="px-3 py-1.5 bg-purple-600 text-white rounded-lg text-sm hover:bg-purple-700 disabled:opacity-50 flex items-center gap-1"
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
              d="M4 6h16M4 10h16M4 14h16M4 18h16"
            />
          </svg>
          Explode BOM
        </button>
        <button
          onClick={() => onCreateProductionOrder(bom)}
          className="px-3 py-1.5 bg-gradient-to-r from-orange-600 to-amber-600 text-white rounded-lg text-sm hover:from-orange-500 hover:to-amber-500 flex items-center gap-1"
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
              d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
            />
          </svg>
          Create Production Order
        </button>
      </div>

      {/* Routing Materials Precedence Warning */}
      {routing.productRouting && Object.values(routing.operationMaterials).flat().length > 0 && (
        <div className="bg-gradient-to-r from-amber-600/10 to-orange-600/10 border border-amber-500/30 rounded-lg p-4 mb-4">
          <div className="flex items-start gap-3">
            <svg
              className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            <div>
              <h4 className="text-amber-300 font-medium text-sm">Routing Materials Take Precedence</h4>
              <p className="text-amber-200/70 text-xs mt-1">
                This product has materials defined on routing operations. For MRP and production orders,
                <strong className="text-amber-200"> routing materials are used instead of the BOM lines below</strong>.
                Edit operation materials in the <span className="text-amber-300">Manufacturing Operations</span> section above.
              </p>
              <p className="text-amber-200/50 text-xs mt-1">
                BOM lines are only used as a fallback for products without routing materials.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* BOM Lines Table */}
      <BOMLinesList
        lines={bomLines.lines}
        editingLine={bomLines.editingLine}
        setEditingLine={bomLines.setEditingLine}
        uoms={bomLines.uoms}
        onUpdateLine={bomLines.handleUpdateLine}
        onDeleteLine={bomLines.handleDeleteLine}
      />

      <BOMRoutingSection
        showProcessPath={showProcessPath}
        productRouting={routing.productRouting}
        operationMaterials={routing.operationMaterials}
        expandedOperations={routing.expandedOperations}
        setExpandedOperations={routing.setExpandedOperations}
        timeOverrides={routing.timeOverrides}
        showAddOperation={routing.showAddOperation}
        setShowAddOperation={routing.setShowAddOperation}
        showAddOperationToExisting={routing.showAddOperationToExisting}
        setShowAddOperationToExisting={routing.setShowAddOperationToExisting}
        pendingOperations={routing.pendingOperations}
        newOperation={routing.newOperation}
        setNewOperation={routing.setNewOperation}
        workCenters={routing.workCenters}
        routingTemplates={routing.routingTemplates}
        selectedTemplateId={routing.selectedTemplateId}
        setSelectedTemplateId={routing.setSelectedTemplateId}
        applyingTemplate={routing.applyingTemplate}
        savingRouting={routing.savingRouting}
        addingOperation={routing.addingOperation}
        setShowAddMaterialModal={routing.setShowAddMaterialModal}
        handleAddPendingOperation={routing.handleAddPendingOperation}
        handleRemovePendingOperation={routing.handleRemovePendingOperation}
        handleSaveRouting={routing.handleSaveRouting}
        handleApplyTemplate={routing.handleApplyTemplate}
        updateOperationTime={routing.updateOperationTime}
        saveOperationTime={routing.saveOperationTime}
        handleDeleteOperation={routing.handleDeleteOperation}
        handleDeleteMaterial={routing.handleDeleteMaterial}
        handleAddOperationToExisting={routing.handleAddOperationToExisting}
        formatTime={routing.formatTime}
        fetchProductRouting={routing.fetchProductRouting}
        toast={toast}
      />

      {/* Add Line Form */}
      {bomLines.showAddLine && (
        <BOMAddLineForm
          newLine={bomLines.newLine}
          setNewLine={bomLines.setNewLine}
          products={bomLines.products}
          uoms={bomLines.uoms}
          loading={bomLines.loading}
          onAddLine={bomLines.handleAddLine}
          onCancel={() => bomLines.setShowAddLine(false)}
        />
      )}

      <div className="flex justify-end pt-4 border-t border-gray-800">
        <button
          onClick={onClose}
          className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
        >
          Close
        </button>
      </div>

      {/* Purchase Request Modal */}
      <Modal
        isOpen={!!purchaseLine}
        onClose={() => setPurchaseLine(null)}
        title="Create Purchase Request"
        className="w-full max-w-2xl"
      >
        <div className="p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-white">Create Purchase Request</h2>
            <button onClick={() => setPurchaseLine(null)} className="text-gray-400 hover:text-white p-1" aria-label="Close">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          {purchaseLine && (
            <PurchaseRequestModal
              line={purchaseLine}
              onClose={() => setPurchaseLine(null)}
              onSuccess={() => {
                setPurchaseLine(null);
                onUpdate && onUpdate();
              }}
            />
          )}
        </div>
      </Modal>

      {/* Work Order Request Modal */}
      <Modal
        isOpen={!!workOrderLine}
        onClose={() => setWorkOrderLine(null)}
        title="Create Work Order"
        className="w-full max-w-2xl"
      >
        <div className="p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-white">Create Work Order</h2>
            <button onClick={() => setWorkOrderLine(null)} className="text-gray-400 hover:text-white p-1" aria-label="Close">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          {workOrderLine && (
            <WorkOrderRequestModal
              line={workOrderLine}
              onClose={() => setWorkOrderLine(null)}
              onSuccess={() => {
                setWorkOrderLine(null);
                onUpdate && onUpdate();
              }}
            />
          )}
        </div>
      </Modal>

      {/* Add Material to Operation Modal */}
      <Modal
        isOpen={!!routing.showAddMaterialModal}
        onClose={routing.closeMaterialModal}
        title="Add Material to Operation"
        className="w-full max-w-2xl"
      >
        <AddOperationMaterialForm
          newMaterial={routing.newMaterial}
          setNewMaterial={routing.setNewMaterial}
          products={bomLines.products}
          uoms={bomLines.uoms}
          onSubmit={() => routing.handleAddMaterial(routing.showAddMaterialModal)}
          onClose={routing.closeMaterialModal}
        />
      </Modal>

      {/* Exploded BOM View Modal */}
      <Modal
        isOpen={bomLines.showExploded && !!bomLines.explodedData}
        onClose={() => bomLines.setShowExploded(false)}
        title="Exploded BOM View"
        className="w-full max-w-4xl"
      >
        {bomLines.explodedData && (
          <ExplodedBOMView
            explodedData={bomLines.explodedData}
            onClose={() => bomLines.setShowExploded(false)}
          />
        )}
      </Modal>
    </div>
  );
}
