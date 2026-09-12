// utils/api.js — 后端 API 封装（含 SSE 流式处理）
const app = getApp();

function baseUrl() {
  return app.globalData.baseUrl;
}

// 附加登录 token（Authorization: Bearer）
function authHeaders(extra) {
  const h = extra || {};
  const token = (app.globalData && app.globalData.token) || wx.getStorageSync('token') || '';
  if (token) h['Authorization'] = 'Bearer ' + token;
  return h;
}

// 清掉本地登录态（token 失效时用）：storage 和 globalData 都要清，否则下次仍会带旧 token
function clearAuth() {
  if (app.globalData) app.globalData.token = '';
  wx.removeStorageSync('token');
  wx.removeStorageSync('openid');
}

function request(path, method = 'GET', data = null, _retried = false) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: baseUrl() + path,
      method,
      data,
      header: authHeaders({ 'content-type': 'application/json' }),
      success: (res) => {
        if (res.statusCode === 401 && !_retried) {
          // token 失效：清掉过期 token，强制重新登录后重试一次
          clearAuth();
          app.ensureLogin(true).then((ok) => {
            if (ok) {
              request(path, method, data, true).then(resolve).catch(reject);
            } else {
              reject(new Error('未登录，请稍后重试'));
            }
          });
          return;
        }
        if (res.statusCode >= 200 && res.statusCode < 300) resolve(res.data);
        else reject(new Error((res.data && res.data.detail) || `HTTP ${res.statusCode}`));
      },
      fail: (err) => reject(new Error('网络请求失败：' + err.errMsg)),
    });
  });
}

// 上传文件（formData 可携带额外字段，如原始文件名）
function uploadFile(path, filePath, name = 'file', formData = {}, _retried = false) {
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: baseUrl() + path,
      filePath,
      name,
      formData,
      header: authHeaders(),
      success: (res) => {
        if (res.statusCode === 401 && !_retried) {
          clearAuth();
          app.ensureLogin(true).then((ok) => {
            if (ok) {
              uploadFile(path, filePath, name, formData, true).then(resolve).catch(reject);
            } else {
              reject(new Error('未登录，请稍后重试'));
            }
          });
          return;
        }
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

function streamPost(url, data, onEvent, _retried = false) {
  // 收尾守卫：保证 onEvent 只收到一次 done，避免页面 sending 永久锁死
  let finished = false;
  let watchdog = null;

  const close = (errMsg) => {
    if (finished) return;
    finished = true;
    if (watchdog) clearTimeout(watchdog);
    if (errMsg) onEvent({ type: 'error', data: errMsg });
    onEvent({ type: 'done' });
  };

  const task = wx.request({
    url: baseUrl() + url,
    method: 'POST',
    data,
    header: authHeaders({ 'content-type': 'application/json' }),
    enableChunked: true,
    success: (res) => {
      if (res.statusCode >= 300) {
        if (res.statusCode === 401 && !_retried) {
          // token 失效：流式请求同样走「清缓存 + 强制重登 + 重试一次」，避免主交互卡死
          clearAuth();
          app.ensureLogin(true).then((ok) => {
            if (ok) streamPost(url, data, onEvent, true);
            else close('登录已过期，请重新打开小程序');
          });
          return;
        }
        close(res.statusCode === 401 ? '登录已过期，请重新打开小程序' : ((res.data && res.data.detail) || `HTTP ${res.statusCode}`));
        return;
      }
      // 连接正常结束但从未收到 done（服务端异常中断等）→ 补齐收尾
      close(null);
    },
    fail: (err) => close('网络请求失败：' + err.errMsg),
  });

  // 兜底：长时间既无 done 也无 success/fail（例如卡死）→ 主动收尾
  watchdog = setTimeout(() => {
    if (finished) return;
    try { task.abort(); } catch (e) { /* ignore */ }
    close('响应超时，请重试');
  }, 180000);

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
        const evt = JSON.parse(payload);
        if (evt && evt.type === 'done' && !finished) {
          finished = true;
          if (watchdog) clearTimeout(watchdog);
        }
        onEvent(evt);
      } catch (e) { /* 解析失败跳过（理论不应出现，缓冲已保证完整行） */ }
    }
    // 防御：异常流无限增长时兜底清空
    if (lineBuf.length > 65536) lineBuf = '';
  });
  return task;
}

module.exports = { request, uploadFile, streamAsk, streamRegen, baseUrl };
