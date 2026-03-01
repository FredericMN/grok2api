(() => {
  const startBtn = document.getElementById('startBtn');
  const stopBtn = document.getElementById('stopBtn');
  const clearBtn = document.getElementById('clearBtn');
  const promptInput = document.getElementById('promptInput');
  const imageUrlInput = document.getElementById('imageUrlInput');
  const imageFileInput = document.getElementById('imageFileInput');
  const imageFileName = document.getElementById('imageFileName');
  const clearImageFileBtn = document.getElementById('clearImageFileBtn');
  const selectImageFileBtn = document.getElementById('selectImageFileBtn');
  const ratioSelect = document.getElementById('ratioSelect');
  const lengthSelect = document.getElementById('lengthSelect');
  const resolutionSelect = document.getElementById('resolutionSelect');
  const presetSelect = document.getElementById('presetSelect');
  const statusText = document.getElementById('statusText');
  const progressBar = document.getElementById('progressBar');
  const progressFill = document.getElementById('progressFill');
  const progressText = document.getElementById('progressText');
  const durationValue = document.getElementById('durationValue');
  const aspectValue = document.getElementById('aspectValue');
  const lengthValue = document.getElementById('lengthValue');
  const resolutionValue = document.getElementById('resolutionValue');
  const presetValue = document.getElementById('presetValue');
  const videoEmpty = document.getElementById('videoEmpty');
  const videoStage = document.getElementById('videoStage');

  const DEFAULT_REASONING_EFFORT = 'low';

  // 全局任务注册表：taskId -> TaskContext
  const taskRegistry = new Map();
  let previewCount = 0;
  let fileDataUrl = '';

  // 任务上下文类：每个视频任务独立的状态
  class TaskContext {
    constructor(taskId) {
      this.taskId = taskId;
      this.source = null;
      this.previewItem = null;
      this.progressBuffer = '';
      this.contentBuffer = '';
      this.collectingContent = false;
      this.startAt = Date.now();
      this.elapsedTimer = null;
      this.lastProgress = 0;
      this.isRunning = true;
    }

    close() {
      this.isRunning = false;
      if (this.source) {
        try {
          this.source.close();
        } catch (e) {
          // ignore
        }
        this.source = null;
      }
      this.stopElapsedTimer();
      taskRegistry.delete(this.taskId);
    }

    startElapsedTimer() {
      this.stopElapsedTimer();
      const self = this;
      this.elapsedTimer = setInterval(() => {
        if (!self.startAt || !self.isRunning) return;
        // 更新对应 preview item 的耗时显示
        const durationEl = self.previewItem?.querySelector('.video-item-duration');
        if (durationEl) {
          const seconds = Math.max(0, Math.round((Date.now() - self.startAt) / 1000));
          durationEl.textContent = `耗时 ${seconds}s`;
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

  function toast(message, type) {
    if (typeof showToast === 'function') {
      showToast(message, type);
    }
  }

  function setStatus(state, text) {
    if (!statusText) return;
    statusText.textContent = text;
    statusText.classList.remove('connected', 'connecting', 'error');
    if (state) {
      statusText.classList.add(state);
    }
  }

  function setButtons(running) {
    // 并发模式：只要有任务在运行就显示停止按钮
    if (!stopBtn) return;
    const hasRunning = taskRegistry.size > 0;
    if (hasRunning) {
      stopBtn.classList.remove('hidden');
    } else {
      stopBtn.classList.add('hidden');
    }
  }

  function updateProgress(value) {
    const safe = Math.max(0, Math.min(100, Number(value) || 0));
    if (progressFill) {
      progressFill.style.width = `${safe}%`;
    }
    if (progressText) {
      progressText.textContent = `${safe}%`;
    }
  }

  function updateMeta() {
    if (aspectValue && ratioSelect) {
      aspectValue.textContent = ratioSelect.value;
    }
    if (lengthValue && lengthSelect) {
      lengthValue.textContent = `${lengthSelect.value}s`;
    }
    if (resolutionValue && resolutionSelect) {
      resolutionValue.textContent = resolutionSelect.value;
    }
    if (presetValue && presetSelect) {
      presetValue.textContent = presetSelect.value;
    }
  }

  function resetOutput(keepPreview) {
    if (!keepPreview) {
      if (videoStage) {
        videoStage.innerHTML = '';
        videoStage.classList.add('hidden');
      }
      if (videoEmpty) {
        videoEmpty.classList.remove('hidden');
      }
      previewCount = 0;
      // 关闭所有任务
      for (const ctx of taskRegistry.values()) {
        ctx.close();
      }
      taskRegistry.clear();
    }
    updateProgress(0);
    setIndeterminate(false);
    if (durationValue) {
      durationValue.textContent = '耗时 -';
    }
    setButtons(false);
  }

  function initPreviewSlot(ctx) {
    if (!videoStage) return null;
    previewCount += 1;
    
    const item = document.createElement('div');
    item.className = 'video-item is-pending';
    item.dataset.index = String(previewCount);
    item.dataset.taskId = ctx.taskId;

    const header = document.createElement('div');
    header.className = 'video-item-bar';

    const title = document.createElement('div');
    title.className = 'video-item-title';
    title.textContent = `视频 ${previewCount}`;

    const durationEl = document.createElement('div');
    durationEl.className = 'video-item-duration';
    durationEl.textContent = '耗时 -';

    const actions = document.createElement('div');
    actions.className = 'video-item-actions';

    const openBtn = document.createElement('a');
    openBtn.className = 'geist-button-outline text-xs px-3 video-open hidden';
    openBtn.target = '_blank';
    openBtn.rel = 'noopener';
    openBtn.textContent = '打开';

    const downloadBtn = document.createElement('button');
    downloadBtn.className = 'geist-button-outline text-xs px-3 video-download';
    downloadBtn.type = 'button';
    downloadBtn.textContent = '下载';
    downloadBtn.disabled = true;

    actions.appendChild(openBtn);
    actions.appendChild(downloadBtn);
    header.appendChild(title);
    header.appendChild(durationEl);
    header.appendChild(actions);

    const body = document.createElement('div');
    body.className = 'video-item-body';
    body.innerHTML = '<div class="video-item-placeholder">生成中…</div>';

    const link = document.createElement('div');
    link.className = 'video-item-link';

    item.appendChild(header);
    item.appendChild(body);
    item.appendChild(link);
    videoStage.appendChild(item);
    videoStage.classList.remove('hidden');
    if (videoEmpty) {
      videoEmpty.classList.add('hidden');
    }

    ctx.previewItem = item;
    return item;
  }

  function updateItemLinks(item, url) {
    if (!item) return;
    const openBtn = item.querySelector('.video-open');
    const downloadBtn = item.querySelector('.video-download');
    const link = item.querySelector('.video-item-link');
    const safeUrl = url || '';
    item.dataset.url = safeUrl;
    if (link) {
      link.textContent = safeUrl;
      link.classList.toggle('has-url', Boolean(safeUrl));
    }
    if (openBtn) {
      if (safeUrl) {
        openBtn.href = safeUrl;
        openBtn.classList.remove('hidden');
      } else {
        openBtn.classList.add('hidden');
        openBtn.removeAttribute('href');
      }
    }
    if (downloadBtn) {
      downloadBtn.dataset.url = safeUrl;
      downloadBtn.disabled = !safeUrl;
    }
    if (safeUrl) {
      item.classList.remove('is-pending');
      // 更新全局进度条（显示最新完成的）
      updateProgress(100);
      setIndeterminate(false);
    }
  }

  function setIndeterminate(active) {
    if (!progressBar) return;
    if (active) {
      progressBar.classList.add('indeterminate');
    } else {
      progressBar.classList.remove('indeterminate');
    }
  }

  function clearFileSelection() {
    fileDataUrl = '';
    if (imageFileInput) {
      imageFileInput.value = '';
    }
    if (imageFileName) {
      imageFileName.textContent = '未选择文件';
    }
  }

  function normalizeAuthHeader(authHeader) {
    if (!authHeader) return '';
    if (authHeader.startsWith('Bearer ')) {
      return authHeader.slice(7).trim();
    }
    return authHeader;
  }

  function buildSseUrl(taskId, rawPublicKey) {
    const httpProtocol = window.location.protocol === 'https:' ? 'https' : 'http';
    const base = `${httpProtocol}://${window.location.host}/v1/public/video/sse`;
    const params = new URLSearchParams();
    params.set('task_id', taskId);
    params.set('t', String(Date.now()));
    if (rawPublicKey) {
      params.set('public_key', rawPublicKey);
    }
    return `${base}?${params.toString()}`;
  }

  async function createVideoTask(authHeader, params) {
    const res = await fetch('/v1/public/video/start', {
      method: 'POST',
      headers: {
        ...buildAuthHeaders(authHeader),
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(params)
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || 'Failed to create task');
    }
    const data = await res.json();
    return data && data.task_id ? String(data.task_id) : '';
  }

  async function stopVideoTask(taskId, authHeader) {
    if (!taskId) return;
    try {
      await fetch('/v1/public/video/stop', {
        method: 'POST',
        headers: {
          ...buildAuthHeaders(authHeader),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ task_ids: [taskId] })
      });
    } catch (e) {
      // ignore
    }
  }

  function extractVideoInfo(buffer) {
    if (!buffer) return null;
    if (buffer.includes('<video')) {
      const matches = buffer.match(/<video[\s\S]*?<\/video>/gi);
      if (matches && matches.length) {
        return { html: matches[matches.length - 1] };
      }
    }
    const mdMatches = buffer.match(/\[video\]\(([^)]+)\)/g);
    if (mdMatches && mdMatches.length) {
      const last = mdMatches[mdMatches.length - 1];
      const urlMatch = last.match(/\[video\]\(([^)]+)\)/);
      if (urlMatch) {
        return { url: urlMatch[1] };
      }
    }
    const urlMatches = buffer.match(/https?:\/\/[^\s<)]+/g);
    if (urlMatches && urlMatches.length) {
      return { url: urlMatches[urlMatches.length - 1] };
    }
    return null;
  }

  function renderVideoFromHtml(ctx, html) {
    const item = ctx.previewItem;
    if (!item) return;
    const body = item.querySelector('.video-item-body');
    if (!body) return;
    body.innerHTML = html;
    const videoEl = body.querySelector('video');
    let videoUrl = '';
    if (videoEl) {
      videoEl.controls = true;
      videoEl.preload = 'metadata';
      const source = videoEl.querySelector('source');
      if (source && source.getAttribute('src')) {
        videoUrl = source.getAttribute('src');
      } else if (videoEl.getAttribute('src')) {
        videoUrl = videoEl.getAttribute('src');
      }
    }
    updateItemLinks(item, videoUrl);
  }

  function renderVideoFromUrl(ctx, url) {
    const item = ctx.previewItem;
    if (!item) return;
    const safeUrl = url || '';
    const body = item.querySelector('.video-item-body');
    if (!body) return;
    body.innerHTML = `<video controls preload="metadata"><source src="${safeUrl}" type="video/mp4"></video>`;
    updateItemLinks(item, safeUrl);
  }

  function handleDelta(ctx, text) {
    if (!text || !ctx.isRunning) return;
    if (text.includes('"><?php') || text.includes('')) {
      return;
    }
    if (text.includes('超分辨率')) {
      // 更新该任务的占位符
      const placeholder = ctx.previewItem?.querySelector('.video-item-placeholder');
      if (placeholder) {
        placeholder.textContent = '超分辨率中…';
      }
      return;
    }

    if (!ctx.collectingContent) {
      const maybeVideo = text.includes('<video') || text.includes('[video](') || text.includes('http://') || text.includes('https://');
      if (maybeVideo) {
        ctx.collectingContent = true;
      }
    }

    if (ctx.collectingContent) {
      ctx.contentBuffer += text;
      const info = extractVideoInfo(ctx.contentBuffer);
      if (info) {
        if (info.html) {
          renderVideoFromHtml(ctx, info.html);
        } else if (info.url) {
          renderVideoFromUrl(ctx, info.url);
        }
      }
      return;
    }

    ctx.progressBuffer += text;
    const matches = [...ctx.progressBuffer.matchAll(/进度\s*(\d+)%/g)];
    if (matches.length) {
      const last = matches[matches.length - 1];
      const value = parseInt(last[1], 10);
      ctx.lastProgress = value;
      // 更新全局进度条（显示最新任务的进度）
      updateProgress(value);
      setIndeterminate(false);
      ctx.progressBuffer = ctx.progressBuffer.slice(Math.max(0, ctx.progressBuffer.length - 200));
    }
  }

  function finishTask(ctx, hasError) {
    ctx.stopElapsedTimer();
    if (!hasError && ctx.previewItem) {
      const placeholder = ctx.previewItem.querySelector('.video-item-placeholder');
      if (placeholder) {
        placeholder.textContent = hasError ? '生成失败' : '已完成';
      }
    }
    setButtons(false);
  }

  async function startConnection() {
    const prompt = promptInput ? promptInput.value.trim() : '';
    if (!prompt) {
      toast('请输入提示词', 'error');
      return;
    }

    const authHeader = await ensurePublicKey();
    if (authHeader === null) {
      toast('请先配置 Public Key', 'error');
      window.location.href = '/login';
      return;
    }

    updateMeta();

    // 准备请求参数
    const rawUrl = imageUrlInput ? imageUrlInput.value.trim() : '';
    const imageUrl = fileDataUrl || rawUrl;
    
    const requestParams = {
      prompt,
      image_url: imageUrl || null,
      reasoning_effort: DEFAULT_REASONING_EFFORT,
      aspect_ratio: ratioSelect ? ratioSelect.value : '3:2',
      video_length: lengthSelect ? parseInt(lengthSelect.value, 10) : 6,
      resolution_name: resolutionSelect ? resolutionSelect.value : '480p',
      preset: presetSelect ? presetSelect.value : 'normal'
    };

    let taskId = '';
    try {
      taskId = await createVideoTask(authHeader, requestParams);
    } catch (e) {
      toast('创建任务失败: ' + e.message, 'error');
      return;
    }

    // 创建任务上下文
    const ctx = new TaskContext(taskId);
    taskRegistry.set(taskId, ctx);

    // 初始化预览槽位
    initPreviewSlot(ctx);
    ctx.startElapsedTimer();

    setStatus('connected', '生成中');
    setButtons(true);
    setIndeterminate(true);

    const rawPublicKey = normalizeAuthHeader(authHeader);
    const url = buildSseUrl(taskId, rawPublicKey);
    
    const es = new EventSource(url);
    ctx.source = es;

    es.onopen = () => {
      // 连接成功
    };

    es.onmessage = (event) => {
      if (!event || !event.data || !ctx.isRunning) return;
      if (event.data === '[DONE]') {
        finishTask(ctx, false);
        ctx.close();
        return;
      }
      let payload = null;
      try {
        payload = JSON.parse(event.data);
      } catch (e) {
        return;
      }
      if (payload && payload.error) {
        toast(payload.error, 'error');
        finishTask(ctx, true);
        ctx.close();
        return;
      }
      const choice = payload.choices && payload.choices[0];
      const delta = choice && choice.delta ? choice.delta : null;
      if (delta && delta.content) {
        handleDelta(ctx, delta.content);
      }
      if (choice && choice.finish_reason === 'stop') {
        finishTask(ctx, false);
        ctx.close();
      }
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
    
    // 停止所有任务
    for (const ctx of taskRegistry.values()) {
      if (authHeader !== null) {
        await stopVideoTask(ctx.taskId, authHeader);
      }
      ctx.close();
    }
    taskRegistry.clear();
    
    setStatus('', '未连接');
    setButtons(false);
  }

  if (startBtn) {
    startBtn.addEventListener('click', () => startConnection());
  }

  if (stopBtn) {
    stopBtn.addEventListener('click', () => stopAllConnections());
  }

  if (clearBtn) {
    clearBtn.addEventListener('click', () => resetOutput());
  }

  if (videoStage) {
    videoStage.addEventListener('click', async (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      if (!target.classList.contains('video-download')) return;
      event.preventDefault();
      const item = target.closest('.video-item');
      if (!item) return;
      const url = item.dataset.url || target.dataset.url || '';
      const index = item.dataset.index || '';
      if (!url) return;
      try {
        const response = await fetch(url, { mode: 'cors' });
        if (!response.ok) {
          throw new Error('download_failed');
        }
        const blob = await response.blob();
        const blobUrl = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = blobUrl;
        anchor.download = index ? `grok_video_${index}.mp4` : 'grok_video.mp4';
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(blobUrl);
      } catch (e) {
        toast('下载失败，请检查视频链接是否可访问', 'error');
      }
    });
  }

  if (imageFileInput) {
    imageFileInput.addEventListener('change', () => {
      const file = imageFileInput.files && imageFileInput.files[0];
      if (!file) {
        clearFileSelection();
        return;
      }
      if (imageUrlInput && imageUrlInput.value.trim()) {
        imageUrlInput.value = '';
      }
      if (imageFileName) {
        imageFileName.textContent = file.name;
      }
      const reader = new FileReader();
      reader.onload = () => {
        if (typeof reader.result === 'string') {
          fileDataUrl = reader.result;
        } else {
          fileDataUrl = '';
          toast('文件读取失败', 'error');
        }
      };
      reader.onerror = () => {
        fileDataUrl = '';
        toast('文件读取失败', 'error');
      };
      reader.readAsDataURL(file);
    });
  }

  if (selectImageFileBtn && imageFileInput) {
    selectImageFileBtn.addEventListener('click', () => {
      imageFileInput.click();
    });
  }

  if (clearImageFileBtn) {
    clearImageFileBtn.addEventListener('click', () => {
      clearFileSelection();
    });
  }

  if (imageUrlInput) {
    imageUrlInput.addEventListener('input', () => {
      if (imageUrlInput.value.trim() && fileDataUrl) {
        clearFileSelection();
      }
    });
  }

  if (promptInput) {
    promptInput.addEventListener('keydown', (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
        event.preventDefault();
        startConnection();
      }
    });
  }

  updateMeta();
})();
