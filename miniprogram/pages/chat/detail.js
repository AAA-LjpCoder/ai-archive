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
