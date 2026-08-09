// pages/docs/detail.js — 文档详情
const api = require('../../utils/api');

Page({
  data: { doc: null, chunks: [] },

  onLoad(options) {
    this.docId = Number(options.id);
    this.load();
  },

  async load() {
    try {
      const [doc, chunks] = await Promise.all([
        api.request(`/api/docs/${this.docId}`),
        api.request(`/api/docs/${this.docId}/chunks?limit=30`),
      ]);
      this.setData({ doc, chunks });
    } catch (e) {
      wx.showToast({ title: e.message, icon: 'none' });
    }
  },

  askThisDoc() {
    if (!this.data.doc || this.data.doc.status !== 'ready') {
      wx.showToast({ title: '文档处理完成后才能提问', icon: 'none' });
      return;
    }
    wx.showLoading({ title: '创建会话' });
    api.request('/api/conversations', 'POST', { mode: 'doc', doc_id: this.docId })
      .then((conv) => {
        wx.hideLoading();
        wx.navigateTo({ url: `/pages/chat/detail?id=${conv.id}&mode=doc` });
      })
      .catch((e) => {
        wx.hideLoading();
        wx.showToast({ title: e.message, icon: 'none' });
      });
  },

  deleteDoc() {
    wx.showModal({
      title: '删除文档',
      content: `确认删除「${this.data.doc.name}」？`,
      success: (res) => {
        if (!res.confirm) return;
        api.request(`/api/docs/${this.docId}`, 'DELETE')
          .then(() => {
            wx.showToast({ title: '已删除', icon: 'success' });
            setTimeout(() => wx.navigateBack(), 600);
          })
          .catch((e) => wx.showToast({ title: e.message, icon: 'none' }));
      },
    });
  },
});
