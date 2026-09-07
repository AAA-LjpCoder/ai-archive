// pages/chat/detail.js — 对话页（流式 + 引用 + Markdown 渲染）
const api = require('../../utils/api');
const { mdToNodes } = require('../../utils/md2nodes');

Page({
  data: {
    convId: null,
    mode: 'global',
    messages: [],       // {role, content, nodes, citations, streaming}
    input: '',
    searchOnly: false,
    sending: false,
    scrollTo: '',
  },

  onLoad(options) {
    this.setData({ convId: Number(options.id), mode: options.mode || 'global' });
    this.loadHistory();
  },

  async loadHistory() {
    try {
      const msgs = await api.request(`/api/conversations/${this.data.convId}/messages`);
      this.setData({
        messages: msgs.map((m) => ({
          ...m,
          streaming: false,
          nodes: m.role === 'assistant' ? mdToNodes(m.content) : null,
        })),
      });
      this.scrollBottom();
    } catch (e) {
      wx.showToast({ title: e.message, icon: 'none' });
    }
  },

  onInput(e) { this.setData({ input: e.detail.value }); },
  toggleSearchOnly(e) { this.setData({ searchOnly: e.detail.value }); },

  // ---- 会话框附件：图/文件 → 入库 → 自动开单文档会话 ----
  attachTap() {
    if (this.data.sending) return;
    wx.showActionSheet({
      itemList: ['拍照上传', '相册图片上传', '聊天选择文件'],
      success: (res) => {
        if (res.tapIndex === 0) this._pickAndUpload('camera');
        else if (res.tapIndex === 1) this._pickAndUpload('album');
        else if (res.tapIndex === 2) this._pickAndUpload('chat');
      },
    });
  },

  _pickAndUpload(source) {
    if (source === 'chat') {
      wx.chooseMessageFile({
        count: 1,
        type: 'all',
        success: (r) => {
          const f = r.tempFiles[0];
          if (f) this._uploadAttach(f.path, f.name || '', f.size || 0);
        },
      });
      return;
    }
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: [source],
      sizeType: ['compressed'],
      success: (r) => {
        const f = r.tempFiles[0];
        if (!f) return;
        let ext = (f.tempFilePath.match(/\.(\w+)$/) || [])[1];
        ext = ext && /^(jpe?g|png|webp|bmp|gif)$/i.test(ext) ? ext.toLowerCase() : 'jpg';
        const now = new Date();
        const pad = (n) => (n < 10 ? '0' + n : '' + n);
        const ts = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
        const name = `${source === 'camera' ? '拍照' : '图片'}_${ts}.${ext}`;
        this._uploadAttach(f.tempFilePath, name, f.size || 0);
      },
    });
  },

  async _uploadAttach(path, name, size) {
    if (size > 20 * 1024 * 1024) {
      wx.showToast({ title: '文件超过 20MB 限制', icon: 'none' });
      return;
    }
    wx.showLoading({ title: '上传入库中…' });
    try {
      const doc = await api.uploadFile('/api/docs/upload', path, 'file', { filename: name });
      wx.showLoading({ title: '创建会话…' });
      const conv = await api.request('/api/conversations', 'POST', {
        mode: 'doc',
        doc_id: doc.id,
        title: doc.name,
      });
      wx.hideLoading();
      wx.showToast({ title: '已入库，识别完成即可提问', icon: 'none' });
      setTimeout(
        () => wx.redirectTo({ url: `/pages/chat/detail?id=${conv.id}&mode=doc` }),
        900
      );
    } catch (e) {
      wx.hideLoading();
      wx.showToast({ title: (e && e.message) || '上传失败', icon: 'none' });
    }
  },

  scrollBottom() {
    // 必须指向真实存在的节点，否则 scroll-into-view 找不到目标可能引发渲染层异常
    const len = this.data.messages.length;
    this.setData({ scrollTo: len > 0 ? `msg-${len - 1}` : '' });
  },

  quickAsk(e) {
    const q = e.currentTarget.dataset.q;
    this.setData({ input: q }, () => this.send());
  },

  send() {
    const q = this.data.input.trim();
    if (!q || this.data.sending) return;

    const messages = [...this.data.messages];
    const uid = Date.now() + '-' + Math.random().toString(36).slice(2, 6);
    messages.push({ id: `u-${uid}`, role: 'user', content: q, streaming: false });
    messages.push({ id: `a-${uid}`, role: 'assistant', content: '', nodes: [], citations: null, streaming: true });
    this.setData({ messages, input: '', sending: true });
    this.scrollBottom();

    let answer = '';
    let citations = null;

    api.streamAsk(this.data.convId, q, this.data.searchOnly, (evt) => {
      const idx = messages.length - 1;
      if (evt.type === 'citations') {
        citations = evt.data;
        this.setData({ [`messages[${idx}].citations`]: citations });
      } else if (evt.type === 'delta') {
        answer += evt.data;
        this.setData({
          [`messages[${idx}].content`]: answer,
          [`messages[${idx}].nodes`]: mdToNodes(answer),
        });
        this.scrollBottom();
      } else if (evt.type === 'error') {
        answer = '出错了：' + evt.data;
        this.setData({
          [`messages[${idx}].content`]: answer,
          [`messages[${idx}].nodes`]: mdToNodes(answer),
          sending: false,
          [`messages[${idx}].streaming`]: false,
        });
        wx.showToast({ title: evt.data, icon: 'none' });
      } else if (evt.type === 'done') {
        this.setData({ sending: false, [`messages[${idx}].streaming`]: false });
        this.scrollBottom();
        // 拉一次历史，拿服务器真实消息 id（供反馈/重新生成使用）
        this.loadHistory();
      }
    });
  },

  // 重新生成最后一条 AI 回答
  regenerate() {
    const msgs = this.data.messages;
    const last = msgs[msgs.length - 1];
    if (this.data.sending || !last || last.role !== 'assistant' || last.streaming) return;
    wx.showModal({
      title: '重新生成',
      content: '将替换这条回答并重跑一遍（消耗一轮问答额度）。',
      confirmText: '重新生成',
      confirmColor: '#146B5A',
      success: (res) => {
        if (res.confirm) this.doRegenerate();
      },
    });
  },

  doRegenerate() {
    const idx = this.data.messages.length - 1;
    this.setData({
      sending: true,
      [`messages[${idx}].streaming`]: true,
      [`messages[${idx}].content`]: '',
      [`messages[${idx}].nodes`]: [],
      [`messages[${idx}].citations`]: null,
    });
    this.scrollBottom();

    let answer = '';
    api.streamRegen(this.data.convId, (evt) => {
      if (evt.type === 'citations') {
        this.setData({ [`messages[${idx}].citations`]: evt.data });
      } else if (evt.type === 'delta') {
        answer += evt.data;
        this.setData({
          [`messages[${idx}].content`]: answer,
          [`messages[${idx}].nodes`]: mdToNodes(answer),
        });
        this.scrollBottom();
      } else if (evt.type === 'error') {
        answer = '出错了：' + evt.data;
        this.setData({
          sending: false,
          [`messages[${idx}].streaming`]: false,
          [`messages[${idx}].content`]: answer,
          [`messages[${idx}].nodes`]: mdToNodes(answer),
        });
        wx.showToast({ title: evt.data, icon: 'none' });
      } else if (evt.type === 'done') {
        this.setData({ sending: false, [`messages[${idx}].streaming`]: false });
        this.scrollBottom();
        this.loadHistory();
      }
    });
  },

  // 点赞/点踩（再点一次取消）
  toggleFeedback(e) {
    const { msgidx, val } = e.currentTarget.dataset;
    const msg = this.data.messages[msgidx];
    if (!msg || msg.role !== 'assistant' || typeof msg.id !== 'number') return;
    const next = msg.feedback === val ? null : val;
    api.request(`/api/messages/${msg.id}/feedback`, 'PUT', { value: next })
      .then(() => this.setData({ [`messages[${msgidx}].feedback`]: next }))
      .catch((err) => wx.showToast({ title: err.message, icon: 'none' }));
  },

  copyAnswer(e) {
    const { msgidx } = e.currentTarget.dataset;
    const msg = this.data.messages[msgidx];
    if (!msg || !msg.content) return;
    wx.setClipboardData({ data: msg.content });
  },

  onCitationTap(e) {
    const { cidx, msgidx } = e.currentTarget.dataset;
    const msg = this.data.messages[msgidx];
    if (!msg || !msg.citations) return;
    const c = msg.citations[cidx];
    if (!c) return;
    wx.showModal({
      title: `${c.doc_name}${c.page_no ? ' · p' + c.page_no : ''}`,
      content: c.snippet,
      showCancel: false,
      confirmText: '知道了',
    });
  },
});
