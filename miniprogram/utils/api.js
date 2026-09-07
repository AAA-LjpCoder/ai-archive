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

// 上传文件（formData 可携带额外字段，如原始文件名）
function uploadFile(path, filePath, name = 'file', formData = {}) {
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: baseUrl() + path,
      filePath,
      name,
      formData,
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
  return streamPost(`/api/conversations/${convId}/ask`, { question, search_only: searchOnly }, onEvent);
}

// 重新生成最后一条回答（SSE）
function streamRegen(convId, onEvent) {
  return streamPost(`/api/conversations/${convId}/regenerate`, null, onEvent);
}

// 流式 UTF-8 解码器：跨 chunk 的多字节字符/帧会正确拼接（不丢半包）
function makeUtf8Decoder() {
  let carry = []; // 上一包未完成的多字节尾字节
  return function decode(bytes) {
    const data = carry.length ? carry.concat(Array.from(bytes)) : Array.from(bytes);
    carry = [];
    let out = '';
    let i = 0;
    const n = data.length;
    while (i < n) {
      const b = data[i];
      let len;
      let cp;
      if (b < 0x80) { cp = b; len = 1; }
      else if ((b & 0xE0) === 0xC0) { cp = b & 0x1F; len = 2; }
      else if ((b & 0xF0) === 0xE0) { cp = b & 0x0F; len = 3; }
      else if ((b & 0xF8) === 0xF0) { cp = b & 0x07; len = 4; }
      else { out += '\ufffd'; i += 1; continue; }
      if (i + len > n) { carry = data.slice(i); break; } // 不完整，等下一包
      for (let j = 1; j < len; j++) cp = (cp << 6) | (data[i + j] & 0x3F);
      if (len < 4) out += String.fromCharCode(cp);
      else out += String.fromCodePoint(cp);
      i += len;
    }
    return out;
  };
}

function streamPost(url, data, onEvent) {
  const task = wx.request({
    url: baseUrl() + url,
    method: 'POST',
    data,
    header: { 'content-type': 'application/json' },
    enableChunked: true,
    success: (res) => {
      if (res.statusCode >= 300) {
        onEvent({ type: 'error', data: (res.data && res.data.detail) || `HTTP ${res.statusCode}` });
      }
    },
    fail: (err) => onEvent({ type: 'error', data: '网络请求失败：' + err.errMsg }),
  });

  // 行缓冲：SSE 帧可能跨多个网络 chunk，必须攒到完整 \n 才解析
  const decode = makeUtf8Decoder();
  let lineBuf = '';
  task.onChunkReceived((res) => {
    lineBuf += decode(new Uint8Array(res.data));
    let idx;
    while ((idx = lineBuf.indexOf('\n')) >= 0) {
      const line = lineBuf.slice(0, idx).trim();
      lineBuf = lineBuf.slice(idx + 1);
      if (!line.startsWith('data:')) continue;
      const payload = line.slice(5).trim();
      if (!payload) continue;
      try {
        onEvent(JSON.parse(payload));
      } catch (e) { /* 解析失败跳过（理论不应出现，缓冲已保证完整行） */ }
    }
    // 防御：异常流无限增长时兜底清空
    if (lineBuf.length > 65536) lineBuf = '';
  });
  return task;
}

module.exports = { request, uploadFile, streamAsk, streamRegen, baseUrl };
