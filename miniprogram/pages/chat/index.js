// pages/chat/index.js — 会话列表
const api = require('../../utils/api');

Page({
  data: { convs: [], loading: true, q: '' },

  onShow() { this.load(); },

  async load(silent) {
    const q = (this.data.q || '').trim();
    if (!silent) this.setData({ loading: true });
    try {
      const url = '/api/conversations' + (q ? `?q=${encodeURIComponent(q)}` : '');
      const convs = await api.request(url);
      this.setData({ convs, loading: false });
    } catch (e) {
      this.setData({ loading: false });
      wx.showToast({ title: e.message, icon: 'none' });
    }
  },

  // 搜索：300ms 防抖，静默刷新（不闪骨架屏）
  onSearchInput(e) {
    this.setData({ q: e.detail.value });
    clearTimeout(this._t);
    this._t = setTimeout(() => this.load(true), 300);
  },

  clearSearch() {
    clearTimeout(this._t);
    this.setData({ q: '' });
    this.load();
  },

  newConversation() {
    const mode = 'global';
    wx.showLoading({ title: '创建中' });
    api.request('/api/conversations', 'POST', { mode })
      .then((conv) => {
        wx.hideLoading();
        wx.navigateTo({ url: `/pages/chat/detail?id=${conv.id}&mode=${mode}` });
      })
      .catch((e) => {
        wx.hideLoading();
        wx.showToast({ title: e.message, icon: 'none' });
      });
  },

  openConversation(e) {
    const { id, mode } = e.currentTarget.dataset;
    wx.navigateTo({ url: `/pages/chat/detail?id=${id}&mode=${mode}` });
  },

  deleteConversation(e) {
    const { id } = e.currentTarget.dataset;
    wx.showModal({
      title: '删除会话',
      content: '确认删除该会话及其消息？',
      success: (res) => {
        if (!res.confirm) return;
        api.request(`/api/conversations/${id}`, 'DELETE')
          .then(() => this.load())
          .catch((err) => wx.showToast({ title: err.message, icon: 'none' }));
      },
    });
  },
});
