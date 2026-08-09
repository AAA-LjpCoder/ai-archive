// utils/api.js — 后端 API 封装（含 SSE 流式处理）
const app = getApp();

function baseUrl() {
  return app.globalData.baseUrl;
}

function request(path, method = 'GET', data = null) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: baseUrl() + path,
      method,
      data,
      header: { 'content-type': 'application/json' },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(res.data);
        else reject(new Error((res.data && res.data.detail) || `HTTP ${res.statusCode}`));
      },
      fail: (err) => reject(new Error('网络请求失败：' + err.errMsg)),
    });
  });
}

// 上传文件
function uploadFile(path, filePath, name = 'file') {
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: baseUrl() + path,
      filePath,
      name,
      success: (res) => {
        try {
          const data = JSON.parse(res.data);
          if (res.statusCode >= 200 && res.statusCode < 300) resolve(data);
          else reject(new Error(data.detail || `HTTP ${res.statusCode}`));
        } catch (e) {
          reject(new Error('响应解析失败'));
        }
      },
      fail: (err) => reject(new Error('上传失败：' + err.errMsg)),
    });
  });
}

// 流式问答（SSE over wx.request enableChunked）
// 回调: onEvent({type: 'citations'|'delta'|'done'|'error', data})
function streamAsk(convId, question, searchOnly, onEvent) {
  const task = wx.request({
    url: baseUrl() + `/api/conversations/${convId}/ask`,
    method: 'POST',
    data: { question, search_only: searchOnly },
    header: { 'content-type': 'application/json' },
    enableChunked: true,
    success: (res) => {
      if (res.statusCode >= 300) {
        onEvent({ type: 'error', data: (res.data && res.data.detail) || `HTTP ${res.statusCode}` });
      }
    },
    fail: (err) => onEvent({ type: 'error', data: '网络请求失败：' + err.errMsg }),
  });

  task.onChunkReceived((res) => {
    const bytes = new Uint8Array(res.data);
    const text = decodeURIComponent(escape(String.fromCharCode(...bytes))); // 兼容中文 chunk
    const lines = text.split('\n');
    for (const line of lines) {
      const s = line.trim();
      if (!s.startsWith('data:')) continue;
      const payload = s.slice(5).trim();
      if (!payload) continue;
      try {
        const obj = JSON.parse(payload);
        onEvent(obj);
      } catch (e) { /* 半包 JSON 忽略，等完整帧 */ }
    }
  });
  return task;
}

module.exports = { request, uploadFile, streamAsk, baseUrl };
