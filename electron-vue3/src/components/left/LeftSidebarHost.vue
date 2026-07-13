<template>
  <div class="left-sidebar-host">
    <PlansPanel
      v-if="activeLeftPanel === 'plans'"
      :planCollapsed="planCollapsed"
      :loading="loading"
      :activePlans="activePlans"
      :selectedPlan="selectedPlan"
      :expandedPlans="expandedPlans"
      :hoveredPlan="hoveredPlan"
      :contextMenu="contextMenu"
      :contextMenuDragActive="contextMenuDragActive"
      :getPlanIcon="getPlanIcon"
      :formatDate="formatDate"
      :onShowCreatePlanModal="showCreatePlanModal"
      :onSelectPlan="selectPlan"
      :onShowPlanActions="showPlanActions"
      :onHidePlanActions="hidePlanActions"
      :onTogglePlanExpansion="togglePlanExpansion"
      :onShowContextMenu="showContextMenu"
      :onContextMenuDragStart="onContextMenuDragStart"
      :onCreateSubPlan="createSubPlan"
      :onCreateSiblingPlan="createSiblingPlan"
      :onEditPlan="editPlan"
      :onArchivePlan="archivePlan"
      :onDeletePlan="deletePlan"
      :onPinPlan="pinPlan"
      :pendingDeletePlanId="pendingDeletePlanId"
      :confirmDelete="confirmDelete"
      :cancelPendingDelete="cancelModify"
      :pendingPlanCreates="pendingPlanCreates"
      :confirmCreate="confirmCreate"
      :cancelCreate="cancelCreate"
      :isLastInCreateCluster="isLastInCreateCluster"
      :getCreateClusterSize="getCreateClusterSize"
      :confirmConsecutiveCreateGroup="confirmConsecutiveCreateGroup"
      :cancelConsecutiveCreateGroup="cancelConsecutiveCreateGroup"
    />

    <SearchPanel
      v-else-if="activeLeftPanel === 'search'"
      :projectId="projectId"
      @close="$emit('closeSearch')"
      @select="$emit('selectSearchResult', $event)"
    />

    <ArchivePanel
      v-else-if="activeLeftPanel === 'archive'"
      :planCollapsed="planCollapsed"
      :loading="loading"
      :archivedPlans="archivedPlans"
      :selectedPlan="selectedPlan"
      :expandedPlans="expandedPlans"
      :hoveredPlan="hoveredPlan"
      :contextMenu="contextMenu"
      :contextMenuDragActive="contextMenuDragActive"
      :getPlanIcon="getPlanIcon"
      :formatDate="formatDate"
      :onSelectPlan="selectPlan"
      :onShowPlanActions="showPlanActions"
      :onHidePlanActions="hidePlanActions"
      :onTogglePlanExpansion="togglePlanExpansion"
      :onShowContextMenu="showContextMenu"
      :onContextMenuDragStart="onContextMenuDragStart"
      :onEditPlan="editPlan"
      :onDeletePlan="deletePlan"
      :onPinPlan="pinPlan"
    />

    <PluginsPanel
      v-else-if="activeLeftPanel === 'plugins'"
      :key="'plugins-panel-v2'"
      :projectId="projectId"
      :selectedPlan="selectedPlan"
      :currentUser="currentUser"
      @action="$emit('pluginAction', $event)"
    />

    <div v-else class="left-sidebar-placeholder">
      <div class="placeholder-title">{{ activeLeftPanel }}</div>
      <div class="placeholder-desc">该面板稍后接入（search/archive/plugins）。</div>
    </div>
  </div>
</template>

<script setup>
import PlansPanel from './PlansPanel.vue'
import SearchPanel from './SearchPanel.vue'
import ArchivePanel from './ArchivePanel.vue'
import PluginsPanel from './PluginsPanel.vue'

defineEmits(['closeSearch', 'selectSearchResult', 'pluginAction'])

defineProps({
  activeLeftPanel: { type: String, default: 'plans' },
  projectId: { type: [String, Number, null], default: null },
  selectedPlan: { type: [String, Number, null], default: null },
  currentUser: { type: Object, default: null },
  planCollapsed: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  activePlans: { type: Array, default: () => [] },
  archivedPlans: { type: Array, default: () => [] },
  expandedPlans: { type: Array, default: () => [] },
  hoveredPlan: { type: [String, Number, null], default: null },
  contextMenu: { type: Object, default: () => ({}) },
  contextMenuDragActive: { type: Boolean, default: false },
  getPlanIcon: { type: Function, required: true },
  formatDate: { type: Function, required: true },
  showCreatePlanModal: { type: Function, required: true },
  selectPlan: { type: Function, required: true },
  showPlanActions: { type: Function, required: true },
  hidePlanActions: { type: Function, required: true },
  togglePlanExpansion: { type: Function, required: true },
  showContextMenu: { type: Function, required: true },
  onContextMenuDragStart: { type: Function, required: true },
  createSubPlan: { type: Function, required: true },
  createSiblingPlan: { type: Function, required: true },
  editPlan: { type: Function, required: true },
  archivePlan: { type: Function, required: true },
  deletePlan: { type: Function, required: true },
  pinPlan: { type: Function, required: true },
  pendingDeletePlanId: { type: [String, Number], default: null },
  confirmDelete: { type: Function, default: null },
  cancelModify: { type: Function, default: null },
  pendingPlanCreates: { type: Array, default: () => [] },
  confirmCreate: { type: Function, default: null },
  cancelCreate: { type: Function, default: null },
  isLastInCreateCluster: { type: Function, default: null },
  getCreateClusterSize: { type: Function, default: null },
  confirmConsecutiveCreateGroup: { type: Function, default: null },
  cancelConsecutiveCreateGroup: { type: Function, default: null }
})
</script>

<style scoped>
.left-sidebar-host {
  height: 100%;
  width: 100%;
}
.left-sidebar-placeholder {
  padding: 12px;
  color: #666;
}
.placeholder-title {
  font-weight: 600;
  margin-bottom: 6px;
}
</style>

