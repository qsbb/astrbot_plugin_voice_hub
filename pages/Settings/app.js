'use strict';

const $ = id => document.getElementById(id);
const bridge = window.AstrBotPluginPage || {
  ready: async () => ({}),
  apiGet: async () => ({ success: false, error: 'AstrBot Pages bridge unavailable' }),
  apiPost: async () => ({ success: false, error: 'AstrBot Pages bridge unavailable' }),
  upload: async () => ({ success: false, error: 'AstrBot Pages bridge unavailable' }),
};

let state = { config: {}, voices: [], defaults: {} };

function toast(message, type = 'ok') {
  const el = $('toast');
  el.textContent = message;
  el.className = `toast ${type}`;
  el.style.display = 'block';
  clearTimeout(el._timer);
  el._timer = setTimeout(() => { el.style.display = 'none'; }, 2800);
}

function configPayload() {
  return {
    api_key: $('api-key').value.trim(),
    base_url: $('base-url').value.trim(),
    model: $('model').value.trim(),
    default_context: $('default-context').value,
    max_text_chars: Number($('max-text-chars').value || 500),
    max_concurrency: Number($('max-concurrency').value || 1),
    max_voice_file_mb: Number($('max-voice-file-mb').value || 10),
  };
}

function applyState(payload) {
  state.config = payload.config || {};
  state.voices = payload.voices || [];
  state.defaults = payload.defaults || {};
  $('api-key').value = state.config.api_key || '';
  $('base-url').value = state.config.base_url || 'https://api.xiaomimimo.com/v1';
  $('model').value = state.config.model || 'mimo-v2.5-tts-voiceclone';
  $('default-context').value = state.config.default_context || '';
  $('max-text-chars').value = state.config.max_text_chars || 500;
  $('max-concurrency').value = state.config.max_concurrency || 1;
  $('max-voice-file-mb').value = state.config.max_voice_file_mb || 10;
  renderVoices();
}

function renderVoices() {
  $('voice-count').textContent = `${state.voices.length} 个音色`;
  const list = $('voice-list');
  const select = $('preview-voice');
  list.innerHTML = '';
  select.innerHTML = '';
  if (!state.voices.length) {
    list.innerHTML = '<div class="muted">暂无音色，请上传 mp3 或 wav 参考音频。</div>';
    select.innerHTML = '<option value="">暂无音色</option>';
    return;
  }
  state.voices.forEach(voice => {
    const isDefault = voice.id === state.defaults.global_default_voice_id;
    const disabled = !voice.enabled;
    const card = document.createElement('div');
    card.className = 'voice-card';
    card.innerHTML = `
      <div>
        <div class="voice-title">${escapeHtml(voice.name)}${isDefault ? ' · 全局默认' : ''}${disabled ? ' · 已禁用' : ''}</div>
        <div class="voice-meta">${escapeHtml(voice.description || '无说明')} · ${escapeHtml(voice.id)}</div>
      </div>
      <div class="voice-actions">
        <button data-action="default" data-id="${voice.id}">设为默认</button>
        <button data-action="toggle" data-id="${voice.id}">${disabled ? '启用' : '禁用'}</button>
        <button class="danger" data-action="delete" data-id="${voice.id}">删除</button>
      </div>`;
    list.appendChild(card);
    const option = document.createElement('option');
    option.value = voice.id;
    option.textContent = voice.name;
    select.appendChild(option);
  });
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

async function refresh() {
  const payload = await bridge.apiGet('get_config');
  if (!payload.success) throw new Error(payload.error || '加载配置失败');
  applyState(payload);
}

async function saveConfig() {
  const res = await bridge.apiPost('save_config', configPayload());
  if (!res.success) throw new Error(res.error || '保存失败');
  state.config = res.config || state.config;
  toast('配置已保存');
}

async function uploadVoice() {
  const file = $('voice-file').files[0];
  if (!file) throw new Error('请选择音频文件');
  if (!$('voice-consent').checked) throw new Error('请先确认已获得声音使用授权');
  const res = await bridge.upload('upload_voice_sample', file);
  if (!res.success || !res.voice) throw new Error(res.error || '上传失败');
  const name = $('voice-name').value.trim();
  const description = $('voice-desc').value.trim();
  if (name || description) {
    await bridge.apiPost('update_voice', {
      voice_id: res.voice.id,
      name: name || res.voice.name,
      description,
    });
  }
  $('voice-file').value = '';
  $('voice-name').value = '';
  $('voice-desc').value = '';
  $('voice-consent').checked = false;
  await refresh();
  toast('音色已上传');
}

async function voiceAction(action, id) {
  const voice = state.voices.find(item => item.id === id);
  if (!voice) return;
  if (action === 'default') {
    const res = await bridge.apiPost('set_default_voice', { scope: 'global', voice_id: id });
    if (!res.success) throw new Error(res.error || '设置默认失败');
  } else if (action === 'toggle') {
    const res = await bridge.apiPost('update_voice', { voice_id: id, enabled: !voice.enabled });
    if (!res.success) throw new Error(res.error || '更新失败');
  } else if (action === 'delete') {
    if (!confirm(`删除音色「${voice.name}」？`)) return;
    const res = await bridge.apiPost('delete_voice', { voice_id: id });
    if (!res.success) throw new Error(res.error || '删除失败');
  }
  await refresh();
}

async function preview() {
  const text = $('preview-text').value.trim();
  const voiceId = $('preview-voice').value;
  if (!text) throw new Error('请输入试听文本');
  if (!voiceId) throw new Error('请选择音色');
  const res = await bridge.apiPost('synthesize_preview', {
    text,
    voice_id: voiceId,
    context: $('default-context').value,
  });
  if (!res.success || !res.audio_data) throw new Error(res.error || '试听失败');
  $('preview-audio').src = res.audio_data;
  $('preview-audio').play().catch(() => {});
}

function bind(id, handler) {
  $(id).addEventListener('click', async () => {
    try {
      await handler();
    } catch (error) {
      toast(String(error.message || error), 'err');
    }
  });
}

async function init() {
  await bridge.ready();
  bind('save-config', saveConfig);
  bind('upload-voice', uploadVoice);
  bind('preview-btn', preview);
  $('voice-list').addEventListener('click', async event => {
    const button = event.target.closest('button[data-action]');
    if (!button) return;
    try {
      await voiceAction(button.dataset.action, button.dataset.id);
    } catch (error) {
      toast(String(error.message || error), 'err');
    }
  });
  await refresh();
}

init().catch(error => toast(String(error.message || error), 'err'));
