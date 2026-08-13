// pages/docs/index.js — 文档库
const api = require('../../utils/api');

Page({
  data: { docs: [], loading: true },

  onShow() { this.load(); },

  async load() {
    try {
      const docs = await api.request('/api/docs');
      this.setData({ docs: docs.map((d) => ({ ...d, size_kb: (d.size / 1024).toFixed(0) })), loading: false });
    } catch (e) {
      this.setData({ loading: false });
      wx.showToast({ title: e.message, icon: 'none' });
    }
  },

  goUpload() { wx.navigateTo({ url: '/pages/docs/upload' }); },
  goDetail(e) { wx.navigateTo({ url: `/pages/docs/detail?id=${e.currentTarget.dataset.id}` }); },

  deleteDoc(e) {
    const { id, name } = e.currentTarget.dataset;
    wx.showModal({
      title: '删除文档',
      content: `确认删除「${name}」？向量数据将一并清除。`,
      success: (res) => {
        if (!res.confirm) return;
        api.request(`/api/docs/${id}`, 'DELETE')
          .then(() => this.load())
          .catch((err) => wx.showToast({ title: err.message, icon: 'none' }));
      },
    });
  },

  statusText(status) {
    return { pending: '排队中', processing: '处理中', ready: '就绪', failed: '失败' }[status] || status;
  },
});
