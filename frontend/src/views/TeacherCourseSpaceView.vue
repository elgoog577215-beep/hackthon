<template>
  <main class="file-space" :class="{ 'file-space--embedded': embedded }">
    <header v-if="!embedded" class="standalone-header">
      <div><small>{{ t('courseFiles.spaceLabel') }}</small><h1>{{ courseTitle || t('courseFiles.allCourseFiles') }}</h1></div>
      <nav class="workspace-view-switch" :aria-label="t('courseFiles.views.label')">
        <button type="button" :class="{ active: workspaceView === 'categories' }" @click="setWorkspaceView('categories')">
          <LayoutGrid :size="15" />{{ t('courseFiles.views.categories') }}
        </button>
        <button type="button" :class="{ active: workspaceView === 'files' }" @click="setWorkspaceView('files')">
          <FolderTree :size="15" />{{ t('courseFiles.views.files') }}
        </button>
      </nav>
      <div class="standalone-header-actions">
        <div class="list-search" role="search">
          <Search :size="15" />
          <input v-model="query" type="search" :placeholder="t('courseFiles.searchCurrent')" :aria-label="t('courseFiles.searchCurrent')" />
          <button v-if="query" type="button" :aria-label="t('courseFiles.clearSearch')" @click="query = ''"><X :size="14" /></button>
        </div>
        <button type="button" @click="router.push({ name: 'course-library' })"><ArrowLeft :size="16" />{{ t('courseFiles.backToCalendar') }}</button>
      </div>
    </header>

    <section v-if="initializing" class="space-state" role="status"><LoaderCircle class="spin" :size="22" />{{ t('courseFiles.preparingSpace') }}</section>
    <section v-else-if="!selected" class="space-state is-error" role="alert">
      <TriangleAlert :size="22" /><strong>{{ t('courseFiles.spaceUnavailable') }}</strong><span>{{ status }}</span>
      <button type="button" @click="refresh">{{ t('common.retry') }}</button>
    </section>

    <section v-else class="workspace-ready">
      <section v-if="workspaceView === 'files'" class="file-layout">
      <aside class="file-tree-pane">
        <header class="pane-heading">
          <span><FolderTree :size="15" /><strong>{{ t('courseFiles.folderNavigation') }}</strong></span>
          <button type="button" :aria-label="t('common.refresh')" @click="reloadAll"><RefreshCw :size="15" :class="{ spin: busy }" /></button>
        </header>
        <nav class="folder-navigation" :aria-label="t('courseFiles.folderNavigation')">
          <ul role="tree">
            <WorkspaceFolderTreeNode
              v-for="folder in folderTreeData"
              :key="folder.id"
              :node="folder"
              :current-id="currentFolderId"
              :expanded-ids="expandedFolderIds"
              @select="openFolder"
              @toggle="toggleFolder"
            />
          </ul>
        </nav>
        <footer>
          <span>{{ selected.academic_year }} · {{ termLabel(selected.term) }}</span>
          <button type="button" @click="downloadPackage"><Download :size="14" />{{ t('courseFiles.exportCourse') }}</button>
        </footer>
      </aside>

      <section
        class="file-list-pane"
        :class="{ 'is-dragging-files': fileDragActive }"
        @dragenter.prevent="handleFileDragEnter"
        @dragover.prevent
        @dragleave.prevent="handleFileDragLeave"
        @drop.prevent="handleFileDrop"
      >
        <header v-if="breadcrumbs.length" class="list-toolbar">
          <nav :aria-label="t('courseFiles.filePath')">
            <button type="button" @click="openFolder('root')"><Home :size="14" />{{ t('courseFiles.rootName') }}</button>
            <template v-for="crumb in breadcrumbs" :key="crumb.id">
              <ChevronRight :size="13" /><button type="button" @click="openFolder(crumb.id)">{{ crumb.label }}</button>
            </template>
          </nav>
        </header>

        <div class="folder-title">
          <h2>{{ currentListTitle }}</h2>
          <div class="folder-title__actions">
            <span>{{ t('courseFiles.itemCount').replace('{count}', String(filteredChildren.length)) }}</span>
            <button v-if="canBatchImport && !query.trim()" class="batch-import-button" type="button" :disabled="busy" @click="batchFileInput?.click()"><Upload :size="14" />{{ t('courseFiles.importMaterials') }}</button>
            <button v-if="canBatchImport && !query.trim()" class="import-folder-button" type="button" :disabled="busy" :title="t('courseFiles.importFolder')" :aria-label="t('courseFiles.importFolder')" @click="batchFolderInput?.click()"><FolderInput :size="15" /></button>
            <button v-if="canAddTeacherFiles && !query.trim()" class="add-material-button" type="button" @click="openCreateDialog('material', '', currentFolder?.id)"><Plus :size="14" />{{ t('courseFiles.addMaterial') }}</button>
            <button v-if="canAddTeacherFiles && !query.trim()" class="add-folder-button" type="button" :title="t('courseFiles.newFolder')" :aria-label="t('courseFiles.newFolder')" @click="openCreateDialog('folder', '', currentFolder?.id)"><FolderPlus :size="15" /></button>
          </div>
        </div>

        <div v-if="fileDragActive" class="file-drop-overlay" role="status">
          <span><UploadCloud :size="24" /></span>
          <strong>{{ t('courseFiles.dropToImport').replace('{folder}', batchImportLocation) }}</strong>
        </div>

        <div class="file-table" role="table" :aria-label="t('courseFiles.fileList')">
          <div class="file-table__head" role="row">
            <span v-for="column in sortColumns" :key="column.key" role="columnheader" :aria-sort="sortAria(column.key)">
              <button type="button" class="sort-button" :class="{ active: sortKey === column.key }" :aria-label="t('courseFiles.sortBy').replace('{name}', column.label)" @click="toggleSort(column.key)">
                {{ column.label }}
                <component :is="sortIcon(column.key)" :size="14" />
              </button>
            </span>
          </div>
          <button
            v-for="node in filteredChildren"
            :key="node.id"
            type="button"
            class="file-row"
            :class="{ selected: selectedNode?.id === node.id }"
            :data-role="assetRole(node)"
            role="row"
            @click="handleNodeClick(node)"
            @dblclick="node.kind !== 'folder' && primaryAction(node)"
            @contextmenu.prevent="openFileContextMenu($event, node)"
            @keydown="handleFileRowKeydown($event, node)"
          >
            <span class="file-name" role="cell">
              <span class="file-icon" :data-type="node.type"><component :is="node.kind === 'folder' ? Folder : nodeIcon(node)" :size="18" /></span>
              <span class="file-name__copy">
                <strong>{{ node.label }}</strong>
                <small v-if="node.description || query.trim()">{{ node.description || displayPath(node.path) }}</small>
              </span>
            </span>
            <span role="cell">{{ displayUpdated(node) }}</span>
            <span role="cell">{{ typeLabel(node) }}</span>
            <span role="cell">{{ displaySize(node) }}</span>
            <span role="cell"><i class="status-dot" :data-state="node.status" />{{ statusLabel(node) }}</span>
          </button>
          <div v-if="!filteredChildren.length" class="file-empty">
            <template v-if="query.trim()">
              <SearchX :size="27" /><strong>{{ t('courseFiles.noSearchResults') }}</strong>
              <button type="button" @click="query = ''"><X :size="14" />{{ t('courseFiles.clearSearch') }}</button>
            </template>
            <template v-else>
              <FolderOpen :size="27" /><strong>{{ emptyFolderTitle }}</strong>
            </template>
          </div>
        </div>
        <p v-if="status" class="runtime-note" role="status">{{ status }}</p>
      </section>

      <aside class="file-inspector">
        <template v-if="inspectedNode">
          <header>
            <span class="inspector-icon" :data-type="inspectedNode.type"><component :is="inspectedNode.kind === 'folder' ? FolderOpen : nodeIcon(inspectedNode)" :size="22" /></span>
            <div><small v-if="typeLabel(inspectedNode) !== inspectedNode.label">{{ typeLabel(inspectedNode) }}</small><strong>{{ inspectedNode.label }}</strong></div>
            <button v-if="selectedNode" type="button" :aria-label="t('common.close')" @click="selectedNode = null"><X :size="15" /></button>
          </header>
          <section class="inspector-status" :data-state="inspectedNode.status">
            <span><i />{{ statusLabel(inspectedNode) }}</span>
          </section>
          <section class="inspector-overview">
            <dl>
              <div><dt>{{ t('courseFiles.meta.role') }}</dt><dd>{{ fileRoleLabel(inspectedNode) }}</dd></div>
              <div><dt>{{ t('courseFiles.meta.source') }}</dt><dd>{{ fileSourceLabel(inspectedNode) }}</dd></div>
              <div v-if="inspectedNode.kind === 'folder'"><dt>{{ t('courseFiles.meta.items') }}</dt><dd>{{ folderSummary(inspectedNode) }}</dd></div>
              <div v-if="inspectedNode.kind === 'folder'"><dt>{{ t('courseFiles.meta.updated') }}</dt><dd>{{ folderUpdatedLabel(inspectedNode) }}</dd></div>
              <div v-if="inspectedNode.lessonId"><dt>{{ t('courseFiles.meta.lesson') }}</dt><dd>{{ lessonLabel(inspectedNode.lessonId) }}</dd></div>
              <div v-if="inspectedNode.revision"><dt>{{ t('courseFiles.meta.version') }}</dt><dd :title="inspectedNode.revision">{{ shortRevision(inspectedNode.revision) }}</dd></div>
              <div v-if="inspectedNode.asset"><dt>{{ t('courseFiles.meta.recognizedType') }}</dt><dd>
                <select class="asset-type-select" :value="inspectedNode.asset.document_type || 'other'" :disabled="classifyingAssetId === inspectedNode.asset.asset_id" @change="updateAssetDocumentType(inspectedNode.asset, $event)">
                  <option v-for="option in documentTypeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
                </select>
              </dd></div>
              <div v-if="inspectedNode.kind === 'folder'"><dt>{{ t('courseFiles.meta.location') }}</dt><dd>{{ displayPath(inspectedNode.path) }}</dd></div>
            </dl>
            <section v-if="inspectedNode.kind === 'managed'" class="relationship-list">
              <h3>{{ t('courseFiles.inspector.parentSource') }}</h3>
              <div v-for="link in inspectedPrimarySourceLinks" :key="link.link_id">
                <Link2 :size="14" />
                <span><strong>{{ link.source_label }}</strong><small>{{ t('courseFiles.inspector.teacherOriginal') }}</small></span>
              </div>
              <span v-if="!inspectedPrimarySourceLinks.length" class="relationship-empty">—</span>
            </section>
            <section v-if="inspectedNode.kind === 'managed'" class="relationship-list">
              <h3>{{ t('courseFiles.inspector.referenceOriginals') }}</h3>
              <div v-for="link in inspectedReferenceSourceLinks" :key="link.link_id">
                <Link2 :size="14" />
                <span><strong>{{ link.source_label }}</strong><small>{{ relationshipRoleLabel(link.role) }}</small></span>
              </div>
              <span v-if="!inspectedReferenceSourceLinks.length" class="relationship-empty">—</span>
            </section>
            <section v-if="inspectedNode.asset" class="relationship-list">
              <h3>{{ t('courseFiles.inspector.usedBy', '用于') }}</h3>
              <button v-for="link in inspectedUsageLinks" :key="link.link_id" type="button" @click="revealRelationshipTarget(link)">
                <Link2 :size="14" />
                <span><strong>{{ link.target_label }}</strong><small>{{ formalTypeLabel(link.target_type) }}</small></span>
              </button>
              <span v-if="!inspectedUsageLinks.length" class="relationship-empty">—</span>
            </section>
          </section>
          <footer v-if="inspectorHasActions(inspectedNode)" class="inspector-actions">
            <button v-if="selectedNode" class="primary" type="button" :disabled="busy || primaryDisabled(selectedNode)" @click="primaryAction(selectedNode)">
              <LoaderCircle v-if="busy" :size="15" class="spin" /><component :is="primaryIcon(selectedNode)" v-else :size="15" />{{ primaryLabel(selectedNode) }}
            </button>
            <button v-if="!selectedNode && inspectedNode.type === 'root'" class="primary" type="button" @click="downloadPackage"><Download :size="15" />{{ t('courseFiles.exportCourse') }}</button>
            <button v-else-if="!selectedNode && inspectorMaterialFolder(inspectedNode)" class="primary" type="button" @click="openInspectorCreate(inspectedNode, 'material')"><Plus :size="15" />{{ t('courseFiles.addMaterial') }}</button>
            <div v-if="selectedNode?.asset || selectedNode && canExportManaged(selectedNode) || !selectedNode && inspectorMaterialFolder(inspectedNode)" class="inspector-actions__secondary">
              <button v-if="selectedNode?.asset" type="button" @click="downloadAsset(selectedNode.asset)"><Download :size="14" />{{ t('courseFiles.download') }}</button>
              <button v-else-if="selectedNode && canExportManaged(selectedNode)" type="button" :disabled="exportingNodeId === selectedNode.id" @click="exportManagedNode(selectedNode)"><LoaderCircle v-if="exportingNodeId === selectedNode.id" :size="14" class="spin" /><Download v-else :size="14" />{{ t('courseFiles.exportFile') }}</button>
              <button v-if="!selectedNode && inspectorMaterialFolder(inspectedNode)" type="button" @click="openInspectorCreate(inspectedNode, 'folder')"><FolderPlus :size="14" />{{ t('courseFiles.newFolder') }}</button>
            </div>
            <button v-if="selectedNode?.asset" class="danger" type="button" @click="deleteAsset(selectedNode.asset)"><Trash2 :size="14" />{{ t('courseFiles.delete') }}</button>
          </footer>
        </template>
      </aside>
      </section>

      <section v-else class="category-layout">
        <aside class="category-navigation">
          <header>
            <strong>{{ t('courseFiles.categories.title') }}</strong>
          </header>
          <section class="category-progress" :aria-label="t('courseFiles.workbench.progressLabel')">
            <div>
              <span>{{ t('courseFiles.workbench.progressLabel') }}</span>
              <strong>{{ completedCategoryStages }}/{{ categoryGroups.length }}</strong>
            </div>
            <span
              class="category-progress__track"
              role="progressbar"
              :aria-valuenow="completedCategoryStages"
              :aria-valuemax="categoryGroups.length"
              aria-valuemin="0"
            ><i :style="{ transform: `scaleX(${categoryProgressPercent / 100})` }" /></span>
          </section>
          <nav :aria-label="t('courseFiles.categories.title')">
            <div
              v-for="group in categoryGroups"
              :key="group.type"
              class="category-group"
              :class="{ active: selectedCategory === group.type }"
            >
              <button
                type="button"
                class="category-group__button"
                :class="{ active: selectedCategory === group.type }"
                :aria-expanded="categoryHasChildren(group) ? selectedCategory === group.type : undefined"
                @click="selectCategory(group)"
              >
                <span class="category-group__step">{{ String(group.step).padStart(2, '0') }}</span>
                <component :is="group.icon" :size="17" />
                <span class="category-group__copy">
                  <strong>{{ group.label }}</strong>
                </span>
                <span class="category-group__trailing">
                  <b :data-state="categoryState(group)">{{ categoryCountLabel(group) }}</b>
                  <ChevronRight v-if="categoryHasChildren(group)" :size="14" class="category-group__chevron" />
                </span>
              </button>

              <div v-if="selectedCategory === group.type && categoryHasChildren(group)" class="category-children" role="group" :aria-label="group.label">
                <button
                  v-for="node in group.items"
                  :key="node.id"
                  type="button"
                  class="category-child"
                  :class="{ active: categoryDetailNode?.id === node.id }"
                  @click="selectCategoryNode(node)"
                >
                  <span class="category-child__index">{{ lessonNumber(node.lessonId) }}</span>
                  <span class="category-child__name">{{ lessonLabel(node.lessonId || '') }}</span>
                  <i class="status-dot" :data-state="node.status" />
                </button>
              </div>
            </div>
          </nav>
        </aside>

        <section class="category-detail-pane">
          <header class="category-detail-header">
            <div>
              <small v-if="categoryDetailNode?.lessonId">{{ activeCategory?.label }} · {{ t('courseFiles.lessonLevel') }}</small>
              <h2>{{ categoryDetailTitle }}</h2>
              <span v-if="categoryDetailNode" class="category-detail-status"><i class="status-dot" :data-state="categoryDetailNode.status" />{{ statusLabel(categoryDetailNode) }}</span>
            </div>
            <div v-if="categoryDetailNode && categoryDetailMarkdown" class="category-detail-actions">
              <button type="button" class="primary" :disabled="busy || primaryDisabled(categoryDetailNode)" @click="primaryAction(categoryDetailNode)">
                <LoaderCircle v-if="busy" :size="15" class="spin" /><component :is="primaryIcon(categoryDetailNode)" v-else :size="15" />{{ primaryLabel(categoryDetailNode) }}
              </button>
              <button v-if="canExportManaged(categoryDetailNode)" type="button" :disabled="exportingNodeId === categoryDetailNode.id" @click="exportManagedNode(categoryDetailNode)">
                <LoaderCircle v-if="exportingNodeId === categoryDetailNode.id" :size="14" class="spin" /><Download v-else :size="14" />{{ t('courseFiles.exportFile') }}
              </button>
            </div>
          </header>

          <section class="workbench-brief-bar" :aria-label="t('courseFiles.workbench.settingsTitle')">
            <div class="workbench-brief-bar__title">
              <span><SlidersHorizontal :size="16" /></span>
              <div><strong>{{ t('courseFiles.workbench.settingsTitle') }}</strong></div>
            </div>
            <div class="workbench-brief-items">
              <button v-for="item in productionContextItems" :key="item.label" type="button" :title="item.title || item.value" @click="emit('editBaseline')">
                <span>{{ item.label }}</span><strong :data-empty="item.empty || undefined">{{ item.value }}</strong>
              </button>
            </div>
            <div class="workbench-brief-actions">
              <button type="button" class="workbench-edit-baseline" @click="emit('editBaseline')"><Pencil :size="14" />{{ t('courseFiles.workbench.adjustSettings') }}</button>
              <button type="button" class="workbench-settings-button" @click="emit('openAssistant'); emit('discussBaseline')"><Sparkles :size="14" />{{ t('courseFiles.workbench.discussWithAi') }}</button>
            </div>
          </section>

          <div v-if="categoryDetailNode && categoryDetailMarkdown" class="category-document-scroll">
            <article class="category-document" :aria-label="categoryDetailTitle">
              <MarkdownRenderer :content="categoryDetailMarkdown" :enable-code-run="false" />
            </article>
          </div>
          <div v-else class="category-console">
            <section class="category-console__card">
              <header>
                <span class="category-console__icon"><component :is="activeCategory?.icon || FileText" :size="24" /></span>
              </header>
              <h3>{{ categoryConsoleTitle }}</h3>
              <section v-if="!categoryDetailNode && activeCategory?.type !== 'outline'" class="category-prerequisite">
                <FileText :size="17" />
                <div><strong>{{ t('courseFiles.workbench.completeOutlineFirst') }}</strong></div>
              </section>
              <div class="category-console__actions">
                <button type="button" class="primary" :disabled="busy || Boolean(categoryDetailNode && primaryDisabled(categoryDetailNode))" @click="startActiveCategory">
                  <component :is="categoryDetailNode ? primaryIcon(categoryDetailNode) : Pencil" :size="15" />{{ categoryConsoleActionLabel }}
                </button>
                <button type="button" @click="emit('openAssistant')"><Sparkles :size="15" />{{ t('courseFiles.workbench.discussRequirements') }}</button>
              </div>
            </section>
          </div>
        </section>
      </section>
    </section>

    <input ref="importInput" class="sr-only" type="file" @change="captureImportFile" />
    <input ref="batchFileInput" class="sr-only" type="file" multiple @change="captureBatchSelection($event, false)" />
    <input ref="batchFolderInput" class="sr-only" type="file" multiple webkitdirectory @change="captureBatchSelection($event, true)" />
    <Teleport to="body">
      <div v-if="createOpen" class="asset-create-overlay" role="presentation" @click.self="closeCreateDialog" @keydown.esc="closeCreateDialog">
        <section ref="createDialog" class="asset-create-dialog" role="dialog" aria-modal="true" :aria-labelledby="'asset-create-title'" tabindex="-1">
          <header class="asset-create-header"><strong id="asset-create-title">{{ dialogTitle }}</strong><button type="button" :aria-label="t('common.close')" @click="closeCreateDialog"><X :size="17" /></button></header>
          <div class="create-location"><FolderOpen :size="15" /><span>{{ t('courseFiles.form.saveTo') }}</span><strong>{{ createLocationLabel }}</strong></div>
          <form class="asset-form" @submit.prevent="submitCreate">
        <label v-if="needsLesson" class="form-field">
          <span>{{ t('courseFiles.form.lesson') }}</span>
          <select v-model="createForm.lessonId" required>
            <option value="" disabled>{{ t('courseFiles.form.selectLesson') }}</option>
            <option v-for="lesson in lessons" :key="lesson.lesson_unit_id" :value="lesson.lesson_unit_id">{{ lesson.number }}. {{ lesson.title }}</option>
          </select>
        </label>
        <label v-if="['material', 'folder'].includes(createType)" class="form-field">
          <span>{{ createType === 'folder' ? t('courseFiles.form.folderName') : t('courseFiles.form.fileName') }}</span>
          <input v-model.trim="createForm.title" required :placeholder="createType === 'folder' ? t('courseFiles.form.folderPlaceholder') : t('courseFiles.form.materialPlaceholder')" />
        </label>
        <div v-if="createType === 'lesson_plan'" class="form-grid">
          <label class="form-field"><span>{{ t('courseFiles.form.classHours') }}</span><select v-model="createForm.hours"><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4">4</option></select></label>
          <label class="form-field"><span>{{ t('courseFiles.form.generationMode') }}</span><select v-model="createForm.mode"><option value="ai">{{ t('courseFiles.form.aiGenerate') }}</option><option value="import">{{ t('courseFiles.form.importFile') }}</option></select></label>
        </div>
        <section v-if="createType === 'ppt'" class="ppt-origin-picker">
          <span>{{ t('courseFiles.form.pptOrigin') }}</span>
          <div>
            <button type="button" :class="{ active: createForm.mode === 'ai' }" @click="createForm.mode = 'ai'; createForm.file = null">
              <Sparkles :size="15" /><strong>{{ t('courseFiles.form.pptGenerated') }}</strong>
            </button>
            <button type="button" :class="{ active: createForm.mode === 'import' }" @click="createForm.mode = 'import'; createForm.file = null">
              <Upload :size="15" /><strong>{{ t('courseFiles.form.pptUploaded') }}</strong>
            </button>
          </div>
        </section>
        <div v-if="createType === 'ppt' && createForm.mode === 'ai'" class="form-grid">
          <label class="form-field"><span>{{ t('courseFiles.form.slideCount') }}</span><input v-model.number="createForm.count" type="number" min="4" max="80" /></label>
          <label class="form-field"><span>{{ t('courseFiles.form.style') }}</span><select v-model="createForm.style"><option value="simple">{{ t('courseFiles.form.simpleTeaching') }}</option><option value="template">{{ t('courseFiles.form.followTemplate') }}</option></select></label>
        </div>
        <label v-if="createType === 'ppt' && createForm.mode === 'import'" class="form-field">
          <span>{{ t('courseFiles.form.afterUpload') }}</span>
          <select v-model="createForm.pptImportAction">
            <option value="derive_plan">{{ t('courseFiles.form.derivePlanFromPpt') }}</option>
            <option value="store">{{ t('courseFiles.form.storePptOnly') }}</option>
          </select>
        </label>
        <section v-if="createType === 'practice'" class="practice-create-note">
          <ListChecks :size="16" />
          <strong>{{ t('courseFiles.form.practiceScopeTitle') }}</strong>
        </section>
        <section v-if="pptAiBlocked" class="create-prerequisite" role="status">
          <TriangleAlert :size="16" />
          <strong>{{ t('courseFiles.form.pptNeedsPlanTitle') }}</strong>
          <button type="button" @click="createLessonPlanFirst">{{ t('courseFiles.form.createPlanFirst') }}</button>
        </section>
        <label v-if="!['folder', 'outline', 'practice'].includes(createType)" class="form-field">
          <span>{{ t('courseFiles.form.requirements') }}</span>
          <textarea v-model.trim="createForm.requirements" rows="3" :placeholder="requirementsPlaceholder" />
        </label>
        <section v-if="!['folder', 'practice'].includes(createType) && (createType !== 'ppt' || createForm.mode === 'import' || createForm.style === 'template')" class="source-picker">
          <span>{{ sourceFileLabel }}</span>
          <button type="button" @click="importInput?.click()"><Upload :size="14" />{{ createForm.file?.name || t('courseFiles.form.chooseFile') }}</button>
        </section>
            <footer class="dialog-actions">
              <button type="button" @click="closeCreateDialog">{{ t('common.cancel') }}</button>
              <button class="primary" type="submit" :disabled="submitDisabled"><LoaderCircle v-if="busy" class="spin" :size="15" />{{ submitLabel }}</button>
            </footer>
          </form>
        </section>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="fileContextMenu.node"
        ref="fileContextMenuElement"
        class="file-context-menu"
        role="menu"
        :aria-label="t('courseFiles.contextMenu')"
        :style="{ left: `${fileContextMenu.x}px`, top: `${fileContextMenu.y}px` }"
        tabindex="-1"
        @keydown.esc="closeFileContextMenu"
      >
        <button type="button" role="menuitem" @click="runFileContextAction('primary')"><component :is="primaryIcon(fileContextMenu.node)" :size="15" />{{ primaryLabel(fileContextMenu.node) }}</button>
        <button v-if="fileContextMenu.node.asset" type="button" role="menuitem" @click="runFileContextAction('download')"><Download :size="15" />{{ t('courseFiles.download') }}</button>
        <button v-else-if="canExportManaged(fileContextMenu.node)" type="button" role="menuitem" @click="runFileContextAction('export')"><Download :size="15" />{{ t('courseFiles.exportFile') }}</button>
        <span v-if="fileContextMenu.node.asset" />
        <button v-if="fileContextMenu.node.asset" class="danger" type="button" role="menuitem" @click="runFileContextAction('delete')"><Trash2 :size="15" />{{ t('courseFiles.delete') }}</button>
      </div>
    </Teleport>

    <el-dialog v-model="previewOpen" :title="previewAsset?.filename || t('courseFiles.preview')" :width="previewDialogWidth" top="4vh" destroy-on-close @closed="closePreview">
      <div class="preview-surface">
        <img v-if="previewKind === 'image'" :src="previewUrl" :alt="previewAsset?.filename" />
        <iframe v-else-if="previewKind === 'browser'" :src="previewUrl" :title="previewAsset?.filename" />
        <div v-else class="office-note"><FileText :size="28" /><strong>{{ t('courseFiles.officeSaved') }}</strong><button type="button" @click="previewAsset && downloadAsset(previewAsset)">{{ t('courseFiles.downloadOriginal') }}</button></div>
      </div>
    </el-dialog>
  </main>
</template>

<script setup lang="ts">
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, ref, watch, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowDown, ArrowLeft, ArrowUp, ArrowUpDown, BookOpen, BookOpenText, CalendarDays, ChevronRight, ClipboardList, Download, Eye,
  FileCheck2, FileText, Folder, FolderInput, FolderOpen, FolderPlus, FolderTree, Home, ListChecks, LoaderCircle,
  LayoutGrid, Link2, Pencil, Plus, Presentation, RefreshCw, Search, SearchX, SlidersHorizontal, Sparkles, Trash2, TriangleAlert, Upload, UploadCloud, X,
} from 'lucide-vue-next'
import { activeLocale, t } from '../shared/i18n'
import type { CourseGenerationOptions } from '../shared/prompt-config'
import { useCourseStore, type Node } from '../stores/course'
import { useTeacherLessonAuthoringStore, type TeacherLessonProjection } from '../stores/teacherLessonAuthoring'
import { useTeachingCalendarStore } from '../stores/teachingCalendar'
import http, { teacherRequestConfig } from '../utils/http'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import WorkspaceFolderTreeNode from '../components/WorkspaceFolderTreeNode.vue'

type DocumentType = 'outline' | 'lesson_plan' | 'script' | 'ppt' | 'question_bank' | 'school_material' | 'other'
type Asset = { asset_id: string; filename: string; relative_path: string; extension: string; size_bytes: number; category: string; document_type?: DocumentType; material_asset_id?: string; uploaded_at?: string; updated_at?: string }
type FileRelationship = { link_id: string; source_asset_id: string; source_label: string; target_id: string; target_type: string; target_label: string; role: 'primary' | 'reference' | 'question_source' }
type Package = { package_id: string; course_id?: string; course_name: string; academic_year: string; term: string; asset_count: number; assets: Asset[]; relationships?: FileRelationship[]; entries: Array<{ name: string; path?: string; kind: 'folder' }>; preparation_status?: 'pending' | 'review' | 'completed' | 'skipped'; updated_at?: string }
type CompanionDocument = { document_id: string; template_id: string; document_type: string; title: string; status: string; revision_id: string; revision_number: number; rendered_markdown: string; updated_at?: string }
type NodeKind = 'folder' | 'managed' | 'asset'
type NodeType = 'root' | 'deliverables' | 'course_logic' | 'supporting_materials' | 'outline_export' | 'lesson_plans' | 'script_ppt' | 'question_bank_files' | 'question_practices' | 'aux_question_bank' | 'aux_exam_papers' | 'aux_student_work' | 'aux_other' | 'exam_papers' | 'outline' | 'teaching_calendar' | 'lesson' | 'lesson_plan' | 'content' | 'material' | 'ppt' | 'practice' | 'question_bank' | 'exam_paper' | 'companion_documents' | 'companion_document' | 'folder' | 'file'
type NodeStatus = 'ready' | 'draft' | 'missing' | 'working' | 'stale' | 'uploaded' | 'empty'
type WorkspaceNode = {
  id: string; label: string; kind: NodeKind; type: NodeType; path: string; status: NodeStatus;
  lessonId?: string; revision?: string; updatedAt?: string; sizeBytes?: number; asset?: Asset; companionDocument?: CompanionDocument; children?: WorkspaceNode[]; parentId?: string; origin?: 'generated' | 'uploaded'; order?: number; description?: string
}
type WorkspaceFolderTreeItem = { id: string; label: string; attention?: boolean; children?: WorkspaceFolderTreeItem[] }
type CreateType = 'outline' | 'lesson_plan' | 'material' | 'ppt' | 'practice' | 'folder'
type SortKey = 'name' | 'updated' | 'type' | 'size' | 'status'
type SortDirection = 'ascending' | 'descending'
type WorkspaceView = 'files' | 'categories'
type CategoryType = 'outline' | 'lesson_plan' | 'practice' | 'content' | 'ppt'
type CategoryGroup = {
  type: CategoryType
  step: number
  label: string
  description: string
  icon: Component
  items: WorkspaceNode[]
  ready: number
  working: number
  attention: number
}
type BatchImportFile = { file: File; relativePath: string }
type FileContextAction = 'primary' | 'download' | 'export' | 'delete'

const props = withDefaults(defineProps<{
  embedded?: boolean
  courseId?: string
  courseTitle?: string
  workspaceView?: WorkspaceView
  query?: string
  generationOptions?: CourseGenerationOptions
}>(), { embedded: false, courseId: '', courseTitle: '' })
const emit = defineEmits<{
  (event: 'openOutline'): void
  (event: 'createOutline'): void
  (event: 'openTeachingCalendar'): void
  (event: 'openTeachingPlan', lessonId: string): void
  (event: 'openTasks'): void
  (event: 'openPractice', lessonId: string): void
  (event: 'openScript', lessonId: string): void
  (event: 'openPpt', lessonId: string): void
  (event: 'openQuestionBank'): void
  (event: 'openCompanionDocuments'): void
  (event: 'openAssistant'): void
  (event: 'editBaseline'): void
  (event: 'discussBaseline'): void
  (event: 'contextChange', context: { lessonId: string; nodeId: string; label: string; type: NodeType; path: string }): void
  (event: 'readinessChange', summary: { required: number; ready: number; pending: number }): void
  (event: 'update:workspaceView', value: WorkspaceView): void
  (event: 'update:query', value: string): void
}>()
const route = useRoute()
const router = useRouter()
const courseStore = useCourseStore()
const lessonStore = useTeacherLessonAuthoringStore()
const calendarStore = useTeachingCalendarStore()
const embedded = computed(() => props.embedded)
const courseTitle = computed(() => props.courseTitle)
const selected = ref<Package | null>(null)
const initializing = ref(true)
const busy = ref(false)
const exportingNodeId = ref('')
const status = ref('')
const currentFolderId = ref('root')
const expandedFolderIds = ref<string[]>(['root'])
const selectedNode = ref<WorkspaceNode | null>(null)
const localQuery = ref('')
const query = computed({
  get: () => props.query ?? localQuery.value,
  set: (value: string) => {
    if (props.query === undefined) localQuery.value = value
    emit('update:query', value)
  },
})
const sortKey = ref<SortKey>('name')
const sortDirection = ref<SortDirection>('ascending')
const localWorkspaceView = ref<WorkspaceView>('files')
const workspaceView = computed(() => props.workspaceView ?? localWorkspaceView.value)
const selectedCategory = ref<CategoryType>('outline')
const createOpen = ref(false)
const createType = ref<CreateType>('material')
const createTargetFolderId = ref('')
const importInput = ref<HTMLInputElement>()
const batchFileInput = ref<HTMLInputElement>()
const batchFolderInput = ref<HTMLInputElement>()
const createDialog = ref<HTMLElement>()
const createForm = ref({ lessonId: '', title: '', hours: '2', mode: 'ai', count: 12, style: 'simple', difficulty: 'mixed', requirements: '', pptImportAction: 'derive_plan', file: null as File | null })
const previewOpen = ref(false)
const previewAsset = ref<Asset | null>(null)
const previewUrl = ref('')
const questionBankItems = ref<Array<{ node_id?: string; lifecycle_status?: string }>>([])
const questionBankRevisionId = ref('')
const examPapers = ref<Array<{ paper_id: string; revision_id: string; title: string; item_count: number; total_score: number; duration_minutes: number; updated_at?: string }>>([])
const companionDocuments = ref<CompanionDocument[]>([])
const practiceWorkingLessonIds = ref<string[]>([])
const classifyingAssetId = ref('')
const fileDragActive = ref(false)
const fileDragDepth = ref(0)
const fileContextMenuElement = ref<HTMLElement>()
const fileContextMenu = ref<{ node: WorkspaceNode | null; x: number; y: number }>({ node: null, x: 0, y: 0 })

const lessons = computed<TeacherLessonProjection[]>(() => {
  if (lessonStore.lessons.length) return lessonStore.lessons
  return courseStore.nodes
    .filter(node => node.node_level === 1 || node.parent_node_id === 'root')
    .map((node, index) => ({
      lesson_unit_id: node.node_id,
      number: index + 1,
      title: node.node_name.replace(/^第\s*\d+\s*讲\s*/, ''),
      duration_minutes: Number((node as any).estimated_minutes || 45),
      sections: [],
      arrangement: {
        schema_version: 'teacher_lesson_arrangement_v1',
        revision_id: '',
        lesson_unit_id: node.node_id,
        source_outline_revision_id: '',
        lesson_type: 'theory',
        lesson_type_label: '理论讲授',
        blocks: [],
        status: 'suggested',
        confirmed: false,
        source_state: 'current',
      },
      script: {
        current_revision_id: '', confirmed_revision_id: '', source_lesson_plan_revision_id: '',
        source_state: 'current', ready: false, confirmed: false, confirmed_at: '', sections: [],
      },
      plan: {
        lesson_unit_id: node.node_id,
        working_revision_id: '',
        confirmed_revision_id: '',
        source_state: 'current',
        revisions: [],
        ppt_assets: [],
      },
    }))
})
const termLabel = (term: string) => ({ 春季: t('teacherCourseSpace.terms.spring', '春季'), 秋季: t('teacherCourseSpace.terms.autumn', '秋季'), 夏季: t('teacherCourseSpace.terms.summer', '夏季') }[term] || term)
const safePart = (value: string) => value.replace(/[\\/:*?"<>|]/g, '_').trim()
const localizedError = (error: any, fallback: string) => activeLocale.value === 'zh' && error?.response?.data?.detail ? String(error.response.data.detail) : fallback
const textSize = (value: string) => new TextEncoder().encode(value).byteLength || undefined
const displayPath = (value: string) => {
  if (!value) return t('courseFiles.rootName')
  const labels = activeLocale.value === 'en'
    ? { 教务材料: 'Course administration', 课程逻辑文件: 'Course logic', 辅助资料: 'Supporting materials', 大纲文件: 'Outline file', 教学日历文件: 'Teaching calendar file', 其他教务材料: 'Other administration materials', 大纲: 'Outline', 教案: 'Lesson plans', '讲稿-PPT': 'Scripts & PPTs', 题库: 'Question bank', 分讲练习: 'Session practice', 正式试卷: 'Formal exam papers', 老师题库: 'Teacher question banks', 试卷: 'Exam papers', 学生作业: 'Student work', 其他资料: 'Other materials', 课次: 'Sessions', 讲稿: 'Script', 练习: 'Practice' }
    : { 教务材料: '教务材料', 课程逻辑文件: '课程逻辑文件', 辅助资料: '辅助资料', 大纲文件: '大纲文件', 教学日历文件: '教学日历文件', 其他教务材料: '其他教务材料', 大纲: '大纲', 教案: '教案', '讲稿-PPT': '讲稿-PPT', 题库: '题库', 分讲练习: '分讲练习', 正式试卷: '正式试卷', 老师题库: '老师题库', 试卷: '试卷', 学生作业: '学生作业', 其他资料: '其他资料', 课次: '课次', 讲稿: '讲稿', 练习: '练习' }
  return value.split('/').filter(Boolean).map(part => (labels as Record<string, string>)[part] || part.replace(/^(\d+)_/, '$1 ')).join(' / ')
}

function lessonContentNodes(lesson: TeacherLessonProjection): Node[] {
  const includedIds = new Set([
    lesson.lesson_unit_id,
    ...lesson.sections.map(section => section.section_node_id),
  ])
  const matchingTitle = courseStore.nodes.find(node => (
    node.node_level === 1
    && node.node_name.replace(/^第\s*\d+\s*[讲章节]\s*/, '').trim() === lesson.title.replace(/^第\s*\d+\s*[讲章节]\s*/, '').trim()
  ))
  if (matchingTitle) includedIds.add(matchingTitle.node_id)
  let expanded = true
  while (expanded) {
    expanded = false
    courseStore.nodes.forEach(node => {
      if (!includedIds.has(node.node_id) && includedIds.has(node.parent_node_id)) {
        includedIds.add(node.node_id)
        expanded = true
      }
    })
  }
  return courseStore.nodes.filter(node => includedIds.has(node.node_id))
}

const hasUsableContent = (node: Node) => Boolean(
  node.node_content?.trim()
  || node.content_blocks?.some(block => block.content?.trim())
  || node.course_blocks?.length,
)

function physicalChildren(basePath: string, parentId: string): WorkspaceNode[] {
  const result = new Map<string, WorkspaceNode>()
  const prefix = basePath ? `${basePath}/` : ''
  const knownPaths = [
    ...((selected.value?.entries || []).map(item => item.path || item.name)),
    ...((selected.value?.assets || []).map(item => item.relative_path)),
  ]
  for (const fullPath of knownPaths) {
    if (basePath && fullPath !== basePath && !fullPath.startsWith(prefix)) continue
    if (!basePath && !fullPath) continue
    const remaining = basePath ? fullPath.slice(prefix.length) : fullPath
    if (!remaining || remaining.startsWith('../')) continue
    const [first, ...rest] = remaining.split('/').filter(Boolean)
    if (!first) continue
    if (rest.length) {
      const path = basePath ? `${basePath}/${first}` : first
      if (!result.has(`folder:${path}`)) result.set(`folder:${path}`, { id: `folder:${path}`, label: first, kind: 'folder', type: 'folder', path, status: 'ready', parentId, children: [] })
    } else {
      const asset = selected.value?.assets.find(item => item.relative_path === fullPath)
      if (asset) result.set(`asset:${asset.asset_id}`, { id: `asset:${asset.asset_id}`, label: asset.filename, kind: 'asset', type: 'file', path: asset.relative_path, status: 'uploaded', updatedAt: asset.updated_at || asset.uploaded_at || selected.value?.updated_at, asset, parentId })
      else if (fullPath !== basePath) {
        const path = basePath ? `${basePath}/${first}` : first
        result.set(`folder:${path}`, { id: `folder:${path}`, label: first, kind: 'folder', type: 'folder', path, status: 'ready', parentId, children: [] })
      }
    }
  }
  return [...result.values()].map(node => node.kind === 'folder' ? { ...node, children: physicalChildren(node.path, node.id) } : node)
}

function practiceNodeIds(lesson: TeacherLessonProjection) {
  return lessonContentNodes(lesson)
    .filter(node => Number(node.node_level || 0) === 2)
    .map(node => node.node_id)
}
function practiceStatus(lesson: TeacherLessonProjection): NodeStatus {
  if (practiceWorkingLessonIds.value.includes(lesson.lesson_unit_id)) return 'working'
  const nodeIds = new Set(practiceNodeIds(lesson))
  return questionBankItems.value.some(item => item.lifecycle_status !== 'retired' && item.node_id && nodeIds.has(item.node_id))
    ? 'ready'
    : 'missing'
}
function assetIdsIn(nodes: WorkspaceNode[]) {
  const ids = new Set<string>()
  const visit = (node: WorkspaceNode) => { if (node.asset) ids.add(node.asset.asset_id); node.children?.forEach(visit) }
  nodes.forEach(visit)
  return ids
}

type AuxiliaryBucket = 'question_bank' | 'exam_papers' | 'student_work' | 'other'

function auxiliaryBucket(asset: Asset): AuxiliaryBucket {
  const value = `${asset.category || ''} ${asset.relative_path || ''} ${asset.filename || ''}`.toLocaleLowerCase()
  if (/(学生作业|学生答卷|答卷|作业提交|实验报告|课程报告)/.test(value)) return 'student_work'
  if (/(试卷|考卷|真题|模拟卷|考试卷|期中|期末)/.test(value)) return 'exam_papers'
  if (asset.document_type === 'question_bank') return 'question_bank'
  if (/(题库|题目库|习题库|练习题|习题集)/.test(value)) return 'question_bank'
  return 'other'
}

function auxiliaryChildren(basePath: string, parentId: string, bucket: AuxiliaryBucket) {
  const physical = physicalChildren(basePath, parentId)
  const seen = assetIdsIn(physical)
  const legacy = (selected.value?.assets || [])
    .filter(asset => auxiliaryBucket(asset) === bucket && !seen.has(asset.asset_id))
    .map<WorkspaceNode>(asset => ({
      id: `asset:${asset.asset_id}`,
      label: asset.filename,
      kind: 'asset',
      type: 'file',
      path: asset.relative_path,
      status: 'uploaded',
      updatedAt: asset.updated_at || asset.uploaded_at || selected.value?.updated_at,
      asset,
      parentId,
    }))
  return [...physical, ...legacy]
}

const treeData = computed<WorkspaceNode[]>(() => {
  const outlineStatus: NodeStatus = courseStore.nodes.length ? (courseStore.currentDocumentRevision ? 'ready' : 'draft') : 'missing'
  const outlineRevision = courseStore.currentDocumentRevision || ''
  const outlineSize = courseStore.nodes.length ? textSize(outlineMarkdown()) : undefined
  const logicOutline: WorkspaceNode = {
    id: 'managed:outline', label: t('courseFiles.names.outline'), kind: 'managed', type: 'outline', path: '课程逻辑文件/大纲',
    status: outlineStatus, revision: outlineRevision, parentId: 'folder:course-logic', sizeBytes: outlineSize, order: 1,
  }
  const outlineDeliverable: WorkspaceNode = {
    id: 'deliverable:outline', label: t('courseFiles.names.outlineFile'), kind: 'managed', type: 'outline_export', path: '教务材料/大纲文件',
    status: outlineStatus, revision: outlineRevision, parentId: 'folder:deliverables', sizeBytes: outlineSize, order: 1,
    description: t('courseFiles.descriptions.outlineDeliverable'),
  }
  const calendar = calendarStore.calendar?.course_id === props.courseId ? calendarStore.calendar : null
  const calendarSessions = calendar?.sessions || []
  const activeCalendarSessions = calendarSessions.filter(session => session.status !== 'cancelled')
  const calendarStatus: NodeStatus = !calendarSessions.length
    ? 'missing'
    : activeCalendarSessions.length > 0 && activeCalendarSessions.every(session => session.status === 'scheduled' && session.date && session.start_time && session.end_time)
      ? 'ready'
      : 'draft'
  const teachingCalendar: WorkspaceNode = {
    id: 'managed:teaching-calendar', label: t('courseFiles.names.teachingCalendarFile'), kind: 'managed', type: 'teaching_calendar', path: '教务材料/教学日历文件',
    status: calendarStore.loading && !calendar ? 'working' : calendarStatus, revision: calendar?.revision ? `r${calendar.revision}` : '', updatedAt: calendar?.updated_at, parentId: 'folder:deliverables',
    sizeBytes: calendarSessions.length ? textSize(JSON.stringify(calendarSessions)) : undefined, order: 2,
  }
  const formalQuestionBank: WorkspaceNode = {
    id: 'managed:question-bank', label: t('courseFiles.names.questionBank'), kind: 'managed', type: 'question_bank', path: '课程逻辑文件/题库/课程题库',
    status: questionBankItems.value.length ? 'ready' : 'missing', revision: questionBankRevisionId.value, parentId: 'folder:question-bank-files', order: 1,
    sizeBytes: questionBankItems.value.length ? textSize(JSON.stringify(questionBankItems.value)) : undefined,
  }
  const examPaperNodes: WorkspaceNode[] = examPapers.value.map(paper => ({
    id: `exam-paper:${paper.paper_id}`, label: paper.title, kind: 'managed', type: 'exam_paper', path: `课程逻辑文件/题库/正式试卷/${safePart(paper.title)}`,
    status: 'ready', revision: paper.revision_id, updatedAt: paper.updated_at, parentId: 'folder:exam-papers', sizeBytes: textSize(JSON.stringify(paper)),
  }))
  const examPapersFolder: WorkspaceNode = {
    id: 'folder:exam-papers', label: t('courseFiles.names.formalExamPapers'), kind: 'folder', type: 'exam_papers', path: '课程逻辑文件/题库/正式试卷',
    status: examPaperNodes.length ? 'ready' : 'empty', parentId: 'folder:question-bank-files', order: 3, children: examPaperNodes,
  }
  const companionDocumentNodes: WorkspaceNode[] = companionDocuments.value.map(document => ({
    id: `companion-document:${document.document_id}`,
    label: document.title,
    kind: 'managed',
    type: 'companion_document',
    path: `教务材料/其他教务材料/${safePart(document.title)}`,
    status: document.status === 'ready' ? 'ready' : 'draft',
    revision: document.revision_id,
    updatedAt: document.updated_at,
    sizeBytes: textSize(document.rendered_markdown || ''),
    parentId: 'folder:other-deliverables',
    companionDocument: document,
  }))
  const lessonPlanNodes: WorkspaceNode[] = []
  const scriptPptLessonNodes: WorkspaceNode[] = []
  const practiceNodes: WorkspaceNode[] = []
  lessons.value.forEach(lesson => {
    const working = lesson.plan.revisions.find(item => item.revision_id === lesson.plan.working_revision_id)
    const ppt = lesson.plan.ppt_assets.find(item => item.role === 'primary') || lesson.plan.ppt_assets[0]
    const activeJob = lessonStore.activeJobByLesson(lesson.lesson_unit_id)
    const contentNodes = lessonContentNodes(lesson)
    const contentReady = contentNodes.some(hasUsableContent)
    const lessonPrefix = `${String(lesson.number).padStart(2, '0')}  ${lesson.title}`
    const planNode: WorkspaceNode = {
      id: `plan:${lesson.lesson_unit_id}`, label: `${lessonPrefix} · ${t('courseFiles.names.lessonPlan')}`, kind: 'managed', type: 'lesson_plan', path: `课程逻辑文件/教案/${safePart(lessonPrefix)}`,
      lessonId: lesson.lesson_unit_id, parentId: 'folder:lesson-plans', status: activeJob?.type?.includes('plan') ? 'working' : lesson.plan.source_state === 'stale' ? 'stale' : working ? (working.status === 'confirmed' ? 'ready' : 'draft') : 'missing',
      revision: working?.revision_id || '', updatedAt: working?.created_at, sizeBytes: working ? textSize(lessonPlanMarkdown(lesson)) : undefined,
    }
    const contentNode: WorkspaceNode = {
      id: `content:${lesson.lesson_unit_id}`, label: t('courseFiles.names.content'), kind: 'managed', type: 'content', path: `课程逻辑文件/讲稿-PPT/${safePart(lessonPrefix)}/讲稿`,
      lessonId: lesson.lesson_unit_id, parentId: `lesson:${lesson.lesson_unit_id}`, status: contentReady ? 'ready' : contentNodes.length ? 'draft' : 'missing',
      revision: courseStore.currentDocumentRevision, sizeBytes: contentReady ? textSize(lessonContentMarkdown(lesson)) : undefined,
    }
    const pptNode: WorkspaceNode = {
      id: `ppt:${lesson.lesson_unit_id}`, label: t('courseFiles.names.ppt'), kind: 'managed', type: 'ppt', path: `课程逻辑文件/讲稿-PPT/${safePart(lessonPrefix)}/PPT`,
      lessonId: lesson.lesson_unit_id, parentId: `lesson:${lesson.lesson_unit_id}`, status: activeJob?.type?.includes('ppt') ? 'working' : ppt?.source_state === 'stale' ? 'stale' : ppt ? 'ready' : 'missing',
      revision: ppt?.working_revision_id || '', updatedAt: ppt?.revisions?.at(-1)?.created_at, origin: (ppt || activeJob?.type?.includes('ppt') ? 'generated' : undefined) as 'generated' | undefined,
    }
    const practiceNode: WorkspaceNode = {
      id: `practice:${lesson.lesson_unit_id}`, label: `${lessonPrefix} · ${t('courseFiles.names.lessonPractice')}`, kind: 'managed', type: 'practice', path: `课程逻辑文件/题库/分讲练习/${safePart(lessonPrefix)}`,
      lessonId: lesson.lesson_unit_id, parentId: 'folder:question-practices', status: practiceStatus(lesson),
    }
    lessonPlanNodes.push(planNode)
    practiceNodes.push(practiceNode)
    scriptPptLessonNodes.push({
      id: `lesson:${lesson.lesson_unit_id}`, label: lessonPrefix, kind: 'folder', type: 'lesson', path: `课程逻辑文件/讲稿-PPT/${safePart(lessonPrefix)}`,
      status: aggregateStatus([contentNode, pptNode]), lessonId: lesson.lesson_unit_id, parentId: 'folder:script-ppt', children: [contentNode, pptNode],
    })
  })

  const otherDeliverables: WorkspaceNode = {
    id: 'folder:other-deliverables', label: t('courseFiles.names.otherDeliverables'), kind: 'folder', type: 'companion_documents', path: '教务材料/其他教务材料',
    status: companionDocumentNodes.length ? 'ready' : 'empty', parentId: 'folder:deliverables', order: 3, children: companionDocumentNodes,
  }
  const deliverables: WorkspaceNode = {
    id: 'folder:deliverables', label: t('courseFiles.names.deliverables'), kind: 'folder', type: 'deliverables', path: '教务材料',
    status: aggregateStatus([outlineDeliverable, teachingCalendar]), parentId: 'root', order: 1, description: t('courseFiles.descriptions.deliverables'),
    children: [outlineDeliverable, teachingCalendar, ...(companionDocumentNodes.length ? [otherDeliverables] : [])],
  }
  const lessonPlansFolder: WorkspaceNode = {
    id: 'folder:lesson-plans', label: t('courseFiles.names.lessonPlans'), kind: 'folder', type: 'lesson_plans', path: '课程逻辑文件/教案',
    status: aggregateStatus(lessonPlanNodes), parentId: 'folder:course-logic', order: 2, children: lessonPlanNodes,
  }
  const scriptPptFolder: WorkspaceNode = {
    id: 'folder:script-ppt', label: t('courseFiles.names.scriptPpt'), kind: 'folder', type: 'script_ppt', path: '课程逻辑文件/讲稿-PPT',
    status: aggregateStatus(scriptPptLessonNodes), parentId: 'folder:course-logic', order: 3, children: scriptPptLessonNodes,
    description: t('courseFiles.descriptions.scriptPpt'),
  }
  const questionPracticesFolder: WorkspaceNode = {
    id: 'folder:question-practices', label: t('courseFiles.names.questionPractices'), kind: 'folder', type: 'question_practices', path: '课程逻辑文件/题库/分讲练习',
    status: aggregateStatus(practiceNodes), parentId: 'folder:question-bank-files', order: 2, children: practiceNodes,
  }
  const questionBankFolder: WorkspaceNode = {
    id: 'folder:question-bank-files', label: t('courseFiles.names.questionBankFiles'), kind: 'folder', type: 'question_bank_files', path: '课程逻辑文件/题库',
    status: aggregateStatus([formalQuestionBank, questionPracticesFolder, examPapersFolder]), parentId: 'folder:course-logic', order: 4,
    children: [formalQuestionBank, questionPracticesFolder, examPapersFolder],
  }
  const courseLogic: WorkspaceNode = {
    id: 'folder:course-logic', label: t('courseFiles.names.courseLogic'), kind: 'folder', type: 'course_logic', path: '课程逻辑文件',
    status: aggregateStatus([logicOutline, lessonPlansFolder, scriptPptFolder, questionBankFolder]), parentId: 'root', order: 2,
    description: t('courseFiles.descriptions.courseLogic'), children: [logicOutline, lessonPlansFolder, scriptPptFolder, questionBankFolder],
  }

  const auxiliaryDefinitions: Array<{ id: string; label: string; type: NodeType; path: string; bucket: AuxiliaryBucket; order: number }> = [
    { id: 'folder:aux-question-bank', label: t('courseFiles.names.teacherQuestionBanks'), type: 'aux_question_bank', path: '辅助资料/老师题库', bucket: 'question_bank', order: 1 },
    { id: 'folder:aux-exam-papers', label: t('courseFiles.names.uploadedExamPapers'), type: 'aux_exam_papers', path: '辅助资料/试卷', bucket: 'exam_papers', order: 2 },
    { id: 'folder:aux-student-work', label: t('courseFiles.names.studentWork'), type: 'aux_student_work', path: '辅助资料/学生作业', bucket: 'student_work', order: 3 },
    { id: 'folder:aux-other', label: t('courseFiles.names.otherMaterials'), type: 'aux_other', path: '辅助资料/其他资料', bucket: 'other', order: 4 },
  ]
  const auxiliaryFolders = auxiliaryDefinitions.map<WorkspaceNode>(definition => {
    const children = auxiliaryChildren(definition.path, definition.id, definition.bucket)
    return { ...definition, kind: 'folder', status: children.length ? 'ready' : 'empty', parentId: 'folder:supporting-materials', children }
  })
  const supportingMaterials: WorkspaceNode = {
    id: 'folder:supporting-materials', label: t('courseFiles.names.supportingMaterials'), kind: 'folder', type: 'supporting_materials', path: '辅助资料',
    status: auxiliaryFolders.some(folder => folder.children?.length) ? 'ready' : 'empty', parentId: 'root', order: 3,
    description: t('courseFiles.descriptions.supportingMaterials'), children: auxiliaryFolders,
  }
  const courseRoot: WorkspaceNode = {
    id: 'root', label: t('courseFiles.rootName'), kind: 'folder', type: 'root', path: '', status: courseLogic.status,
    children: [deliverables, courseLogic, supportingMaterials],
  }
  return [courseRoot]
})

function toFolderTreeItem(node: WorkspaceNode): WorkspaceFolderTreeItem | null {
  if (node.kind !== 'folder') return null
  const children = (node.children || []).map(toFolderTreeItem).filter((item): item is WorkspaceFolderTreeItem => Boolean(item))
  const attention = (node.children || []).some(item => item.status === 'stale' || item.status === 'working' || item.kind === 'folder' && toFolderTreeItem(item)?.attention)
  return { id: node.id, label: node.label, attention, children }
}
const folderTreeData = computed(() => treeData.value.map(toFolderTreeItem).filter((item): item is WorkspaceFolderTreeItem => Boolean(item)))

const flatNodes = computed(() => {
  const map = new Map<string, WorkspaceNode>()
  const visit = (node: WorkspaceNode) => { map.set(node.id, node); node.children?.forEach(visit) }
  treeData.value.forEach(visit)
  return map
})
const categoryGroups = computed<CategoryGroup[]>(() => ([
  { type: 'outline' as const, step: 1, label: t('courseFiles.names.outline'), description: t('courseFiles.workbench.stages.outline'), icon: markRaw(FileText) },
  { type: 'lesson_plan' as const, step: 2, label: t('courseFiles.names.lessonPlan'), description: t('courseFiles.workbench.stages.lessonPlan'), icon: markRaw(ClipboardList) },
  { type: 'practice' as const, step: 3, label: t('courseFiles.names.questionBank'), description: t('courseFiles.workbench.stages.questionBank'), icon: markRaw(ListChecks) },
  { type: 'content' as const, step: 4, label: t('courseFiles.names.content'), description: t('courseFiles.workbench.stages.content'), icon: markRaw(BookOpenText) },
  { type: 'ppt' as const, step: 5, label: t('courseFiles.names.ppt'), description: t('courseFiles.workbench.stages.ppt'), icon: markRaw(Presentation) },
]).map(definition => {
  const items = [...flatNodes.value.values()]
    .filter(node => node.kind === 'managed' && node.type === definition.type)
    .sort((left, right) => {
      if (!left.lessonId && right.lessonId) return -1
      if (left.lessonId && !right.lessonId) return 1
      const leftNumber = lessons.value.find(item => item.lesson_unit_id === left.lessonId)?.number || 0
      const rightNumber = lessons.value.find(item => item.lesson_unit_id === right.lessonId)?.number || 0
      return leftNumber - rightNumber || left.label.localeCompare(right.label)
    })
  return {
    ...definition,
    items,
    ready: items.filter(node => node.status === 'ready').length,
    working: items.filter(node => node.status === 'working').length,
    attention: items.filter(node => ['draft', 'missing', 'stale', 'empty'].includes(node.status)).length,
  }
}))
const completedCategoryStages = computed(() => categoryGroups.value.filter(group => group.items.length > 0 && group.ready === group.items.length).length)
const categoryProgressPercent = computed(() => categoryGroups.value.length ? Math.round(completedCategoryStages.value / categoryGroups.value.length * 100) : 0)
const activeCategory = computed(() => categoryGroups.value.find(group => group.type === selectedCategory.value) || categoryGroups.value[0])
const categoryDetailNode = computed(() => {
  const group = activeCategory.value
  if (!group) return null
  return group.items.find(node => node.id === selectedNode.value?.id) || group.items[0] || null
})
const categoryDetailTitle = computed(() => {
  const node = categoryDetailNode.value
  if (!node) return activeCategory.value?.label || t('courseFiles.views.categories')
  return node.lessonId ? lessonLabel(node.lessonId) : node.label
})
const categoryDetailMarkdown = computed(() => {
  const node = categoryDetailNode.value
  if (!node || node.status === 'missing' || node.status === 'working') return ''
  if (node.type === 'outline') return previewMarkdown(outlineMarkdown())
  const lesson = node.lessonId ? lessons.value.find(item => item.lesson_unit_id === node.lessonId) : undefined
  if (!lesson) return ''
  if (node.type === 'lesson_plan') return previewMarkdown(lessonPlanMarkdown(lesson))
  if (node.type === 'content') return previewMarkdown(lessonContentMarkdown(lesson))
  if (node.type === 'ppt') return previewMarkdown(lessonPptMarkdown(lesson))
  return ''
})
const productionContextItems = computed(() => {
  const options = props.generationOptions || {}
  const brief = options.teacher_course_brief
  const intent = options.course_intent
  const courseType = String(options.course_type || intent?.type || 'systematic')
  const courseTypeLabel = t(`courseGeneration.courseTypes.${courseType}.label`, courseType)
  const difficulty = options.difficulty
    ? t(`courseGeneration.difficulty.${options.difficulty}.label`, String(options.difficulty))
    : t('courseFiles.workbench.notSet')
  const goal = intent?.type === 'project'
    ? intent.project_goal
    : intent?.type === 'inquiry'
      ? intent.desired_output || intent.core_question
      : intent?.type === 'exam'
        ? intent.exam_scope || intent.exam_name
        : intent?.learning_goal
  const structure = options.pedagogy_mode
    ? t(`courseGeneration.pedagogy.options.${options.pedagogy_mode}`, String(options.pedagogy_mode))
    : t('courseFiles.workbench.notSet')
  const classHours = Number(brief?.total_class_hours || 0)
  const sectionCount = Number(brief?.section_count || 0)
  const scale = classHours && sectionCount
    ? t('courseFiles.workbench.scaleValue').replace('{hours}', String(classHours)).replace('{count}', String(sectionCount))
    : classHours
      ? t('courseFiles.workbench.hoursValue').replace('{hours}', String(classHours))
    : t('courseFiles.workbench.notSet')
  const productionMode = options.production_mode === 'automatic'
    ? t('courseFiles.workbench.productionAutomatic')
    : t('courseFiles.workbench.productionManual')
  return [
    { label: t('courseFiles.workbench.courseType'), value: courseTypeLabel },
    { label: t('courseFiles.workbench.learningGoal'), value: String(goal || t('courseFiles.workbench.notSet')), title: String(goal || ''), empty: !goal },
    { label: t('courseFiles.workbench.difficulty'), value: difficulty, empty: !options.difficulty },
    { label: t('courseFiles.workbench.knowledgeStructure'), value: structure, empty: !options.pedagogy_mode },
    { label: t('courseFiles.workbench.courseScale'), value: scale, empty: !classHours },
    { label: t('courseFiles.workbench.productionMode'), value: productionMode },
  ]
})
const categoryConsoleTitle = computed(() => {
  const group = activeCategory.value
  const node = categoryDetailNode.value
  if (!group) return t('courseFiles.workbench.startPreparing')
  if (!node) return t('courseFiles.workbench.noLessonsTitle').replace('{stage}', group.label)
  if (node.status === 'working') return t('courseFiles.workbench.workingTitle').replace('{stage}', group.label)
  if (node.status === 'stale') return t('courseFiles.workbench.updateTitle').replace('{stage}', group.label)
  if (node.status === 'ready') return t('courseFiles.workbench.manageTitle').replace('{stage}', group.label)
  if (node.status === 'draft') return t('courseFiles.workbench.continueTitle').replace('{stage}', group.label)
  return t('courseFiles.workbench.startStage').replace('{stage}', group.label)
})
const categoryConsoleActionLabel = computed(() => {
  if (categoryDetailNode.value) return primaryLabel(categoryDetailNode.value)
  return activeCategory.value?.type === 'outline'
    ? t('courseFiles.workbench.createOutline')
    : t('courseFiles.workbench.returnToOutline')
})
const currentFolder = computed(() => flatNodes.value.get(currentFolderId.value) || treeData.value[0])
const inspectedNode = computed(() => selectedNode.value || currentFolder.value || null)
function formalTargetId(node: WorkspaceNode) {
  if (node.type === 'outline') return 'managed:outline'
  if (node.type === 'teaching_calendar') return 'managed:teaching-calendar'
  if (node.type === 'lesson_plan') return `lesson-plan:${node.lessonId || ''}`
  if (node.type === 'content') return `script:${node.lessonId || ''}`
  if (node.type === 'ppt') return `ppt:${node.lessonId || ''}`
  if (node.type === 'practice') return `question-bank:${node.lessonId || ''}`
  if (node.type === 'question_bank') return 'managed:question-bank'
  if (node.type === 'exam_paper') return node.id
  if (node.type === 'companion_document') return node.id
  return ''
}
const inspectedSourceLinks = computed(() => {
  const node = selectedNode.value
  if (!node || node.kind !== 'managed') return []
  const targetId = formalTargetId(node)
  return targetId ? (selected.value?.relationships || []).filter(link => link.target_id === targetId) : []
})
const inspectedPrimarySourceLinks = computed(() => inspectedSourceLinks.value.filter(link => link.role === 'primary'))
const inspectedReferenceSourceLinks = computed(() => inspectedSourceLinks.value.filter(link => link.role !== 'primary'))
const inspectedUsageLinks = computed(() => {
  const assetId = selectedNode.value?.asset?.asset_id
  return assetId ? (selected.value?.relationships || []).filter(link => link.source_asset_id === assetId) : []
})
function aggregateStatus(nodes: WorkspaceNode[]): NodeStatus {
  const states = nodes.map(node => node.status)
  if (states.includes('working')) return 'working'
  if (states.includes('stale')) return 'stale'
  if (states.length && states.every(state => state === 'ready')) return 'ready'
  if (states.some(state => state === 'ready' || state === 'draft')) return 'draft'
  return states.length ? 'missing' : 'empty'
}
function relationshipRoleLabel(role: string) {
  if (role === 'primary') return t('courseFiles.inspector.primarySource', '主来源')
  if (role === 'question_source') return t('courseFiles.inspector.questionSource', '真题资料')
  return t('courseFiles.inspector.referenceSource', '参考资料')
}
function formalTypeLabel(type: string) { return t(`courseFiles.formalTypes.${type}`, type) }
const sortColumns = computed<Array<{ key: SortKey; label: string }>>(() => [
  { key: 'name', label: t('courseFiles.columns.name') },
  { key: 'updated', label: t('courseFiles.columns.updated') },
  { key: 'type', label: t('courseFiles.columns.type') },
  { key: 'size', label: t('courseFiles.columns.size') },
  { key: 'status', label: t('courseFiles.columns.status') },
])
const collator = computed(() => new Intl.Collator(activeLocale.value === 'zh' ? 'zh-CN' : 'en-US', { numeric: true, sensitivity: 'base' }))
const filteredChildren = computed(() => {
  const value = query.value.trim().toLocaleLowerCase()
  const candidates = value
    ? [...flatNodes.value.values()].filter(item => item.type !== 'root')
    : currentFolder.value?.children || []
  return candidates
    .filter(item => !value || item.label.toLocaleLowerCase().includes(value))
    .slice()
    .sort(compareNodes)
})
const currentListTitle = computed(() => query.value.trim()
  ? t('courseFiles.searchResults')
  : currentFolder.value?.label || t('courseFiles.rootName'))
const readinessSummary = computed(() => {
  const required = [...flatNodes.value.values()].filter(node => node.kind === 'managed' && ['outline', 'lesson_plan', 'content', 'practice'].includes(node.type))
  const ready = required.filter(node => node.status === 'ready').length
  return { required: required.length, ready, pending: required.length - ready }
})
const breadcrumbs = computed(() => {
  const values: WorkspaceNode[] = []
  let node = currentFolder.value
  while (node?.parentId) { values.unshift(node); node = flatNodes.value.get(node.parentId) }
  return values
})
const createTargetFolder = computed(() => flatNodes.value.get(createTargetFolderId.value) || currentFolder.value)
const canAddTeacherFiles = computed(() => Boolean(currentFolder.value && ['supporting_materials', 'aux_question_bank', 'aux_exam_papers', 'aux_student_work', 'aux_other', 'folder'].includes(currentFolder.value.type)))
const canBatchImport = computed(() => Boolean(currentFolder.value && ['root', 'supporting_materials', 'aux_question_bank', 'aux_exam_papers', 'aux_student_work', 'aux_other', 'folder'].includes(currentFolder.value.type)))
const batchImportLocation = computed(() => currentFolder.value?.type === 'root'
  ? t('courseFiles.rootName')
  : displayPath(targetPath('material', '')))
const emptyFolderTitle = computed(() => ['supporting_materials', 'aux_question_bank', 'aux_exam_papers', 'aux_student_work', 'aux_other'].includes(currentFolder.value?.type || '') ? t('courseFiles.emptyMaterials') : t('courseFiles.emptyFolder'))
const documentTypeOptions = computed<Array<{ value: DocumentType; label: string }>>(() => [
  { value: 'outline', label: t('courseFiles.preparation.documentTypes.outline') },
  { value: 'lesson_plan', label: t('courseFiles.preparation.documentTypes.lessonPlan') },
  { value: 'script', label: t('courseFiles.preparation.documentTypes.script') },
  { value: 'ppt', label: t('courseFiles.preparation.documentTypes.ppt') },
  { value: 'question_bank', label: t('courseFiles.preparation.documentTypes.questionBank') },
  { value: 'school_material', label: t('courseFiles.preparation.documentTypes.schoolMaterial') },
  { value: 'other', label: t('courseFiles.preparation.documentTypes.other') },
])

function setWorkspaceView(value: WorkspaceView) {
  if (props.workspaceView === undefined) localWorkspaceView.value = value
  emit('update:workspaceView', value)
  if (value === 'categories' && activeCategory.value) selectCategory(activeCategory.value)
}

const categoryHasChildren = (group: CategoryGroup) => group.type !== 'outline' && group.items.length > 0
function selectCategory(group: CategoryGroup) {
  selectedCategory.value = group.type
  const current = group.items.find(node => node.id === selectedNode.value?.id)
  if (current) return
  if (group.items[0]) selectNode(group.items[0])
  else selectedNode.value = null
}
function selectCategoryNode(node: WorkspaceNode) { selectNode(node) }

function categoryCountLabel(group: CategoryGroup) {
  if (!group.items.length) return t('courseFiles.categories.notStarted')
  if (group.ready === group.items.length) return t('courseFiles.workbench.completed')
  if (group.working) return t('courseFiles.workbench.generating')
  return t('courseFiles.workbench.progressCount').replace('{ready}', String(group.ready)).replace('{total}', String(group.items.length))
}

function startActiveCategory() {
  if (categoryDetailNode.value) {
    void primaryAction(categoryDetailNode.value)
    return
  }
  const outline = categoryGroups.value.find(group => group.type === 'outline')?.items[0]
  if (outline) void primaryAction(outline)
  else emit('createOutline')
}

function categoryState(group: CategoryGroup) {
  if (group.ready === group.items.length && group.items.length) return 'ready'
  if (group.working) return 'working'
  return 'attention'
}

function documentTypeLabel(type?: DocumentType) {
  const option = documentTypeOptions.value.find(item => item.value === type)
  return option?.label || t('courseFiles.types.file')
}
const typeLabel = (node: WorkspaceNode) => node.asset
  ? documentTypeLabel(node.asset.document_type)
  : t(`courseFiles.types.${node.type === 'lesson_plan' ? 'lessonPlan' : node.type === 'teaching_calendar' ? 'teachingCalendar' : node.type === 'companion_document' ? 'companionDocument' : node.type === 'companion_documents' ? 'companionDocuments' : node.type}`)
function assetRole(node: WorkspaceNode) {
  if (node.kind === 'asset' || ['supporting_materials', 'aux_question_bank', 'aux_exam_papers', 'aux_student_work', 'aux_other'].includes(node.type)) return 'auxiliary'
  if (['deliverables', 'outline_export', 'teaching_calendar', 'companion_documents', 'companion_document'].includes(node.type)) return 'deliverable'
  if (node.kind === 'managed' || ['course_logic', 'lesson_plans', 'script_ppt', 'question_bank_files', 'question_practices', 'exam_papers', 'lesson'].includes(node.type)) return 'logic'
  return 'navigation'
}
const fileRoleLabel = (node: WorkspaceNode) => t(`courseFiles.assetRole.${assetRole(node)}`)
function fileSourceLabel(node: WorkspaceNode) {
  if (node.kind === 'asset') return t('courseFiles.sources.teacherUpload')
  if (node.type === 'outline_export') return t('courseFiles.sources.logicProjection')
  if (node.kind === 'managed') return t('courseFiles.sources.formalTruth')
  return t('courseFiles.sources.semanticFolder')
}
const statusLabel = (node: WorkspaceNode) => t(`courseFiles.status.${node.status}`)
const nodeIcon = (node: WorkspaceNode) => markRaw(node.type === 'teaching_calendar' ? CalendarDays : node.type === 'ppt' ? Presentation : ['practice', 'question_bank', 'question_bank_files', 'question_practices', 'aux_question_bank'].includes(node.type) ? ListChecks : ['exam_paper', 'exam_papers', 'aux_exam_papers', 'companion_document', 'companion_documents', 'outline_export'].includes(node.type) ? FileCheck2 : node.type === 'lesson_plan' ? ClipboardList : node.type === 'content' ? BookOpenText : ['supporting_materials', 'aux_student_work', 'aux_other', 'material'].includes(node.type) ? BookOpen : FileText)
const lessonLabel = (id: string) => lessons.value.find(item => item.lesson_unit_id === id)?.title || id
const lessonNumber = (id?: string) => {
  const lesson = lessons.value.find(item => item.lesson_unit_id === id)
  return lesson ? String(lesson.number).padStart(2, '0') : '—'
}
const dateLabel = (value?: string) => value ? new Intl.DateTimeFormat(activeLocale.value === 'zh' ? 'zh-CN' : 'en-US', { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(value)) : t('courseFiles.notUpdated')
const size = (value: number) => value >= 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(value / 1024))} KB`
const displayUpdated = (node: WorkspaceNode) => node.kind === 'folder' ? folderUpdatedLabel(node) : dateLabel(node.updatedAt)
const displaySize = (node: WorkspaceNode) => node.kind === 'folder'
  ? t('courseFiles.itemCount').replace('{count}', String(node.children?.length || 0))
  : node.asset ? size(node.asset.size_bytes) : node.sizeBytes ? size(node.sizeBytes) : t('courseFiles.unknownSize')

function compareNodes(left: WorkspaceNode, right: WorkspaceNode) {
  const direction = sortDirection.value === 'ascending' ? 1 : -1
  if (left.order !== undefined && right.order !== undefined) return (left.order - right.order) * direction
  if (left.kind === 'folder' && right.kind !== 'folder') return -1
  if (left.kind !== 'folder' && right.kind === 'folder') return 1

  let result = 0
  if (sortKey.value === 'updated') {
    if (!left.updatedAt && right.updatedAt) return 1
    if (left.updatedAt && !right.updatedAt) return -1
    result = (left.updatedAt ? Date.parse(left.updatedAt) : 0) - (right.updatedAt ? Date.parse(right.updatedAt) : 0)
  } else if (sortKey.value === 'type') {
    result = collator.value.compare(typeLabel(left), typeLabel(right))
  } else if (sortKey.value === 'size') {
    const leftSize = left.asset?.size_bytes ?? left.sizeBytes
    const rightSize = right.asset?.size_bytes ?? right.sizeBytes
    if (leftSize === undefined && rightSize !== undefined) return 1
    if (leftSize !== undefined && rightSize === undefined) return -1
    result = (leftSize || 0) - (rightSize || 0)
  } else if (sortKey.value === 'status') {
    result = collator.value.compare(statusLabel(left), statusLabel(right))
  } else {
    result = collator.value.compare(left.label, right.label)
  }
  return result === 0 ? collator.value.compare(left.label, right.label) : result * direction
}

function toggleSort(key: SortKey) {
  if (sortKey.value === key) sortDirection.value = sortDirection.value === 'ascending' ? 'descending' : 'ascending'
  else {
    sortKey.value = key
    sortDirection.value = 'ascending'
  }
}

function sortAria(key: SortKey) {
  return sortKey.value === key ? sortDirection.value : 'none'
}

function sortIcon(key: SortKey) {
  if (sortKey.value !== key) return markRaw(ArrowUpDown)
  return markRaw(sortDirection.value === 'ascending' ? ArrowUp : ArrowDown)
}

function folderSummary(node: WorkspaceNode) {
  const children = node.children || []
  const pending = children.filter(item => ['missing', 'stale', 'working'].includes(item.status)).length
  const total = t('courseFiles.itemCount').replace('{count}', String(children.length))
  return pending ? `${total} · ${t('courseFiles.inspector.pendingCount').replace('{count}', String(pending))}` : total
}

function latestUpdatedAt(node: WorkspaceNode): string | undefined {
  const values = [
    node.updatedAt,
    ...(node.children || []).map(latestUpdatedAt),
    ...(node.type === 'root' ? [selected.value?.updated_at] : []),
  ].filter((value): value is string => Boolean(value) && !Number.isNaN(Date.parse(String(value))))
  return values.sort((left, right) => Date.parse(right) - Date.parse(left))[0]
}

const folderUpdatedLabel = (node: WorkspaceNode) => dateLabel(latestUpdatedAt(node))

function inspectorMaterialFolder(node: WorkspaceNode): WorkspaceNode | null {
  if (query.value.trim()) return null
  if (node.kind !== 'folder') return null
  if (['supporting_materials', 'aux_question_bank', 'aux_exam_papers', 'aux_student_work', 'aux_other', 'folder'].includes(node.type)) return node
  return null
}

function inspectorHasActions(node: WorkspaceNode) {
  return Boolean(selectedNode.value || node.type === 'root' || inspectorMaterialFolder(node))
}

function openInspectorCreate(node: WorkspaceNode, type: 'material' | 'folder') {
  const target = inspectorMaterialFolder(node)
  if (!target) return
  openCreateDialog(type, node.lessonId || target.lessonId || '', target.id)
}

function shortRevision(revision: string) {
  return revision.length > 14 ? `${revision.slice(0, 8)}…${revision.slice(-5)}` : revision
}

function folderPath(id: string) {
  const values: string[] = []
  let node = flatNodes.value.get(id)
  while (node) { if (node.kind === 'folder') values.unshift(node.id); node = node.parentId ? flatNodes.value.get(node.parentId) : undefined }
  return values
}
function toggleFolder(id: string) {
  expandedFolderIds.value = expandedFolderIds.value.includes(id)
    ? expandedFolderIds.value.filter(value => value !== id)
    : [...expandedFolderIds.value, id]
}
function openFolder(id: string) {
  const node = flatNodes.value.get(id)
  if (node?.kind !== 'folder') return
  currentFolderId.value = id
  selectedNode.value = null
  query.value = ''
  expandedFolderIds.value = [...new Set([...expandedFolderIds.value, ...folderPath(id)])]
  const lessonId = node.lessonId || ''
  const nextQuery = { ...route.query }
  if (lessonId) nextQuery.lesson = lessonId
  else delete nextQuery.lesson
  void router.replace({ query: nextQuery })
  emit('contextChange', { lessonId, nodeId: node.id, label: node.label, type: node.type, path: node.path })
}
function selectNode(node: WorkspaceNode) {
  selectedNode.value = node
  emit('contextChange', { lessonId: node.lessonId || '', nodeId: node.id, label: node.label, type: node.type, path: node.path })
}
function revealNode(node: WorkspaceNode) {
  if (node.parentId) openFolder(node.parentId)
  selectNode(node)
}
function relationshipTargetNode(link: FileRelationship) {
  if (link.target_id === 'managed:outline') return flatNodes.value.get('managed:outline')
  if (link.target_id === 'managed:teaching-calendar') return flatNodes.value.get('managed:teaching-calendar')
  if (link.target_id === 'managed:question-bank') return flatNodes.value.get('managed:question-bank')
  if (link.target_id.startsWith('lesson-plan:')) return flatNodes.value.get(`plan:${link.target_id.slice('lesson-plan:'.length)}`)
  if (link.target_id.startsWith('script:')) return flatNodes.value.get(`content:${link.target_id.slice('script:'.length)}`)
  if (link.target_id.startsWith('ppt:')) return flatNodes.value.get(`ppt:${link.target_id.slice('ppt:'.length)}`)
  if (link.target_id.startsWith('question-bank:')) return flatNodes.value.get(`practice:${link.target_id.slice('question-bank:'.length)}`)
  return flatNodes.value.get(link.target_id)
}
function revealRelationshipTarget(link: FileRelationship) {
  const node = relationshipTargetNode(link)
  if (node) revealNode(node)
}
function handleNodeClick(node: WorkspaceNode) {
  closeFileContextMenu()
  if (node.kind === 'folder') { openFolder(node.id); return }
  selectNode(node)
}

function closeFileContextMenu() {
  fileContextMenu.value = { node: null, x: 0, y: 0 }
}

function openFileContextMenu(event: MouseEvent, node: WorkspaceNode) {
  selectNode(node)
  const width = 188
  const height = node.asset ? 154 : 102
  const x = Math.max(8, Math.min(event.clientX, window.innerWidth - width - 8))
  const y = Math.max(8, Math.min(event.clientY, window.innerHeight - height - 8))
  fileContextMenu.value = { node, x, y }
  void nextTick(() => fileContextMenuElement.value?.querySelector<HTMLButtonElement>('button')?.focus())
}

function handleFileRowKeydown(event: KeyboardEvent, node: WorkspaceNode) {
  if (!(event.key === 'ContextMenu' || event.key === 'F10' && event.shiftKey)) return
  event.preventDefault()
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  openFileContextMenu(new MouseEvent('contextmenu', { clientX: rect.left + 32, clientY: rect.top + Math.min(rect.height, 40) }), node)
}

async function runFileContextAction(action: FileContextAction) {
  const node = fileContextMenu.value.node
  closeFileContextMenu()
  if (!node) return
  if (action === 'primary') await primaryAction(node)
  else if (action === 'download' && node.asset) await downloadAsset(node.asset)
  else if (action === 'export') await exportManagedNode(node)
  else if (action === 'delete' && node.asset) await deleteAsset(node.asset)
}

function handleOutsidePointer(event: PointerEvent) {
  if (!fileContextMenu.value.node || fileContextMenuElement.value?.contains(event.target as HTMLElement)) return
  closeFileContextMenu()
}

function primaryLabel(node: WorkspaceNode) {
  if (node.kind === 'folder') return t('courseFiles.openFolder')
  if (node.asset) return t('courseFiles.preview')
  if (node.type === 'outline_export') return node.status === 'missing' ? t('courseFiles.workbench.createOutline') : t('courseFiles.exportFile')
  if (node.type === 'outline') return node.status === 'missing' ? t('courseFiles.workbench.createOutline') : t('courseFiles.openEdit')
  if (node.type === 'teaching_calendar') return node.status === 'missing' ? t('courseFiles.workbench.createTeachingCalendar') : t('courseFiles.openEdit')
  if (node.type === 'lesson_plan') return node.status === 'missing' ? t('courseFiles.workbench.createLessonPlan') : t('courseFiles.openEdit')
  if (node.type === 'content') return node.status === 'missing' ? t('courseFiles.createContent') : t('courseFiles.openContent')
  if (node.type === 'ppt') return node.status === 'missing' ? t('courseFiles.createPpt') : t('courseFiles.openPpt')
  if (node.type === 'practice') return node.status === 'missing' ? t('courseFiles.createPractice') : t('courseFiles.openPractice')
  if (node.type === 'question_bank' || node.type === 'exam_paper') return t('courseFiles.openQuestionBank')
  if (node.type === 'companion_document') return t('courseFiles.openEdit')
  return t('courseFiles.open')
}
function primaryIcon(node: WorkspaceNode) { return markRaw(node.kind === 'folder' ? FolderOpen : node.asset ? Eye : node.type === 'outline_export' && node.status !== 'missing' ? Download : node.status === 'missing' ? Sparkles : Pencil) }
function primaryDisabled(_node: WorkspaceNode) { return false }
function lessonPlanRevision(lessonId: string) { return lessons.value.find(item => item.lesson_unit_id === lessonId)?.plan.working_revision_id || '' }

async function primaryAction(node: WorkspaceNode) {
  selectNode(node)
  if (node.kind === 'folder') { openFolder(node.id); return }
  if (node.asset) { await previewFile(node.asset); return }
  if (node.type === 'outline_export') {
    if (node.status === 'missing') emit('createOutline')
    else await exportManagedNode(node)
    return
  }
  if (node.type === 'outline') { node.status === 'missing' ? openCreateDialog('outline') : emit('openOutline'); return }
  if (node.type === 'teaching_calendar') { emit('openTeachingCalendar'); return }
  if (node.type === 'lesson_plan') { node.status === 'missing' ? openCreateDialog('lesson_plan', node.lessonId) : emit('openTeachingPlan', node.lessonId || ''); return }
  if (node.type === 'content') {
    node.status === 'missing'
      ? emit('openTasks')
      : emit('openScript', node.lessonId || '')
    return
  }
  if (node.type === 'ppt') {
    node.status === 'missing'
      ? emit('openPpt', node.lessonId || '')
      : router.push({ name: 'ppt-workspace', params: { courseId: props.courseId }, query: { lesson: node.lessonId } })
    return
  }
  if (node.type === 'practice') { node.status === 'missing' ? openCreateDialog('practice', node.lessonId) : emit('openPractice', node.lessonId || ''); return }
  if (node.type === 'question_bank' || node.type === 'exam_paper') { emit('openQuestionBank'); return }
  if (node.type === 'companion_document') { emit('openCompanionDocuments'); return }
}

const canExportManaged = (node: WorkspaceNode) => node.kind === 'managed'
  && node.status !== 'missing'
  && ['outline', 'outline_export', 'teaching_calendar', 'lesson_plan', 'content', 'ppt', 'companion_document'].includes(node.type)

function readableNodeContent(node: Node) {
  if (node.node_content?.trim()) return node.node_content.trim()
  return (node.content_blocks || [])
    .filter(block => block.content?.trim())
    .map(block => `${block.title ? `### ${block.title}\n\n` : ''}${block.content.trim()}`)
    .join('\n\n')
}

function outlineMarkdown() {
  const title = selected.value?.course_name || courseTitle.value || t('courseFiles.names.outline')
  const lines = [`# ${title}`, '']
  courseStore.nodes.forEach(node => {
    const level = Math.min(6, Math.max(2, Number(node.node_level || 1) + 1))
    lines.push(`${'#'.repeat(level)} ${node.node_name}`, '')
    if (node.learning_objective) lines.push(`> ${node.learning_objective}`, '')
  })
  return `${lines.join('\n').trim()}\n`
}

function lessonContentMarkdown(lesson: TeacherLessonProjection) {
  const nodes = lessonContentNodes(lesson)
  const minimumLevel = Math.min(...nodes.map(node => Number(node.node_level || 1)), 1)
  const lines = [`# ${lesson.title}`, '']
  nodes.forEach(node => {
    const content = readableNodeContent(node)
    const isLessonRoot = node.node_id === lesson.lesson_unit_id || node.node_name === lesson.title
    if (!isLessonRoot) {
      const level = Math.min(6, Math.max(2, Number(node.node_level || 1) - minimumLevel + 2))
      lines.push(`${'#'.repeat(level)} ${node.node_name}`, '')
    }
    if (content) lines.push(content, '')
  })
  return `${lines.join('\n').trim()}\n`
}

const exportKeyLabel = (key: string) => ({
  objectives: t('courseFiles.exportLabels.objectives'),
  key_points: t('courseFiles.exportLabels.keyPoints'),
  difficult_points: t('courseFiles.exportLabels.difficultPoints'),
  teaching_process: t('courseFiles.exportLabels.teachingProcess'),
  activities: t('courseFiles.exportLabels.activities'),
  assessment: t('courseFiles.exportLabels.assessment'),
  homework: t('courseFiles.exportLabels.homework'),
}[key] || key.replace(/_/g, ' '))

function planValueMarkdown(value: unknown, depth = 2): string {
  if (value === null || value === undefined || value === '') return ''
  if (typeof value !== 'object') return `${String(value)}\n\n`
  if (Array.isArray(value)) {
    if (value.every(item => typeof item !== 'object' || item === null)) return `${value.map(item => `- ${String(item)}`).join('\n')}\n\n`
    return value.map((item, index) => `${'#'.repeat(Math.min(6, depth))} ${index + 1}\n\n${planValueMarkdown(item, depth + 1)}`).join('')
  }
  return Object.entries(value as Record<string, unknown>).map(([key, item]) => {
    const body = planValueMarkdown(item, depth + 1)
    return body ? `${'#'.repeat(Math.min(6, depth))} ${exportKeyLabel(key)}\n\n${body}` : ''
  }).join('')
}

function lessonPlanMarkdown(lesson: TeacherLessonProjection) {
  const revision = lesson.plan.revisions.find(item => item.revision_id === lesson.plan.working_revision_id)
  return `# ${lesson.title} · ${t('courseFiles.names.lessonPlan')}\n\n${planValueMarkdown(revision?.plan || {})}`.trimEnd() + '\n'
}

function lessonPptMarkdown(lesson: TeacherLessonProjection) {
  const asset = lesson.plan.ppt_assets.find(item => item.role === 'primary') || lesson.plan.ppt_assets[0]
  const revision = asset?.revisions.find(item => item.revision_id === asset.working_revision_id)
  const slides = revision?.deck?.slides || []
  if (!slides.length) return ''
  const title = revision?.deck?.title || `${lesson.title} · ${t('courseFiles.names.ppt')}`
  const body = slides.map((slide, index) => {
    const lines = [`## ${index + 1}. ${slide.title}`]
    if (slide.body?.length) lines.push('', ...slide.body.map(item => `- ${item}`))
    if (slide.speaker_notes?.trim()) lines.push('', `> ${slide.speaker_notes.trim()}`)
    return lines.join('\n')
  }).join('\n\n')
  return `# ${title}\n\n${body}\n`
}

function previewMarkdown(value: string) {
  return value.replace(/^#\s+[^\n]+\n+/, '').trim()
}

async function exportManagedNode(node: WorkspaceNode) {
  exportingNodeId.value = node.id
  try {
    const lesson = node.lessonId ? lessons.value.find(item => item.lesson_unit_id === node.lessonId) : undefined
    if (node.type === 'outline' || node.type === 'outline_export') {
      downloadBlob(new Blob([outlineMarkdown()], { type: 'text/markdown;charset=utf-8' }), `${safePart(selected.value?.course_name || t('courseFiles.names.outline'))}-${t('courseFiles.names.outline')}.md`)
    } else if (node.type === 'teaching_calendar') {
      const calendar = calendarStore.calendar?.course_id === props.courseId ? calendarStore.calendar : null
      if (!calendar?.sessions.length) throw new Error(t('courseFiles.errors.exportUnavailable'))
      const response = await http.get(`/api/courses/${props.courseId}/teaching-calendar/export`, teacherRequestConfig({
        params: { format: 'docx', revision: calendar.revision },
        responseType: 'blob',
      }))
      downloadBlob(response.data, `${safePart(selected.value?.course_name || courseTitle.value || t('courseFiles.names.teachingCalendar'))}-${t('courseFiles.names.teachingCalendar')}-r${calendar.revision}.docx`)
    } else if (node.type === 'content' && lesson) {
      downloadBlob(new Blob([lessonContentMarkdown(lesson)], { type: 'text/markdown;charset=utf-8' }), `${safePart(lesson.title)}-${t('courseFiles.names.content')}.md`)
    } else if (node.type === 'lesson_plan' && lesson) {
      downloadBlob(new Blob([lessonPlanMarkdown(lesson)], { type: 'text/markdown;charset=utf-8' }), `${safePart(lesson.title)}-${t('courseFiles.names.lessonPlan')}.md`)
    } else if (node.type === 'companion_document' && node.companionDocument) {
      const response = await http.get(
        `/api/courses/${props.courseId}/companion-documents/${node.companionDocument.document_id}/export`,
        teacherRequestConfig({ params: { format: 'docx' }, responseType: 'blob' }),
      )
      downloadBlob(response.data, `${safePart(node.companionDocument.title)}.docx`)
    } else if (node.type === 'ppt' && lesson) {
      const ppt = lesson.plan.ppt_assets.find(item => item.role === 'primary') || lesson.plan.ppt_assets[0]
      if (!ppt) throw new Error(t('courseFiles.errors.exportUnavailable'))
      const useV6 = ppt.engine === 'slide_deck_v6' && ppt.working_representation_id
      const response = await http.get(
        useV6
          ? `/api/teacher/courses/${props.courseId}/lessons/${lesson.lesson_unit_id}/ppt-v6/${ppt.working_representation_id}/export.pptx`
          : `/api/teacher/courses/${props.courseId}/lessons/${lesson.lesson_unit_id}/ppt/export.pptx`,
        teacherRequestConfig({
          ...(useV6 ? {} : { params: { asset_id: ppt.asset_id, revision_id: ppt.working_revision_id } }),
          responseType: 'blob',
        }),
      )
      downloadBlob(response.data, `${safePart(lesson.title)}-${t('courseFiles.names.ppt')}.pptx`)
    } else {
      throw new Error(t('courseFiles.errors.exportUnavailable'))
    }
    ElMessage.success(t('courseFiles.exported'))
  } catch (error: any) {
    ElMessage.error(localizedError(error, String(error?.message || t('courseFiles.errors.exportFailed'))))
  } finally {
    exportingNodeId.value = ''
  }
}

async function refresh() {
  initializing.value = true
  status.value = ''
  try {
    let packages = (await http.get<Package[]>('/api/teacher-course-spaces', teacherRequestConfig({ params: embedded.value && props.courseId ? { course_id: props.courseId } : undefined }))).data
    let match = embedded.value ? packages.find(item => String(item.course_id || '') === props.courseId) : packages[0]
    if (embedded.value && !match && props.courseTitle) {
      const allPackages = (await http.get<Package[]>('/api/teacher-course-spaces', teacherRequestConfig())).data
      const legacyMatches = allPackages.filter((item: any) => !item.course_id && String(item.course_name).trim() === props.courseTitle.trim())
      if (legacyMatches.length === 1 && props.courseId) {
        match = (await http.patch(`/api/teacher-course-spaces/${legacyMatches[0]!.package_id}`, { course_id: props.courseId }, teacherRequestConfig())).data
      }
    }
    if (embedded.value && !match && props.courseTitle) {
      const now = new Date()
      const startYear = now.getMonth() >= 7 ? now.getFullYear() : now.getFullYear() - 1
      match = (await http.post('/api/teacher-course-spaces', { course_name: props.courseTitle, academic_year: `${startYear}-${startYear + 1}`, term: now.getMonth() >= 7 ? '秋季' : '春季', template: 'blank', course_id: props.courseId }, teacherRequestConfig())).data
    }
    if (match) selected.value = (await http.get(`/api/teacher-course-spaces/${match.package_id}`, teacherRequestConfig())).data
    if (props.courseId) {
      await lessonStore.load(props.courseId).catch(() => undefined)
      await calendarStore.loadCourse(props.courseId).catch(() => undefined)
      await loadQuestionBankSummary()
      await loadExamPapers()
      await loadCompanionDocuments()
    }
    const requestedLessonId = String(route.query.lesson || '')
    currentFolderId.value = requestedLessonId && flatNodes.value.has(`lesson:${requestedLessonId}`)
      ? `lesson:${requestedLessonId}`
      : 'root'
    expandedFolderIds.value = folderPath(currentFolderId.value)
    selectedNode.value = null
  } catch (error: any) {
    status.value = localizedError(error, t('courseFiles.spaceUnavailable'))
  } finally { initializing.value = false }
}
async function reloadAll() {
  busy.value = true
  try {
    if (props.courseId) await courseStore.loadCourse(props.courseId, { includeLearningRecords: false, previewSurface: 'teacher', silentError: true })
    await refresh()
  } finally { busy.value = false }
}
async function reloadPackage() { if (selected.value) selected.value = (await http.get(`/api/teacher-course-spaces/${selected.value.package_id}`, teacherRequestConfig())).data }

async function loadQuestionBankSummary() {
  if (!props.courseId) return
  try {
    const response = await http.get(`/api/courses/${props.courseId}/question-bank`, teacherRequestConfig({ silentError: true }))
    questionBankItems.value = Array.isArray(response.data?.items) ? response.data.items : []
    questionBankRevisionId.value = String(response.data?.bundle_revision_id || '')
  } catch (error: any) {
    if (Number(error?.response?.status || 0) === 404) {
      questionBankItems.value = []
      questionBankRevisionId.value = ''
    }
  }
}

async function loadExamPapers() {
  if (!props.courseId) return
  try {
    const response = await http.get(
      `/api/courses/${props.courseId}/question-bank/exam-papers`,
      teacherRequestConfig({ silentError: true }),
    )
    examPapers.value = Array.isArray(response.data?.papers)
      ? response.data.papers
      : []
  } catch {
    examPapers.value = []
  }
}

async function loadCompanionDocuments() {
  if (!props.courseId) return
  try {
    const response = await http.get(
      `/api/courses/${props.courseId}/companion-documents`,
      teacherRequestConfig({ silentError: true }),
    )
    companionDocuments.value = Array.isArray(response.data?.documents)
      ? response.data.documents
      : []
  } catch {
    companionDocuments.value = []
  }
}

function openCreateDialog(command: CreateType | string, lessonId: unknown = '', targetFolderId = '') {
  const type = command as CreateType
  if (type === 'outline') {
    const outline = flatNodes.value.get('managed:outline')
    if (outline?.status === 'missing') emit('createOutline')
    else emit('openOutline')
    return
  }
  const targetLessonId = typeof lessonId === 'string' && lessonId ? lessonId : currentFolder.value?.lessonId || ''
  if (['lesson_plan', 'ppt', 'practice'].includes(type) && targetLessonId) {
    const existing = [...flatNodes.value.values()].find(node => node.type === type && node.lessonId === targetLessonId && node.status !== 'missing')
    if (existing) {
      selectedNode.value = existing
      void primaryAction(existing)
      return
    }
  }
  const targetFolder = flatNodes.value.get(targetFolderId) || currentFolder.value
  if (type === 'folder' && targetFolder?.kind !== 'folder') return
  resetCreateForm()
  createType.value = type
  createTargetFolderId.value = targetFolder?.id || ''
  createForm.value.lessonId = targetLessonId
  createOpen.value = true
  void nextTick(() => createDialog.value?.focus())
}
function closeCreateDialog() { createOpen.value = false; resetCreateForm() }
const dialogTitle = computed(() => t(`courseFiles.dialog.${createType.value}.title`))
const needsLesson = computed(() => ['lesson_plan', 'ppt', 'practice'].includes(createType.value) && !createForm.value.lessonId)
const createLocationLabel = computed(() => {
  if (needsLesson.value && !createForm.value.lessonId) {
    const typeKey = createType.value === 'lesson_plan' ? 'lessonPlan' : createType.value
    return `${t('courseFiles.rootName')} / ${t('courseFiles.form.selectLesson')} / ${t(`courseFiles.types.${typeKey}`)}`
  }
  const path = targetPath(createType.value, createForm.value.lessonId)
  return path ? `${t('courseFiles.rootName')} / ${displayPath(path)}` : t('courseFiles.rootName')
})
const requirementsPlaceholder = computed(() => t(`courseFiles.dialog.${createType.value}.requirements`))
const sourceFileLabel = computed(() => createType.value === 'ppt'
  ? createForm.value.mode === 'import' ? t('courseFiles.form.oldDeckFile') : t('courseFiles.form.templateFile')
  : t('courseFiles.form.sourceFile'))
const submitLabel = computed(() => {
  if (createType.value === 'ppt') return createForm.value.mode === 'import' ? t('courseFiles.form.importOldDeck') : t('courseFiles.form.generatePpt')
  if (createForm.value.file) return t('courseFiles.form.importAndCreate')
  if (createType.value === 'folder') return t('courseFiles.createFolder')
  if (createType.value === 'material') return t('courseFiles.createFile')
  return t('courseFiles.form.startCreate')
})
const pptAiBlocked = computed(() => createType.value === 'ppt'
  && createForm.value.mode === 'ai'
  && Boolean(createForm.value.lessonId)
  && !lessonPlanRevision(createForm.value.lessonId))
const submitDisabled = computed(() => busy.value
  || needsLesson.value && !createForm.value.lessonId
  || createType.value === 'ppt' && createForm.value.mode === 'import' && !createForm.value.file
  || pptAiBlocked.value)
function captureImportFile(event: Event) { const input = event.target as HTMLInputElement; createForm.value.file = input.files?.[0] || null; input.value = '' }
function resetCreateForm() {
  createTargetFolderId.value = ''
  createForm.value = { lessonId: '', title: '', hours: '2', mode: 'ai', count: 12, style: 'simple', difficulty: 'mixed', requirements: '', pptImportAction: 'derive_plan', file: null }
}
function createLessonPlanFirst() {
  const lessonId = createForm.value.lessonId
  closeCreateDialog()
  openCreateDialog('lesson_plan', lessonId)
}

function targetPath(type: CreateType, _lessonId: string) {
  const folder = createTargetFolder.value
  if (type === 'folder') {
    if (folder && ['supporting_materials', 'aux_question_bank', 'aux_exam_papers', 'aux_student_work', 'aux_other', 'folder'].includes(folder.type) && folder.path.startsWith('辅助资料')) return folder.type === 'supporting_materials' ? '辅助资料/其他资料' : folder.path
    return '辅助资料/其他资料'
  }
  if (type === 'material') {
    if (folder && ['supporting_materials', 'aux_question_bank', 'aux_exam_papers', 'aux_student_work', 'aux_other', 'folder'].includes(folder.type) && folder.path.startsWith('辅助资料')) return folder.type === 'supporting_materials' ? '辅助资料/其他资料' : folder.path
    return '辅助资料/其他资料'
  }
  if (type === 'lesson_plan') return '辅助资料/其他资料'
  if (type === 'ppt') return '辅助资料/其他资料'
  if (type === 'practice') return '辅助资料/其他资料'
  return folder?.path || ''
}

function handleFileDragEnter(event: DragEvent) {
  if (!canBatchImport.value || query.value.trim() || !event.dataTransfer?.types.includes('Files')) return
  fileDragDepth.value += 1
  fileDragActive.value = true
}

function handleFileDragLeave() {
  if (!fileDragActive.value) return
  fileDragDepth.value = Math.max(0, fileDragDepth.value - 1)
  if (!fileDragDepth.value) fileDragActive.value = false
}

async function readDroppedEntry(entry: any, prefix = ''): Promise<BatchImportFile[]> {
  if (entry?.isFile) {
    const file = await new Promise<File>((resolve, reject) => entry.file(resolve, reject))
    return [{ file, relativePath: `${prefix}${file.name}` }]
  }
  if (!entry?.isDirectory) return []
  const directoryPrefix = `${prefix}${entry.name}/`
  const reader = entry.createReader()
  const children: any[] = []
  while (true) {
    const batch = await new Promise<any[]>((resolve, reject) => reader.readEntries(resolve, reject))
    if (!batch.length) break
    children.push(...batch)
  }
  const nested = await Promise.all(children.map(child => readDroppedEntry(child, directoryPrefix)))
  return nested.flat()
}

async function collectDroppedFiles(dataTransfer: DataTransfer): Promise<BatchImportFile[]> {
  const entries = [...dataTransfer.items]
    .filter(item => item.kind === 'file')
    .map(item => (item as DataTransferItem & { webkitGetAsEntry?: () => any }).webkitGetAsEntry?.())
    .filter(Boolean)
  if (entries.length) return (await Promise.all(entries.map(entry => readDroppedEntry(entry)))).flat()
  return [...dataTransfer.files].map(file => ({ file, relativePath: file.name }))
}

async function handleFileDrop(event: DragEvent) {
  fileDragDepth.value = 0
  fileDragActive.value = false
  if (!canBatchImport.value || query.value.trim() || !event.dataTransfer) return
  try {
    const files = await collectDroppedFiles(event.dataTransfer)
    if (files.length) await importBatchFiles(files)
  } catch {
    ElMessage.error(t('courseFiles.preparation.readFolderFailed'))
  }
}

async function captureBatchSelection(event: Event, preserveFolderPath: boolean) {
  const input = event.target as HTMLInputElement
  const files = [...(input.files || [])].map(file => ({
    file,
    relativePath: preserveFolderPath
      ? (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name
      : file.name,
  }))
  input.value = ''
  if (files.length) await importBatchFiles(files)
}

async function importBatchFiles(files: BatchImportFile[]) {
  if (!selected.value || !files.length) return
  busy.value = true
  status.value = t('courseFiles.importingMaterials').replace('{count}', String(files.length))
  try {
    const basePath = currentFolder.value?.type === 'root' ? '' : targetPath('material', '')
    const data = new FormData()
    files.forEach(({ file, relativePath }) => {
      const cleanPath = relativePath.replace(/\\/g, '/').replace(/^\/+/, '') || file.name
      data.append('files', file, file.name)
      data.append('relative_paths', basePath ? `${basePath}/${cleanPath}` : cleanPath)
    })
    const response = await http.post(`/api/teacher-course-spaces/${selected.value.package_id}/imports`, data, teacherRequestConfig())
    selected.value = response.data.package
    selectedNode.value = null
    const outcomes = Array.isArray(response.data.outcomes) ? response.data.outcomes : []
    const imported = outcomes.filter((item: any) => item.outcome === 'imported').length
    const duplicate = outcomes.filter((item: any) => item.outcome === 'duplicate').length
    const rejected = outcomes.filter((item: any) => item.outcome === 'rejected').length
    const summary = t('courseFiles.importSummary')
      .replace('{imported}', String(imported))
      .replace('{duplicate}', String(duplicate))
      .replace('{rejected}', String(rejected))
    rejected ? ElMessage.warning(summary) : ElMessage.success(summary)
  } catch (error: any) {
    ElMessage.error(localizedError(error, t('courseFiles.preparation.importFailed')))
  } finally {
    busy.value = false
    status.value = ''
  }
}

async function updateAssetDocumentType(asset: Asset, event: Event) {
  if (!selected.value) return
  const documentType = (event.target as HTMLSelectElement).value as DocumentType
  const selectedId = selectedNode.value?.id || ''
  classifyingAssetId.value = asset.asset_id
  try {
    await http.patch(
      `/api/teacher-course-spaces/${selected.value.package_id}/assets/${asset.asset_id}`,
      { document_type: documentType },
      teacherRequestConfig(),
    )
    await reloadPackage()
    selectedNode.value = flatNodes.value.get(selectedId) || null
    ElMessage.success(t('courseFiles.classificationSaved'))
  } catch (error: any) {
    ElMessage.error(localizedError(error, t('courseFiles.preparation.classificationFailed')))
  } finally {
    classifyingAssetId.value = ''
  }
}

async function uploadFile(file: File, path: string): Promise<Asset | null> {
  if (!selected.value) return null
  const data = new FormData(); data.append('files', file); data.append('relative_paths', path ? `${path}/${file.name}` : file.name)
  const result = (await http.post(`/api/teacher-course-spaces/${selected.value.package_id}/imports`, data, teacherRequestConfig())).data
  selected.value = result.package
  const relativePath = path ? `${path}/${file.name}` : file.name
  const outcome = result.outcomes?.find((item: Asset & { outcome?: string; error?: string }) => item.relative_path === relativePath)
  if (outcome?.outcome === 'rejected') throw new Error(outcome.error || t('courseFiles.errors.createFailed'))
  return outcome?.asset_id ? outcome : selected.value?.assets.find(item => item.relative_path === relativePath) || null
}
async function attachAssetToFormal(asset: Asset, targetId: string, targetType: string, targetLabel: string, role: 'primary' | 'reference') {
  if (!selected.value || !targetId) return
  const sources = (selected.value.relationships || [])
    .filter(link => link.target_id === targetId && link.source_asset_id !== asset.asset_id)
    .map(link => ({ source_asset_id: link.source_asset_id, role: link.role }))
  const response = await http.put(`/api/teacher-course-spaces/${selected.value.package_id}/relationships`, {
    target_id: targetId,
    target_type: targetType,
    target_label: targetLabel,
    sources: [...sources, { source_asset_id: asset.asset_id, role }],
  }, teacherRequestConfig({ silentError: true }))
  if (response.data?.package) selected.value = response.data.package
}
async function submitCreate() {
  if (!selected.value) return
  busy.value = true
  try {
    if (createType.value === 'folder') {
      const path = targetPath('folder', '')
      await http.post(`/api/teacher-course-spaces/${selected.value.package_id}/folders`, { name: path ? `${path}/${createForm.value.title}` : createForm.value.title }, teacherRequestConfig())
    } else if (createType.value === 'ppt') {
      if (createForm.value.mode === 'import') {
        if (!createForm.value.file) throw new Error(t('courseFiles.errors.selectOldDeck'))
        const uploaded = await uploadFile(createForm.value.file, targetPath('ppt', createForm.value.lessonId))
        if (createForm.value.pptImportAction === 'derive_plan' && uploaded) {
          const lesson = lessons.value.find(item => item.lesson_unit_id === createForm.value.lessonId)
          await attachAssetToFormal(uploaded, `lesson-plan:${createForm.value.lessonId}`, 'lesson_plan', `${lesson?.title || createForm.value.lessonId} · ${t('courseFiles.names.lessonPlan')}`, 'primary')
          await lessonStore.generateLesson(props.courseId, createForm.value.lessonId, {
            packageId: selected.value.package_id,
            assetId: uploaded.asset_id,
          })
        } else if (uploaded) {
          const lesson = lessons.value.find(item => item.lesson_unit_id === createForm.value.lessonId)
          await attachAssetToFormal(uploaded, `ppt:${createForm.value.lessonId}`, 'ppt', `${lesson?.title || createForm.value.lessonId} · ${t('courseFiles.names.ppt')}`, 'primary')
        }
      } else {
        const revision = lessonPlanRevision(createForm.value.lessonId)
        if (!revision) throw new Error(t('courseFiles.errors.createLessonFirst'))
        if (createForm.value.style === 'template' && createForm.value.file) {
          const uploaded = await uploadFile(createForm.value.file, targetPath('ppt', createForm.value.lessonId))
          if (uploaded) {
            const lesson = lessons.value.find(item => item.lesson_unit_id === createForm.value.lessonId)
            await attachAssetToFormal(uploaded, `ppt:${createForm.value.lessonId}`, 'ppt', `${lesson?.title || createForm.value.lessonId} · ${t('courseFiles.names.ppt')}`, 'reference')
          }
        }
        const lessonId = createForm.value.lessonId
        closeCreateDialog()
        await router.push({ name: 'ppt-workspace', params: { courseId: props.courseId }, query: { lesson: lessonId } })
        return
      }
    } else if (createForm.value.file) {
      const uploaded = await uploadFile(createForm.value.file, targetPath(createType.value, createForm.value.lessonId))
      if (uploaded && createForm.value.lessonId && createType.value === 'lesson_plan') {
        const lesson = lessons.value.find(item => item.lesson_unit_id === createForm.value.lessonId)
        await attachAssetToFormal(uploaded, `lesson-plan:${createForm.value.lessonId}`, 'lesson_plan', `${lesson?.title || createForm.value.lessonId} · ${t('courseFiles.names.lessonPlan')}`, 'primary')
      } else if (uploaded && createForm.value.lessonId && createType.value === 'material') {
        const lesson = lessons.value.find(item => item.lesson_unit_id === createForm.value.lessonId)
        await attachAssetToFormal(uploaded, `lesson-plan:${createForm.value.lessonId}`, 'lesson_plan', `${lesson?.title || createForm.value.lessonId} · ${t('courseFiles.names.lessonPlan')}`, 'reference')
      }
    } else if (createType.value === 'outline') {
      emit('openOutline')
    } else if (createType.value === 'lesson_plan') {
      await lessonStore.generateLesson(props.courseId, createForm.value.lessonId)
    } else if (createType.value === 'practice') {
      const lessonId = createForm.value.lessonId
      const lesson = lessons.value.find(item => item.lesson_unit_id === lessonId)
      if (!lesson) throw new Error(t('courseFiles.errors.selectLesson'))
      if (!practiceNodeIds(lesson).length) throw new Error(t('courseFiles.errors.practiceNeedsSections'))
      closeCreateDialog()
      emit('openPractice', lessonId)
      return
    } else if (createType.value === 'material') {
      const name = `${safePart(createForm.value.title || t('courseFiles.names.newMaterial'))}.md`
      const uploaded = await uploadFile(new File([`# ${createForm.value.title}\n\n${createForm.value.requirements}\n`], name, { type: 'text/markdown' }), targetPath('material', createForm.value.lessonId))
      if (uploaded && createForm.value.lessonId) {
        const lesson = lessons.value.find(item => item.lesson_unit_id === createForm.value.lessonId)
        await attachAssetToFormal(uploaded, `lesson-plan:${createForm.value.lessonId}`, 'lesson_plan', `${lesson?.title || createForm.value.lessonId} · ${t('courseFiles.names.lessonPlan')}`, 'reference')
      }
    }
    await reloadPackage()
    await lessonStore.load(props.courseId).catch(() => undefined)
    closeCreateDialog()
    ElMessage.success(t('courseFiles.created'))
  } catch (error: any) { ElMessage.error(localizedError(error, String(error?.message || t('courseFiles.errors.createFailed')))) } finally { busy.value = false }
}
async function previewFile(asset: Asset) {
  if (!selected.value) return
  try {
    const response = await http.get(`/api/teacher-course-spaces/${selected.value.package_id}/assets/${asset.asset_id}/preview`, teacherRequestConfig({ responseType: 'blob' }))
    previewUrl.value = URL.createObjectURL(response.data); previewAsset.value = asset; previewOpen.value = true
  } catch { ElMessage.error(t('courseFiles.errors.previewFailed')) }
}
const previewKind = computed(() => {
  const ext = previewAsset.value?.extension.toLowerCase() || ''
  if (['.png', '.jpg', '.jpeg', '.webp', '.bmp'].includes(ext)) return 'image'
  if (['.pdf', '.md', '.markdown', '.txt', '.csv', '.json', '.html'].includes(ext)) return 'browser'
  return 'office'
})
const previewDialogWidth = computed(() => `${Math.min(typeof window === 'undefined' ? 920 : window.innerWidth - 40, 1100)}px`)
function closePreview() { if (previewUrl.value) URL.revokeObjectURL(previewUrl.value); previewUrl.value = ''; previewAsset.value = null }
async function downloadAsset(asset: Asset) { if (!selected.value) return; const response = await http.get(`/api/teacher-course-spaces/${selected.value.package_id}/assets/${asset.asset_id}/download`, teacherRequestConfig({ responseType: 'blob' })); downloadBlob(response.data, asset.filename) }
async function downloadPackage() { if (!selected.value) return; const response = await http.get(`/api/teacher-course-spaces/${selected.value.package_id}/export`, teacherRequestConfig({ responseType: 'blob' })); downloadBlob(response.data, `${selected.value.course_name}-${t('courseFiles.archiveName')}.zip`) }
function downloadBlob(blob: Blob, name: string) { const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 100) }
async function deleteAsset(asset: Asset) {
  if (!selected.value) return
  try {
    await ElMessageBox.confirm(t('courseFiles.deleteConfirm').replace('{name}', asset.filename), t('courseFiles.delete'), { type: 'warning', confirmButtonText: t('courseFiles.delete'), cancelButtonText: t('common.cancel') })
    await http.delete(`/api/teacher-course-spaces/${selected.value.package_id}/assets/${asset.asset_id}`, teacherRequestConfig())
    selectedNode.value = null; await reloadPackage(); ElMessage.success(t('courseFiles.deleted'))
  } catch (error: any) { if (error !== 'cancel' && error !== 'close') ElMessage.error(localizedError(error, t('courseFiles.errors.deleteFailed'))) }
}

watch(readinessSummary, summary => emit('readinessChange', summary), { immediate: true })
watch(
  () => [calendarStore.calendar?.course_id, calendarStore.calendar?.revision, calendarStore.calendar?.updated_at],
  () => {
    if (selectedNode.value?.id === 'managed:teaching-calendar') {
      selectedNode.value = flatNodes.value.get('managed:teaching-calendar') || selectedNode.value
    }
  },
)
onMounted(() => {
  window.addEventListener('pointerdown', handleOutsidePointer)
  window.addEventListener('resize', closeFileContextMenu)
  void refresh()
})
onBeforeUnmount(() => {
  window.removeEventListener('pointerdown', handleOutsidePointer)
  window.removeEventListener('resize', closeFileContextMenu)
})
</script>

<style scoped>
.file-space,.file-space *{box-sizing:border-box}.file-space{height:100%;min-height:0;color:var(--lz-text-strong);background:#f8fafc;font-size:14px}.standalone-header{position:relative;height:68px;display:flex;align-items:center;justify-content:space-between;padding:0 24px;border-bottom:1px solid var(--lz-border);background:#fff}.standalone-header small,.standalone-header h1{display:block;margin:0}.standalone-header small{color:var(--lz-text-muted);font-size:13px}.standalone-header h1{font-size:20px}.standalone-header-actions{display:flex;align-items:center;gap:10px}.standalone-header-actions>button{height:38px;display:flex;align-items:center;gap:7px;padding:0 10px;border:0;border-radius:8px;color:var(--lz-text-secondary);background:transparent;font-size:14px;cursor:pointer}.standalone-header-actions>button:hover{color:var(--lz-brand-strong);background:var(--lz-brand-soft)}
.workspace-ready{height:100%;min-height:0;overflow:hidden}.workspace-view-switch{position:absolute;left:50%;top:50%;display:inline-flex;align-items:center;gap:3px;padding:3px;border:1px solid var(--lz-border);border-radius:10px;background:#f5f6fa;transform:translate(-50%,-50%)}.workspace-view-switch button{height:32px;display:inline-flex;align-items:center;gap:6px;padding:0 11px;border:0;border-radius:7px;color:var(--lz-text-secondary);background:transparent;font-size:12px;font-weight:700;cursor:pointer}.workspace-view-switch button:hover{color:var(--lz-text-strong)}.workspace-view-switch button.active{color:var(--lz-brand-strong);background:#fff;box-shadow:0 2px 7px rgba(15,23,42,.08)}.workspace-view-switch button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:2px}
.file-layout{height:100%;min-height:0;display:grid;grid-template-columns:260px minmax(560px,1fr) 312px;overflow:hidden;background:#fff}.file-tree-pane,.file-list-pane,.file-inspector{min-height:0;overflow:hidden}.file-tree-pane{display:grid;grid-template-rows:auto minmax(0,1fr) auto;border-right:1px solid var(--lz-border);background:#f8fafc}.pane-heading{min-height:56px;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:0 14px;border-bottom:1px solid #e8edf4}.pane-heading>span{min-width:0;display:flex;align-items:center;gap:8px;color:#475569}.pane-heading>span>svg{color:#64748b}.pane-heading strong{overflow:hidden;font-size:14px;text-overflow:ellipsis;white-space:nowrap}.pane-heading button,.file-inspector header>button{width:32px;height:32px;display:grid;place-items:center;padding:0;border:0;border-radius:7px;background:transparent;color:var(--lz-text-muted);cursor:pointer}.pane-heading button:hover,.file-inspector header>button:hover{color:var(--lz-text-strong);background:#eef2f7}.folder-navigation{min-height:0;overflow:auto;padding:9px 8px 16px}.folder-navigation>ul{margin:0;padding:0;list-style:none}.file-tree-pane footer{display:grid;gap:9px;padding:14px;border-top:1px solid var(--lz-border);color:var(--lz-text-muted);font-size:12px}.file-tree-pane footer button{display:flex;align-items:center;gap:7px;padding:0;border:0;background:transparent;color:var(--lz-text-secondary);font-size:13px;font-weight:700;cursor:pointer}
.category-layout{height:100%;min-height:0;display:grid;grid-template-columns:272px minmax(0,1fr);overflow:hidden;background:#fff}.category-navigation{min-height:0;overflow:auto;padding:18px 12px;border-right:1px solid var(--lz-border);background:#f8fafc}.category-navigation>header{display:grid;gap:5px;padding:0 8px 15px}.category-navigation>header strong{font-size:14px}.category-navigation>header small{color:var(--lz-text-muted);font-size:12px;line-height:1.45}.category-navigation nav{display:grid;gap:5px}.category-group{min-width:0}.category-group__button{width:100%;min-width:0;min-height:58px;display:grid;grid-template-columns:18px minmax(0,1fr) auto;align-items:center;gap:10px;padding:9px 10px;border:1px solid transparent;border-radius:10px;color:var(--lz-text-muted);background:transparent;text-align:left;cursor:pointer}.category-group__button:hover{background:#fff}.category-group__button.active{border-color:rgba(99,102,241,.2);color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.category-group__button>span:nth-child(2){min-width:0;display:grid;gap:3px}.category-group__button strong,.category-group__button small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.category-group__button strong{color:var(--lz-text-secondary);font-size:13px}.category-group__button small{color:var(--lz-text-muted);font-size:12px}.category-group__button.active strong{color:var(--lz-brand-strong)}.category-group__trailing{display:flex;align-items:center;gap:4px}.category-group__trailing b{min-width:30px;color:var(--lz-text-muted);font-size:11px;text-align:right;font-variant-numeric:tabular-nums}.category-group__trailing b[data-state="ready"]{color:var(--lz-success)}.category-group__trailing b[data-state="working"]{color:var(--lz-brand-strong)}.category-group__trailing b[data-state="attention"]{color:var(--lz-warning)}.category-group__chevron{transition:transform .16s ease}.category-group.active .category-group__chevron{transform:rotate(90deg)}.category-children{display:grid;gap:2px;margin:3px 5px 9px 26px;padding-left:11px;border-left:1px solid #dbe2ec}.category-child{width:100%;min-width:0;min-height:38px;display:grid;grid-template-columns:28px minmax(0,1fr) 8px;align-items:center;gap:7px;padding:5px 8px;border:0;border-radius:7px;color:var(--lz-text-secondary);background:transparent;text-align:left;cursor:pointer}.category-child:hover{background:#fff}.category-child.active{color:var(--lz-brand-strong);background:#fff;box-shadow:0 1px 3px rgba(15,23,42,.08)}.category-child__index{color:var(--lz-text-muted);font-size:11px;font-variant-numeric:tabular-nums}.category-child__name{overflow:hidden;font-size:12px;font-weight:650;text-overflow:ellipsis;white-space:nowrap}.category-child .status-dot{margin:0}.category-group__button:focus-visible,.category-child:focus-visible,.category-detail-actions button:focus-visible,.category-detail-empty button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:2px}.category-detail-pane{min-width:0;min-height:0;display:grid;grid-template-rows:auto minmax(0,1fr);overflow:hidden;background:#f8fafc}.category-detail-header{min-height:84px;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:13px 24px;border-bottom:1px solid var(--lz-border);background:#fff}.category-detail-header>div:first-child{min-width:0;display:grid;grid-template-columns:auto 1fr;align-items:center;gap:4px 12px}.category-detail-header small{grid-column:1/-1;color:var(--lz-text-muted);font-size:12px}.category-detail-header h2{min-width:0;margin:0;overflow:hidden;font-size:20px;text-overflow:ellipsis;white-space:nowrap}.category-detail-status{display:inline-flex;align-items:center;color:var(--lz-text-muted);font-size:12px;white-space:nowrap}.category-detail-status .status-dot{margin-right:6px}.category-detail-actions{flex:none;display:flex;align-items:center;gap:8px}.category-detail-actions button,.category-detail-empty button{min-height:36px;display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:0 12px;border:1px solid var(--lz-border);border-radius:8px;color:var(--lz-text-secondary);background:#fff;font-size:12px;font-weight:700;cursor:pointer}.category-detail-actions button.primary,.category-detail-empty button.primary{border-color:var(--lz-brand);color:#fff;background:var(--lz-brand)}.category-detail-actions button:hover:not(:disabled){border-color:var(--lz-brand-border);color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.category-detail-actions button.primary:hover:not(:disabled){border-color:var(--lz-brand-strong);color:#fff;background:var(--lz-brand-strong)}.category-detail-actions button:disabled,.category-detail-empty button:disabled{opacity:.45;cursor:not-allowed}.category-document-scroll{min-height:0;overflow:auto;padding:28px 32px 48px}.category-document{width:min(940px,100%);min-height:calc(100% - 4px);margin:0 auto;padding:32px 42px 52px;border:1px solid #e2e8f0;border-radius:12px;background:#fff;box-shadow:0 8px 24px rgba(15,23,42,.05)}.category-document :deep(.markdown-renderer){color:var(--lz-text-secondary);font-size:14px;line-height:1.75}.category-document :deep(.markdown-renderer> :first-child){margin-top:0}.category-document :deep(h2){margin:28px 0 12px;color:var(--lz-text-strong);font-size:20px}.category-document :deep(h3){margin:22px 0 10px;color:var(--lz-text-strong);font-size:16px}.category-document :deep(p),.category-document :deep(ul),.category-document :deep(ol){margin:10px 0}.category-document :deep(blockquote){margin:14px 0;padding:10px 14px;border:1px solid var(--lz-brand-border);border-radius:8px;color:var(--lz-text-secondary);background:var(--lz-brand-soft)}.category-detail-empty{min-height:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:9px;padding:28px;color:var(--lz-text-muted);text-align:center}.category-detail-empty>svg{color:#94a3b8}.category-detail-empty strong{color:var(--lz-text-secondary);font-size:16px}.category-detail-empty>span{max-width:380px;font-size:13px;line-height:1.6}.category-detail-empty button{margin-top:5px}
.file-list-pane{position:relative;display:flex;flex-direction:column;background:#fff}.file-list-pane.is-dragging-files{background:#fafaff}.list-toolbar{min-height:58px;flex:none;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 18px;border-bottom:1px solid var(--lz-border)}.list-toolbar nav{min-width:0;display:flex;align-items:center;gap:4px;overflow:hidden}.list-toolbar nav button{display:flex;align-items:center;gap:6px;min-width:0;padding:5px;border:0;background:transparent;color:var(--lz-text-secondary);font-size:13px;white-space:nowrap;cursor:pointer}.list-toolbar nav svg{flex:none;color:#94a3b8}.toolbar-actions{display:flex;align-items:center;gap:8px}.list-search{width:248px;height:40px;display:flex;align-items:center;gap:8px;padding:0 10px 0 12px;border:1px solid transparent;border-radius:10px;color:#94a3b8;background:#f1f5f9;transition:border-color .15s ease,background .15s ease,box-shadow .15s ease}.list-search:focus-within{border-color:var(--lz-brand-border);background:#fff;box-shadow:0 0 0 3px var(--lz-brand-soft)}.list-search input{min-width:0;width:100%;border:0;outline:0;color:var(--lz-text-strong);background:transparent;font-size:13px}.list-search input::-webkit-search-cancel-button{display:none}.list-search button{width:26px;height:26px;flex:none;display:grid;place-items:center;padding:0;border:0;border-radius:6px;color:#64748b;background:transparent;cursor:pointer}.list-search button:hover{color:var(--lz-text-strong);background:#e2e8f0}.list-search button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:2px}
.folder-title{min-height:66px;flex:none;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:9px 18px}.folder-title h2{min-width:0;margin:0;overflow:hidden;font-size:20px;text-overflow:ellipsis;white-space:nowrap}.folder-title__actions{flex:none;display:flex;align-items:center;gap:7px}.folder-title__actions>span{margin-right:3px;color:var(--lz-text-muted);font-size:13px}.folder-title__actions button{height:36px;display:inline-flex;align-items:center;justify-content:center;gap:6px;border:1px solid var(--lz-border);border-radius:9px;color:var(--lz-text-secondary);background:#fff;font-size:13px;font-weight:700;cursor:pointer}.folder-title__actions button:hover:not(:disabled){border-color:var(--lz-brand-border);color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.folder-title__actions button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:2px}.folder-title__actions button:disabled{opacity:.5;cursor:not-allowed}.batch-import-button{padding:0 12px!important;border-color:var(--lz-brand)!important;color:#fff!important;background:var(--lz-brand)!important}.batch-import-button:hover:not(:disabled){border-color:var(--lz-brand-strong)!important;color:#fff!important;background:var(--lz-brand-strong)!important}.import-folder-button,.add-folder-button{width:36px;padding:0}.add-material-button{padding:0 12px}.file-drop-overlay{position:absolute;inset:66px 12px 14px;z-index:8;display:grid;place-content:center;justify-items:center;gap:10px;border:1px dashed #8f8aef;border-radius:12px;color:var(--lz-brand-strong);background:rgba(247,247,255,.96);pointer-events:none}.file-drop-overlay>span{width:50px;height:50px;display:grid;place-items:center;border-radius:14px;color:var(--lz-brand-strong);background:#fff;box-shadow:0 10px 26px rgba(79,70,229,.12)}.file-drop-overlay strong{font-size:14px}
.file-table{min-height:0;flex:1;overflow:auto;padding:0 12px 20px}.file-table__head,.file-row{display:grid;grid-template-columns:minmax(230px,1.65fr) 126px 88px 76px 98px;align-items:center;gap:10px}.file-table__head{min-height:42px;padding:0 10px;border-bottom:1px solid var(--lz-border);color:var(--lz-text-muted);font-size:12px;font-weight:700}.sort-button{height:40px;display:inline-flex;align-items:center;gap:5px;padding:0;border:0;color:inherit;background:transparent;font:inherit;cursor:pointer}.sort-button svg{opacity:.55}.sort-button:hover,.sort-button.active{color:var(--lz-text-secondary)}.sort-button.active svg{opacity:1}.sort-button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:2px}.file-table__head span:nth-child(4),.file-row>span:nth-child(4){text-align:right}.file-table__head span:nth-child(4) .sort-button{width:100%;justify-content:flex-end}.file-row{width:100%;min-height:58px;padding:7px 10px;border:0;border-bottom:1px solid #edf1f6;background:transparent;color:var(--lz-text-secondary);text-align:left;font-size:13px;cursor:pointer}.file-row:hover,.file-row:focus-visible{outline:0;background:#f7f9fc}.file-row.selected{background:#e9eeff}.file-name{min-width:0;display:flex;align-items:center;gap:10px}.file-name strong{overflow:hidden;color:var(--lz-text-strong);font-size:14px;text-overflow:ellipsis;white-space:nowrap}.file-icon{width:34px;height:34px;flex:none;display:grid;place-items:center;border-radius:8px;background:#f1f5f9;color:#64748b}.file-icon[data-type="outline"],.file-icon[data-type="teaching_calendar"],.file-icon[data-type="lesson_plan"],.file-icon[data-type="ppt"]{background:#eef2ff;color:#4f46e5}.status-dot{width:7px;height:7px;display:inline-block;margin-right:6px;border-radius:50%;background:#94a3b8}.status-dot[data-state="ready"],.status-dot[data-state="uploaded"]{background:#10b981}.status-dot[data-state="working"]{background:#6366f1}.status-dot[data-state="stale"]{background:#f97316}.status-dot[data-state="missing"],.status-dot[data-state="empty"]{background:#cbd5e1}
.file-empty{min-height:260px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;color:var(--lz-text-muted);text-align:center}.file-empty strong{color:var(--lz-text-secondary);font-size:15px}.file-empty span{max-width:320px;font-size:13px;line-height:1.55}.file-empty button{display:flex;align-items:center;gap:6px;padding:8px 12px;border:1px solid var(--lz-border);border-radius:8px;background:#fff;color:#4f46e5;font-size:13px;cursor:pointer}.file-empty button:hover{border-color:var(--lz-brand-border);background:var(--lz-brand-soft)}.runtime-note{margin:0;padding:9px 18px;border-top:1px solid var(--lz-border);color:#9a3412;background:#fff7ed;font-size:13px}
.file-inspector{display:flex;flex-direction:column;border-left:1px solid var(--lz-border);background:#fff}.file-inspector>header{display:grid;grid-template-columns:38px minmax(0,1fr) auto;align-items:center;gap:10px;padding:15px 14px;border-bottom:1px solid var(--lz-border)}.inspector-icon{width:38px;height:38px;display:grid;place-items:center;border-radius:9px;background:#eef2ff;color:#4f46e5}.file-inspector header div{min-width:0;display:grid;gap:2px}.file-inspector header small{color:var(--lz-text-muted);font-size:11px}.file-inspector header strong{overflow:hidden;font-size:15px;text-overflow:ellipsis;white-space:nowrap}.inspector-status{padding:10px 14px;border-bottom:1px solid #edf1f5}.inspector-status>span{display:flex;align-items:center;gap:7px;color:var(--lz-text-secondary);font-size:12px;font-weight:700}.inspector-status i{width:7px;height:7px;border-radius:50%;background:#94a3b8}.inspector-status[data-state="ready"] i,.inspector-status[data-state="uploaded"] i{background:#10b981}.inspector-status[data-state="working"] i{background:#6366f1}.inspector-status[data-state="stale"] i{background:#f97316}.inspector-status[data-state="empty"] i{background:#cbd5e1}.inspector-overview{min-height:0;overflow:auto;padding:4px 14px 18px}.inspector-overview h3{margin:0;color:var(--lz-text-secondary);font-size:12px;font-weight:750}.inspector-overview dl{margin:0}.inspector-overview dl>div{display:grid;grid-template-columns:64px minmax(0,1fr);gap:9px;padding:10px 0;border-bottom:1px solid #edf1f5}.inspector-overview dt{color:var(--lz-text-muted);font-size:12px}.inspector-overview dd{margin:0;overflow-wrap:anywhere;color:var(--lz-text-secondary);font-size:12px;line-height:1.45}.asset-type-select{width:100%;min-height:30px;padding:0 25px 0 8px;border:1px solid #d8deea;border-radius:7px;outline:0;color:#334155;background:#fff;font:inherit;font-size:12px}.asset-type-select:focus{border-color:var(--lz-brand);box-shadow:0 0 0 3px var(--lz-brand-soft)}.asset-type-select:disabled{opacity:.6;cursor:wait}.inspector-actions{display:grid;gap:8px;margin-top:auto;padding:13px 14px;border-top:1px solid var(--lz-border);background:#fff}.inspector-actions__secondary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.inspector-actions__secondary>button:only-child{grid-column:1/-1}.inspector-actions button{min-height:38px;display:flex;align-items:center;justify-content:center;gap:6px;border:1px solid var(--lz-border);border-radius:8px;background:#fff;color:var(--lz-text-secondary);font-size:12px;font-weight:700;cursor:pointer}.inspector-actions button:hover:not(:disabled){border-color:var(--lz-brand-border);color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.inspector-actions button.primary{min-height:40px;border-color:#4f46e5;background:#4f46e5;color:#fff}.inspector-actions button.primary:hover:not(:disabled){border-color:var(--lz-brand-strong);color:#fff;background:var(--lz-brand-strong)}.inspector-actions button.danger{border-color:transparent;color:#b91c1c;background:transparent}.inspector-actions button.danger:hover:not(:disabled){border-color:#fecaca;color:#991b1b;background:#fff1f2}.inspector-actions button:disabled{opacity:.45;cursor:not-allowed}.inspector-actions button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:2px}
.relationship-list{display:grid;gap:0;padding-top:16px}.relationship-list h3{padding-bottom:7px}.relationship-list>div,.relationship-list>button{width:100%;display:grid;grid-template-columns:18px minmax(0,1fr);gap:7px;align-items:start;padding:9px 0;border:0;border-top:1px solid #edf1f5;background:transparent;color:#6366f1;text-align:left}.relationship-list>button{cursor:pointer}.relationship-list>button:hover{color:var(--lz-brand-strong)}.relationship-list>div>span,.relationship-list>button>span{min-width:0;display:grid;gap:2px}.relationship-list strong{overflow:hidden;color:#334155;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.relationship-list small{color:#64748b;font-size:11px}.relationship-empty{padding:7px 0;color:#94a3b8;font-size:12px}
.space-state{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:9px;color:var(--lz-text-muted);text-align:center;font-size:13px}.space-state strong{color:var(--lz-text-secondary);font-size:15px}.space-state span{max-width:240px;font-size:13px;line-height:1.5}.space-state button{padding:8px 13px;border:1px solid var(--lz-border);border-radius:8px;background:#fff;font-size:13px}
.asset-create-overlay{position:fixed;inset:0;z-index:2600;display:grid;place-items:center;padding:14px;background:rgba(15,23,42,.38);backdrop-filter:blur(2px)}.asset-create-dialog{width:min(580px,calc(100vw - 28px));max-height:calc(100vh - 28px);overflow:auto;padding:0 20px 20px;border:1px solid rgba(255,255,255,.65);border-radius:14px;background:#fff;box-shadow:0 24px 70px rgba(15,23,42,.22)}.asset-create-header{position:sticky;top:0;z-index:1;display:flex;align-items:center;justify-content:space-between;min-height:54px;margin:0 -20px 15px;padding:0 20px;border-bottom:1px solid #eef2f7;background:rgba(255,255,255,.96)}.asset-create-header strong{font-size:16px}.asset-create-header button{width:32px;height:32px;display:grid;place-items:center;border:0;border-radius:7px;color:var(--lz-text-muted);background:transparent;cursor:pointer}.asset-create-header button:hover{background:#f1f5f9;color:var(--lz-text-strong)}.asset-create-help{margin:0 0 15px;color:var(--lz-text-secondary);font-size:13px;line-height:1.55}.create-location{min-height:40px;display:grid;grid-template-columns:18px auto minmax(0,1fr);align-items:center;gap:7px;padding:0 11px;border:1px solid #e2e8f0;border-radius:8px;color:#64748b;background:#f8fafc;font-size:12px}.create-location strong{overflow:hidden;color:#334155;font-weight:650;text-overflow:ellipsis;white-space:nowrap}.asset-form{display:grid;gap:14px;padding-top:16px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.form-field{display:grid;gap:7px}.form-field>span,.source-picker>div>span{color:var(--lz-text-secondary);font-size:13px;font-weight:700}.form-field>small{color:var(--lz-text-muted);font-size:12px;line-height:1.5}.form-field input,.form-field select,.form-field textarea{width:100%;min-height:42px;padding:9px 11px;border:1px solid var(--lz-border);border-radius:8px;outline:0;color:var(--lz-text-strong);background:#fff;font:inherit;font-size:13px}.form-field textarea{resize:vertical}.form-field input:focus,.form-field select:focus,.form-field textarea:focus{border-color:#6366f1;box-shadow:0 0 0 3px rgba(99,102,241,.1)}.source-picker{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px;border:1px dashed #cbd5e1;border-radius:9px}.source-picker>div{display:grid;gap:4px}.source-picker small{color:var(--lz-text-muted);font-size:12px}.source-picker button{max-width:220px;display:flex;align-items:center;gap:6px;overflow:hidden;padding:8px 10px;border:1px solid var(--lz-border);border-radius:7px;background:#fff;color:#4f46e5;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.ppt-origin-picker{display:grid;gap:8px}.ppt-origin-picker>span{color:var(--lz-text-secondary);font-size:13px;font-weight:700}.ppt-origin-picker>div{display:grid;grid-template-columns:1fr 1fr;gap:9px}.ppt-origin-picker button{min-width:0;display:grid;grid-template-columns:20px minmax(0,1fr);gap:2px 8px;padding:11px;border:1px solid var(--lz-border);border-radius:9px;color:var(--lz-text-secondary);background:#fff;text-align:left;cursor:pointer}.ppt-origin-picker button svg{grid-row:1/3;align-self:center;color:#64748b}.ppt-origin-picker button strong{font-size:13px}.ppt-origin-picker button small{overflow:hidden;color:var(--lz-text-muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}.ppt-origin-picker button.active{border-color:var(--lz-brand);color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.ppt-origin-picker button.active svg{color:var(--lz-brand)}.ppt-origin-note{display:flex;align-items:flex-start;gap:7px;margin:0;padding:10px 11px;border:1px solid #e0e7ff;border-radius:8px;color:#4f46e5;background:#f8faff;font-size:12px;line-height:1.5}.ppt-origin-note[data-mode="import"]{border-color:#e2e8f0;color:#475569;background:#f8fafc}.dialog-actions{display:flex;justify-content:flex-end;gap:8px;padding-top:5px}.dialog-actions button{min-height:38px;padding:0 14px;border:1px solid var(--lz-border);border-radius:8px;background:#fff;color:var(--lz-text-secondary);font-size:13px;font-weight:700;cursor:pointer}.dialog-actions button.primary{border-color:#4f46e5;background:#4f46e5;color:#fff}.dialog-actions button:disabled{opacity:.45;cursor:not-allowed}.practice-create-note,.create-prerequisite{display:grid;grid-template-columns:20px minmax(0,1fr);align-items:start;gap:9px;padding:12px;border:1px solid #e2e8f0;border-radius:9px;color:#475569;background:#f8fafc}.practice-create-note>div,.create-prerequisite>div{display:grid;gap:4px}.practice-create-note strong,.create-prerequisite strong{font-size:13px}.practice-create-note small,.create-prerequisite small{color:var(--lz-text-muted);font-size:12px;line-height:1.5}.create-prerequisite{grid-template-columns:20px minmax(0,1fr) auto;border-color:#fed7aa;color:#9a3412;background:#fff7ed}.create-prerequisite button{align-self:center;padding:7px 9px;border:1px solid #fdba74;border-radius:7px;color:#9a3412;background:#fff;font-size:12px;font-weight:700;cursor:pointer}
.source-picker>span{color:var(--lz-text-secondary);font-size:13px;font-weight:700}.ppt-origin-picker button{align-items:center;gap:8px}.ppt-origin-picker button svg{grid-row:auto}.practice-create-note,.create-prerequisite{align-items:center}
.file-context-menu{position:fixed;z-index:3200;width:188px;display:grid;padding:6px;border:1px solid #dfe4ec;border-radius:10px;background:#fff;box-shadow:0 18px 46px rgba(15,23,42,.2);outline:0}.file-context-menu button{min-height:36px;display:flex;align-items:center;gap:9px;padding:0 9px;border:0;border-radius:7px;color:#334155;background:transparent;font:inherit;font-size:12px;font-weight:650;text-align:left;cursor:pointer}.file-context-menu button:hover,.file-context-menu button:focus-visible{outline:0;color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.file-context-menu>span{height:1px;margin:5px 4px;background:#edf1f5}.file-context-menu button.danger{color:#b91c1c}.file-context-menu button.danger:hover,.file-context-menu button.danger:focus-visible{color:#991b1b;background:#fff1f2}.preview-surface{min-height:420px;display:grid;place-items:center}.preview-surface img{max-width:100%;max-height:75vh}.preview-surface iframe{width:100%;min-height:72vh;border:0}.office-note{display:flex;flex-direction:column;align-items:center;gap:8px;color:var(--lz-text-muted);text-align:center;font-size:13px}.office-note strong{color:var(--lz-text-strong);font-size:15px}.office-note button{padding:8px 11px;border:1px solid var(--lz-border);border-radius:7px;background:#fff;font-size:13px}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media (max-width:1080px){.file-layout{grid-template-columns:220px minmax(440px,1fr) 270px}.list-search{display:none}.file-table__head,.file-row{grid-template-columns:minmax(190px,1.5fr) 104px 78px 90px}.file-table__head span:nth-child(4),.file-row>span:nth-child(4){display:none}}
@media (max-width:760px){.workspace-view-switch button{padding:0 8px}.file-layout{grid-template-columns:1fr;grid-template-rows:170px minmax(0,1fr) auto}.file-tree-pane{display:grid;grid-template-rows:46px minmax(0,1fr);overflow:hidden;border-right:0;border-bottom:1px solid var(--lz-border)}.pane-heading{min-height:46px;padding:0 11px}.folder-navigation{overflow:auto;padding:6px 8px 11px}.file-tree-pane footer{display:none}.file-inspector{max-height:56vh;border-left:0;border-top:1px solid var(--lz-border)}.inspector-actions{padding:13px 14px}.list-toolbar{min-height:50px;padding:0 11px}.list-toolbar nav button{max-width:110px}.folder-title{min-height:58px;padding:8px 12px}.folder-title h2{font-size:17px}.folder-title__actions>span{display:none}.add-material-button{padding:0 10px}.file-table{padding:0 7px 12px}.file-table__head,.file-row{grid-template-columns:minmax(180px,1fr) 94px}.file-table__head span:nth-child(2),.file-row>span:nth-child(2),.file-table__head span:nth-child(3),.file-row>span:nth-child(3),.file-table__head span:nth-child(4),.file-row>span:nth-child(4){display:none}.category-layout{grid-template-columns:minmax(0,1fr);grid-template-rows:minmax(160px,32vh) minmax(0,1fr)}.category-navigation{padding:11px 10px;border-right:0;border-bottom:1px solid var(--lz-border)}.category-navigation>header{display:none}.category-group__button{min-height:50px}.category-detail-header{min-height:72px;align-items:flex-start;gap:10px;padding:10px 12px}.category-detail-header>div:first-child{gap:3px 8px}.category-detail-header h2{font-size:17px}.category-detail-actions{gap:5px}.category-detail-actions button{min-height:34px;padding:0 9px}.category-document-scroll{padding:12px 10px 28px}.category-document{min-height:100%;padding:20px 18px 34px;border-radius:9px}.form-grid{grid-template-columns:1fr}}
.category-layout{grid-template-columns:312px minmax(0,1fr);background:#f3f5f9}
.category-navigation{margin:14px 0 14px 14px;padding:20px 14px;border:1px solid #e6eaf1;border-radius:22px;background:#fff;box-shadow:0 12px 34px rgba(15,23,42,.045)}
.category-navigation>header{padding:0 8px 14px}.category-navigation>header strong{font-size:15px}
.category-progress{display:grid;gap:8px;margin:0 4px 14px;padding:12px 13px;border:1px solid #e4e8f1;border-radius:10px;background:rgba(255,255,255,.84)}
.category-progress>div{display:flex;align-items:center;justify-content:space-between;gap:12px;color:var(--lz-text-muted);font-size:12px}.category-progress>div strong{color:var(--lz-brand-strong);font-size:13px;font-variant-numeric:tabular-nums}
.category-progress__track{height:5px;overflow:hidden;border-radius:999px;background:#e7eaf2}.category-progress__track i{display:block;width:100%;height:100%;transform-origin:left;border-radius:inherit;background:var(--lz-brand);transition:transform .24s ease}
.category-navigation nav{gap:7px}.category-group__button{min-height:62px;grid-template-columns:27px 18px minmax(0,1fr) auto;gap:9px;padding:9px 11px;border-radius:14px}.category-group__button>svg{color:#8b98ab}.category-group__button.active>svg{color:var(--lz-brand)}
.category-group__step{width:27px;height:27px;display:grid;place-items:center;border:1px solid #dbe2ec;border-radius:7px;color:#7b8798;background:rgba(255,255,255,.72);font-size:10px;font-weight:800;font-variant-numeric:tabular-nums}.category-group__button.active .category-group__step{border-color:rgba(99,102,241,.24);color:var(--lz-brand-strong);background:#fff}
.category-group__copy{min-width:0;display:grid;gap:3px}.category-group__copy strong,.category-group__copy small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.category-group__copy strong{color:var(--lz-text-secondary);font-size:13px}.category-group__copy small{color:var(--lz-text-muted);font-size:11px}.category-group__button.active .category-group__copy strong{color:var(--lz-brand-strong)}
.category-group__trailing b{min-width:max-content;padding:3px 6px;border-radius:999px;background:#eef2f7;text-align:center}.category-group__trailing b[data-state="ready"]{background:#ecfdf5}.category-group__trailing b[data-state="working"]{background:#eef2ff}.category-group__trailing b[data-state="attention"]{background:#fff7ed}
.category-detail-pane{grid-template-rows:auto auto minmax(0,1fr);margin:14px;border:1px solid #e5e9f0;border-radius:24px;background:#fff;box-shadow:0 16px 44px rgba(15,23,42,.055)}
.category-detail-header{min-height:92px;padding:16px 26px;border-bottom-color:#edf0f5}.category-detail-header h2{font-size:21px;letter-spacing:-.016em}.category-detail-actions button{min-height:40px;padding:0 15px;border-radius:12px}
.workbench-brief-bar{min-height:104px;display:grid;grid-template-columns:minmax(145px,.58fr) minmax(420px,2fr) auto;align-items:center;gap:18px;padding:14px 24px;border-bottom:1px solid #edf0f5;background:#fbfcff}
.workbench-brief-bar__title{min-width:0;display:flex;align-items:center;gap:11px}.workbench-brief-bar__title>span{width:38px;height:38px;display:grid;place-items:center;flex:none;border-radius:12px;color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.workbench-brief-bar__title>div{min-width:0;display:grid}.workbench-brief-bar__title strong{font-size:14px}
.workbench-brief-items{min-width:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.workbench-brief-items button{min-width:0;display:grid;gap:3px;padding:8px 10px;border:1px solid #e8ebf2;border-radius:12px;color:inherit;background:#fff;text-align:left;cursor:pointer}.workbench-brief-items button:hover{border-color:var(--lz-brand-border);background:var(--lz-brand-soft)}.workbench-brief-items button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:2px}.workbench-brief-items span{color:var(--lz-text-muted);font-size:12px}.workbench-brief-items strong{overflow:hidden;color:var(--lz-text-secondary);font-size:12px;font-weight:750;text-overflow:ellipsis;white-space:nowrap}.workbench-brief-items strong[data-empty="true"]{color:#a1a9b6;font-weight:600}
.workbench-brief-actions{display:flex;align-items:center;gap:7px}.workbench-edit-baseline{display:none}
.workbench-settings-button{min-height:40px;display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:0 13px;border:1px solid var(--lz-brand-border);border-radius:12px;color:var(--lz-brand-strong);background:#fff;font-size:12px;font-weight:750;white-space:nowrap;cursor:pointer}.workbench-settings-button:hover{background:var(--lz-brand-soft)}.workbench-settings-button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:2px}
.category-document-scroll{padding:24px 28px 42px;background:#f8f9fc}.category-document{width:min(980px,100%);padding:38px 46px 56px;border-color:#e6eaf1;border-radius:22px;box-shadow:0 14px 34px rgba(15,23,42,.045)}
.category-console{min-height:0;overflow:auto;display:grid;place-items:center;padding:32px;background:#f8f9fc}
.category-console__card{width:min(660px,100%);display:grid;justify-items:center;padding:42px 44px 44px;border:1px solid #e4e8ef;border-radius:24px;background:#fff;box-shadow:0 18px 46px rgba(15,23,42,.06);text-align:center}.category-console__card>header{width:100%;display:flex;align-items:center;justify-content:center}.category-console__icon{width:54px;height:54px;display:grid;place-items:center;border-radius:17px;color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.category-console__card h3{margin:26px 0 0;color:var(--lz-text-strong);font-size:23px;letter-spacing:-.018em}
.category-prerequisite{width:100%;display:grid;grid-template-columns:22px minmax(0,1fr);align-items:center;gap:9px;margin-top:22px;padding:12px 14px;border:1px solid #e4e8f1;border-radius:10px;color:#64748b;background:#f8fafc;text-align:left}.category-prerequisite>svg{color:var(--lz-brand)}.category-prerequisite>div{display:grid;gap:2px}.category-prerequisite small{font-size:10px}.category-prerequisite strong{color:#475569;font-size:12px}
.category-group__trailing b,
.category-child__index,
.category-group__step,
.category-group__copy small,
.workbench-brief-bar__title small,
.workbench-brief-items span,
.category-prerequisite small { font-size:12px; }
.category-console__actions{display:flex;align-items:center;justify-content:center;gap:10px;margin-top:28px}.category-console__actions button{min-height:44px;display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:0 18px;border:1px solid var(--lz-border);border-radius:13px;color:var(--lz-text-secondary);background:#fff;font-size:13px;font-weight:750;cursor:pointer}.category-console__actions button.primary{border-color:var(--lz-brand);color:#fff;background:var(--lz-brand);box-shadow:0 9px 20px rgba(99,102,241,.17)}.category-console__actions button:hover:not(:disabled){border-color:var(--lz-brand-border);color:var(--lz-brand-strong);background:var(--lz-brand-soft)}.category-console__actions button.primary:hover:not(:disabled){border-color:var(--lz-brand-strong);color:#fff;background:var(--lz-brand-strong)}.category-console__actions button:disabled{opacity:.45;cursor:not-allowed}.category-console__actions button:focus-visible{outline:2px solid var(--lz-brand);outline-offset:2px}
.file-name__copy{min-width:0;display:grid;gap:2px}.file-name__copy strong,.file-name__copy small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.file-name__copy small{color:#64748b;font-size:11px}.file-icon[data-type="outline_export"],.file-icon[data-type="companion_document"]{background:#eef2ff;color:#4f46e5}
@media (max-width:1180px){.category-layout{grid-template-columns:280px minmax(0,1fr)}.workbench-brief-bar{grid-template-columns:minmax(130px,.55fr) minmax(300px,1.7fr) auto;gap:12px;padding-inline:16px}.workbench-brief-items{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media (max-width:760px){.category-layout{grid-template-columns:minmax(0,1fr);grid-template-rows:minmax(210px,37vh) minmax(0,1fr)}.category-navigation{padding:10px;border-right:0;border-bottom:1px solid var(--lz-border)}.category-navigation>header{display:none}.category-progress{margin:0 2px 8px;padding:8px 10px}.category-group__button{min-height:54px;grid-template-columns:24px 16px minmax(0,1fr) auto;padding:7px 8px}.category-group__step{width:24px;height:24px}.category-group__copy small{display:none}.category-children{margin-bottom:5px}.category-detail-header{min-height:66px}.workbench-brief-bar{min-height:60px;grid-template-columns:minmax(0,1fr) auto;padding:8px 12px}.workbench-brief-bar__title small,.workbench-brief-items{display:none}.workbench-edit-baseline{min-height:38px;display:inline-flex;align-items:center;justify-content:center;gap:5px;padding:0 10px;border:1px solid var(--lz-border);border-radius:11px;color:var(--lz-text-secondary);background:#fff;font-size:12px;font-weight:750;white-space:nowrap;cursor:pointer}.category-console{padding:14px 10px 26px}.category-console__card{padding:22px 18px 24px;border-radius:12px}.category-console__card h3{margin-top:18px;font-size:19px}.category-console__actions{width:100%;display:grid;grid-template-columns:1fr;margin-top:20px}.category-console__actions button{width:100%}}
@media (max-width:760px){.category-layout{grid-template-rows:minmax(210px,34vh) minmax(0,1fr)}.category-navigation{margin:8px 8px 0;padding:9px;border:1px solid #e6eaf1;border-radius:18px}.category-detail-pane{margin:8px;border-radius:18px}.category-detail-header{padding:11px 14px}.category-document-scroll{padding:10px 8px 24px}.category-document{padding:22px 18px 34px;border-radius:16px}.category-console{padding:12px 8px 22px}.category-console__card{padding:26px 20px 28px;border-radius:18px}.category-console__icon{width:48px;height:48px;border-radius:15px}.workbench-settings-button{min-height:38px;border-radius:11px}}
@media (max-width:760px){.file-layout{grid-template-rows:170px minmax(280px,45vh) auto;align-content:start;overflow-y:auto}.file-inspector{max-height:none;display:block;overflow:visible}.inspector-overview{min-height:auto;overflow:visible}.inspector-actions{margin-top:0}}
</style>
