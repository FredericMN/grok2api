(() => {
  /* === DOM References === */
  const startBtn = document.getElementById('startBtn');
  const stopBtn = document.getElementById('stopBtn');
  const clearBtn = document.getElementById('clearBtn');
  const promptInput = document.getElementById('promptInput');
  const sizeSelect = document.getElementById('sizeSelect');
  const nSelect = document.getElementById('nSelect');
  const statusText = document.getElementById('statusText');
  const progressBar = document.getElementById('progressBar');
  const progressFill = document.getElementById('progressFill');
  const progressText = document.getElementById('progressText');
  const durationValue = document.getElementById('durationValue');
  const sizeValue = document.getElementById('sizeValue');
  const nValue = document.getElementById('nValue');
  const refValue = document.getElementById('refValue');
  const taskCountValue = document.getElementById('taskCountValue');
  const galleryEmpty = document.getElementById('galleryEmpty');
  const galleryStage = document.getElementById('galleryStage');
  const uploadArea = document.getElementById('uploadArea');
  const uploadPlaceholder = document.getElementById('uploadPlaceholder');
  const thumbnailList = document.getElementById('thumbnailList');
  const imageFileInput = document.getElementById('imageFileInput');
  const imageCount = document.getElementById('imageCount');
  const clearImagesBtn = document.getElementById('clearImagesBtn');

  /* === Constants === */
  const MAX_IMAGES = 3;
  const MAX_IMAGE_SIZE = 50 * 1024 * 1024;
  const ALLOWED_TYPES = ['image/png', 'image/jpeg', 'image/webp'];

  /* === State === */
  const taskRegistry = new Map();
  let previewCount = 0;
  let imageDataUrls = []; // Array of { dataUrl, name }

  /* === TaskContext === */
  class TaskContext {
    constructor(taskId, expectedN) {
      this.taskId = taskId;
      this.expectedN = expectedN || 1;
      this.source = null;
      this.previewItems = new Map(); // index -> gallery-item DOM
      this.startAt = Date.now();
      this.elapsedTimer = null;
      this.lastProgress = 0;
      this.isRunning = true;
      this.completedCount = 0;
    }

    close() {
      this.isRunning = false;
      if (this.source) {
        try { this.source.close(); } catch (e) { /* ignore */ }
        this.source = null;
      }
      this.stopElapsedTimer();
      taskRegistry.delete(this.taskId);
      updateTaskCount();
    }

    startElapsedTimer() {
      this.stopElapsedTimer();
      const self = this;
      this.elapsedTimer = setInterval(() => {
        if (!self.startAt || !self.isRunning) return;
        // Update duration on the first preview item
        const firstItem = self.previewItems.values().next().value;
        const durationEl = firstItem?.querySelector('.gallery-item-duration');
        if (durationEl) {
          const seconds = Math.max(0, Math.round((Date.now() - self.startAt) / 1000));
          durationEl.textContent = `${seconds}s`;
        }
      }, 1000);
    }

    stopElapsedTimer() {
      if (this.elapsedTimer) {
        clearInterval(this.elapsedTimer);
        this.elapsedTimer = null;
      }
    }
  }

  /* === Utilities === */
  function toast(message, type) {
    if (typeof showToast === 'function') showToast(message, type);
  }

  function setStatus(state, text) {
    if (!statusText) return;
    statusText.textContent = text;
    statusText.classList.remove('connected', 'connecting', 'error');
    if (state) statusText.classList.add(state);
  }

  function setButtons() {
    if (stopBtn) stopBtn.classList.toggle('hidden', taskRegistry.size === 0);
  }

  function updateProgress(value) {
    const safe = Math.max(0, Math.min(100, Number(value) || 0));
    if (progressFill) progressFill.style.width = `${safe}%`;
    if (progressText) progressText.textContent = `${safe}%`;
  }

  function setIndeterminate(active) {
    if (!progressBar) return;
    progressBar.classList.toggle('indeterminate', active);
  }

  function updateTaskCount() {
    if (taskCountValue) taskCountValue.textContent = String(taskRegistry.size);
  }

  function updateMeta() {
    if (sizeValue && sizeSelect) sizeValue.textContent = sizeSelect.value;
    if (nValue && nSelect) nValue.textContent = nSelect.value + ' 张';
    if (refValue) refValue.textContent = imageDataUrls.length + ' 张';
  }

  function normalizeAuthHeader(authHeader) {
    if (!authHeader) return '';
    return authHeader.startsWith('Bearer ') ? authHeader.slice(7).trim() : authHeader;
  }

  /* === Image Upload Management === */
  let pendingReads = 0;

  function addImages(files) {
    const remaining = MAX_IMAGES - imageDataUrls.length - pendingReads;
    const toProcess = Array.from(files).slice(0, Math.max(0, remaining));

    if (toProcess.length < files.length) {
      toast(`最多上传 ${MAX_IMAGES} 张图片`, 'error');
    }

    for (const file of toProcess) {
      if (!ALLOWED_TYPES.includes(file.type)) {
        toast(`不支持的格式: ${file.name}`, 'error');
        continue;
      }
      if (file.size > MAX_IMAGE_SIZE) {
        toast(`图片太大: ${file.name}（最大 50MB）`, 'error');
        continue;
      }
      pendingReads++;
      const reader = new FileReader();
      reader.onload = () => {
        pendingReads--;
        if (typeof reader.result === 'string' && imageDataUrls.length < MAX_IMAGES) {
          imageDataUrls.push({ dataUrl: reader.result, name: file.name });
          renderThumbnails();
          updateMeta();
        }
      };
      reader.onerror = () => {
        pendingReads--;
        toast('文件读取失败', 'error');
      };
      reader.readAsDataURL(file);
    }
  }

  function removeImage(index) {
    imageDataUrls.splice(index, 1);
    renderThumbnails();
    updateMeta();
  }

  function clearAllImages() {
    imageDataUrls = [];
    if (imageFileInput) imageFileInput.value = '';
    renderThumbnails();
    updateMeta();
  }

  function renderThumbnails() {
    if (!thumbnailList) return;
    thumbnailList.innerHTML = '';

    imageDataUrls.forEach((img, i) => {
      const item = document.createElement('div');
      item.className = 'thumbnail-item';

      const imgEl = document.createElement('img');
      imgEl.src = img.dataUrl;
      imgEl.alt = img.name;

      const removeBtn = document.createElement('button');
      removeBtn.className = 'thumbnail-remove';
      removeBtn.textContent = '\u00d7';
      removeBtn.type = 'button';
      removeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        removeImage(i);
      });

      item.appendChild(imgEl);
      item.appendChild(removeBtn);
      thumbnailList.appendChild(item);
    });

    // "Add more" button if under limit
    if (imageDataUrls.length > 0 && imageDataUrls.length < MAX_IMAGES) {
      const addBtn = document.createElement('div');
      addBtn.className = 'thumbnail-add';
      addBtn.textContent = '+';
      addBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (imageFileInput) imageFileInput.click();
      });
      thumbnailList.appendChild(addBtn);
    }

    const hasImages = imageDataUrls.length > 0;
    if (uploadPlaceholder) uploadPlaceholder.classList.toggle('hidden', hasImages);
    if (uploadArea) uploadArea.classList.toggle('has-images', hasImages);
    if (imageCount) imageCount.textContent = `已选 ${imageDataUrls.length}/${MAX_IMAGES} 张`;
  }

  /* === Upload Area Events === */
  if (uploadArea) {
    uploadArea.addEventListener('dragover', (e) => {
      e.preventDefault();
      uploadArea.classList.add('drag-over');
    });
    uploadArea.addEventListener('dragleave', () => {
      uploadArea.classList.remove('drag-over');
    });
    uploadArea.addEventListener('drop', (e) => {
      e.preventDefault();
      uploadArea.classList.remove('drag-over');
      if (e.dataTransfer && e.dataTransfer.files.length) {
        addImages(Array.from(e.dataTransfer.files));
      }
    });
    uploadArea.addEventListener('click', (e) => {
      // Only trigger file picker if clicking on placeholder area (not thumbnails)
      if (e.target === uploadArea || e.target === uploadPlaceholder || uploadPlaceholder?.contains(e.target)) {
        if (imageDataUrls.length < MAX_IMAGES && imageFileInput) {
          imageFileInput.click();
        }
      }
    });
  }

  if (imageFileInput) {
    imageFileInput.addEventListener('change', () => {
      if (imageFileInput.files && imageFileInput.files.length) {
        addImages(Array.from(imageFileInput.files));
      }
      imageFileInput.value = '';
    });
  }

  if (clearImagesBtn) {
    clearImagesBtn.addEventListener('click', clearAllImages);
  }

  /* === SSE URL Builder === */
  function buildSseUrl(taskId, rawPublicKey) {
    const proto = window.location.protocol === 'https:' ? 'https' : 'http';
    const base = `${proto}://${window.location.host}/v1/public/image-edit/sse`;
    const params = new URLSearchParams();
    params.set('task_id', taskId);
    params.set('t', String(Date.now()));
    if (rawPublicKey) params.set('public_key', rawPublicKey);
    return `${base}?${params.toString()}`;
  }

  /* === API Functions === */
  async function createEditTask(authHeader, params) {
    const res = await fetch('/v1/public/image-edit/start', {
      method: 'POST',
      headers: {
        ...buildAuthHeaders(authHeader),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(params),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || 'Failed to create task');
    }
    const data = await res.json();
    return data && data.task_id ? String(data.task_id) : '';
  }

  async function stopEditTask(taskId, authHeader) {
    if (!taskId) return;
    try {
      await fetch('/v1/public/image-edit/stop', {
        method: 'POST',
        headers: {
          ...buildAuthHeaders(authHeader),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ task_ids: [taskId] }),
      });
    } catch (e) {
      /* ignore */
    }
  }

  /* === Gallery Preview Slot === */
  function initPreviewSlots(ctx) {
    if (!galleryStage) return;
    for (let i = 0; i < ctx.expectedN; i++) {
      previewCount += 1;
      const item = document.createElement('div');
      item.className = 'gallery-item is-pending';
      item.dataset.index = String(previewCount);
      item.dataset.taskId = ctx.taskId;
      item.dataset.slotIndex = String(i);

      const header = document.createElement('div');
      header.className = 'gallery-item-bar';

      const title = document.createElement('div');
      title.className = 'gallery-item-title';
      title.textContent = `图片 ${previewCount}`;

      const durationEl = document.createElement('div');
      durationEl.className = 'gallery-item-duration';
      durationEl.textContent = '-';

      const actions = document.createElement('div');
      actions.className = 'gallery-item-actions';

      const downloadBtn = document.createElement('button');
      downloadBtn.className = 'geist-button-outline text-xs px-3 gallery-download';
      downloadBtn.type = 'button';
      downloadBtn.textContent = '下载';
      downloadBtn.disabled = true;

      actions.appendChild(downloadBtn);
      header.appendChild(title);
      header.appendChild(durationEl);
      header.appendChild(actions);

      const body = document.createElement('div');
      body.className = 'gallery-item-body';
      body.innerHTML = '<div class="gallery-item-placeholder">编辑中\u2026</div>';

      item.appendChild(header);
      item.appendChild(body);
      galleryStage.appendChild(item);

      ctx.previewItems.set(i, item);
    }
    galleryStage.classList.remove('hidden');
    if (galleryEmpty) galleryEmpty.classList.add('hidden');
  }

  /* === Image Rendering === */
  function renderImage(ctx, imgData, index) {
    const item = ctx.previewItems.get(index) || ctx.previewItems.get(0);
    if (!item) return;
    const body = item.querySelector('.gallery-item-body');
    if (!body) return;

    body.innerHTML = '';
    const imgEl = document.createElement('img');

    if (imgData.startsWith('data:') || imgData.startsWith('http')) {
      imgEl.src = imgData;
    } else {
      imgEl.src = `data:image/png;base64,${imgData}`;
    }

    body.appendChild(imgEl);
    item.classList.remove('is-pending');
    ctx.completedCount++;
    updateProgress(100);
    setIndeterminate(false);

    // Enable download
    const downloadBtn = item.querySelector('.gallery-download');
    if (downloadBtn) {
      downloadBtn.disabled = false;
      downloadBtn.dataset.src = imgEl.src;
    }
  }

  /* === SSE Event Handling === */
  function handleSSEEvent(ctx, event, eventType) {
    if (!ctx.isRunning) return;

    const data = event.data;
    if (data === '[DONE]') {
      finishTask(ctx, false);
      return;
    }

    let payload;
    try {
      payload = JSON.parse(data);
    } catch (e) {
      return;
    }

    if (payload.error) {
      toast(payload.error, 'error');
      finishTask(ctx, true);
      return;
    }

    const type = payload.type || eventType;

    if (type === 'image_generation.partial_image') {
      const progress = payload.progress || 0;
      ctx.lastProgress = progress;
      updateProgress(progress);
      setIndeterminate(false);
      return;
    }

    if (type === 'image_generation.completed') {
      const imgData = payload.url || payload.b64_json || payload.base64 || '';
      const index = payload.index || 0;
      if (imgData) {
        renderImage(ctx, imgData, index);
      }
      return;
    }
  }

  function finishTask(ctx, hasError) {
    ctx.stopElapsedTimer();
    for (const [, item] of ctx.previewItems) {
      const placeholder = item.querySelector('.gallery-item-placeholder');
      if (placeholder) {
        if (hasError) {
          placeholder.textContent = '编辑失败';
          item.classList.add('is-failed');
        } else if (ctx.completedCount === 0) {
          placeholder.textContent = '编辑失败（无图片返回）';
          item.classList.add('is-failed');
        } else {
          placeholder.remove();
        }
      }
    }
    // Close first, then check remaining tasks
    ctx.close();
    if (taskRegistry.size === 0) {
      setStatus('', '已完成');
    }
    setButtons();
    updateTaskCount();
  }

  /* === Main Connection Flow === */
  async function startConnection() {
    const prompt = promptInput ? promptInput.value.trim() : '';
    if (!prompt) {
      toast('请输入提示词', 'error');
      return;
    }
    if (imageDataUrls.length === 0) {
      toast('请至少上传 1 张图片', 'error');
      return;
    }

    const authHeader = await ensurePublicKey();
    if (authHeader === null) {
      toast('请先配置 Public Key', 'error');
      window.location.href = '/login';
      return;
    }

    updateMeta();

    const requestParams = {
      prompt,
      images: imageDataUrls.map((img) => img.dataUrl),
      size: sizeSelect ? sizeSelect.value : '1024x1024',
      n: nSelect ? parseInt(nSelect.value, 10) : 1,
    };

    let taskId = '';
    try {
      taskId = await createEditTask(authHeader, requestParams);
    } catch (e) {
      toast('创建任务失败: ' + e.message, 'error');
      return;
    }

    const expectedN = requestParams.n;
    const ctx = new TaskContext(taskId, expectedN);
    taskRegistry.set(taskId, ctx);
    initPreviewSlots(ctx);
    ctx.startElapsedTimer();
    updateTaskCount();

    setStatus('connected', '编辑中');
    setButtons();
    setIndeterminate(true);

    const rawPublicKey = normalizeAuthHeader(authHeader);
    const url = buildSseUrl(taskId, rawPublicKey);
    const es = new EventSource(url);
    ctx.source = es;

    // Named SSE events from ImageStreamProcessor
    es.addEventListener('image_generation.partial_image', (e) => {
      handleSSEEvent(ctx, e, 'image_generation.partial_image');
    });
    es.addEventListener('image_generation.completed', (e) => {
      handleSSEEvent(ctx, e, 'image_generation.completed');
    });

    // Fallback for unnamed events: [DONE] and error payloads
    es.onmessage = (e) => {
      handleSSEEvent(ctx, e, '');
    };

    es.onerror = () => {
      if (!ctx.isRunning) return;
      toast('连接错误', 'error');
      finishTask(ctx, true);
      ctx.close();
    };
  }

  async function stopAllConnections() {
    const authHeader = await ensurePublicKey();
    const contexts = [...taskRegistry.values()];
    await Promise.all(
      contexts.map(async (ctx) => {
        if (authHeader !== null) await stopEditTask(ctx.taskId, authHeader);
        ctx.close();
      })
    );
    setStatus('', '未连接');
    setButtons();
    updateTaskCount();
  }

  function resetOutput(keepPreview) {
    if (!keepPreview) {
      if (galleryStage) {
        galleryStage.innerHTML = '';
        galleryStage.classList.add('hidden');
      }
      if (galleryEmpty) galleryEmpty.classList.remove('hidden');
      previewCount = 0;
      const contexts = [...taskRegistry.values()];
      for (const ctx of contexts) ctx.close();
    }
    updateProgress(0);
    setIndeterminate(false);
    if (durationValue) durationValue.textContent = '耗时 -';
    setStatus('', '未连接');
    setButtons();
    updateTaskCount();
  }

  /* === Download Handler (delegated) === */
  if (galleryStage) {
    galleryStage.addEventListener('click', async (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement) || !target.classList.contains('gallery-download')) return;
      event.preventDefault();

      const src = target.dataset.src;
      if (!src) return;

      const item = target.closest('.gallery-item');
      const index = item ? item.dataset.index : '';

      try {
        let blobUrl;
        if (src.startsWith('data:')) {
          // Base64 data URI → blob
          const res = await fetch(src);
          const blob = await res.blob();
          blobUrl = URL.createObjectURL(blob);
        } else {
          // URL download
          const res = await fetch(src, { mode: 'cors' });
          if (!res.ok) throw new Error('download_failed');
          const blob = await res.blob();
          blobUrl = URL.createObjectURL(blob);
        }

        const anchor = document.createElement('a');
        anchor.href = blobUrl;
        anchor.download = index ? `grok_edit_${index}.png` : 'grok_edit.png';
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(blobUrl);
      } catch (e) {
        toast('下载失败，请尝试右键另存为', 'error');
      }
    });
  }

  /* === Event Listeners === */
  if (startBtn) startBtn.addEventListener('click', () => startConnection());
  if (stopBtn) stopBtn.addEventListener('click', () => stopAllConnections());
  if (clearBtn) clearBtn.addEventListener('click', () => resetOutput());

  if (promptInput) {
    promptInput.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        startConnection();
      }
    });
  }

  updateMeta();
})();
