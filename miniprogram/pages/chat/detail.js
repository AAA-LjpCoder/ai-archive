// pages/chat/detail.js — 对话页（流式 + 引用）
const api = require('../../utils/api');

Page({
  data: {
    convId: null,
    mode: 'global',
    messages: [],       // {role, content, citations, streaming}
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
      this.setData({ messages: msgs.map((m) => ({ ...m, streaming: false })) });
      this.scrollBottom();
    } catch (e) {
      wx.showToast({ title: e.message, icon: 'none' });
    }
  },

  onInput(e) { this.setData({ input: e.detail.value }); },
  toggleSearchOnly(e) { this.setData({ searchOnly: e.detail.value }); },

  scrollBottom() {
    this.setData({ scrollTo: `msg-${this.data.messages.length}` });
  },

  send() {
    const q = this.data.input.trim();
    if (!q || this.data.sending) return;

    const messages = [...this.data.messages];
    messages.push({ role: 'user', content: q, streaming: false });
    messages.push({ role: 'assistant', content: '', citations: null, streaming: true });
    this.setData({ messages, input: '', sending: true });
    this.scrollBottom();

    const assistant = messages[messages.length - 1];
    let answer = '';
    let citations = null;

    api.streamAsk(this.data.convId, q, this.data.searchOnly, (evt) => {
      if (evt.type === 'citations') {
        citations = evt.data;
        this.setData({ [`messages[${messages.length - 1}].citations`]: citations });
      } else if (evt.type === 'delta') {
        answer += evt.data;
        this.setData({ [`messages[${messages.length - 1}].content`]: answer });
        this.scrollBottom();
      } else if (evt.type === 'error') {
        answer = '出错了：' + evt.data;
        this.setData({ [`messages[${messages.length - 1}].content`]: answer, sending: false, [`messages[${messages.length - 1}].streaming`]: false });
        wx.showToast({ title: evt.data, icon: 'none' });
      } else if (evt.type === 'done') {
        this.setData({ sending: false, [`messages[${messages.length - 1}].streaming`]: false });
        this.scrollBottom();
      }
    });
  },

  onCitationTap(e) {
    const { index } = e.currentTarget.dataset;
    const citations = this.data.messages[this.data.citationMsgIndex || 0].citations;
    // 简单展示：弹窗显示引用来源
    const c = (this.data.lastCitations || [])[index];
    if (!c) return;
    wx.showModal({
      title: c.doc_name,
      content: `第${c.page_no || '-'}页\n\n${c.snippet}`,
      showCancel: false,
    });
  },

  onAssistantTap(e) {
    const { index } = e.currentTarget.dataset;
    const msg = this.data.messages[index];
    if (msg && msg.citations) this.setData({ lastCitations: msg.citations });
  },
});
