// pages/mine/privacy.js — 隐私与数据管理
const api = require('../../utils/api');

Page({
  clearAll() {
    wx.showModal({
      title: '清空全部数据',
      content: '将删除所有文档、向量和会话记录，且不可恢复。确认？',
      confirmColor: '#B4492E',
      success: async (res) => {
        if (!res.confirm) return;
        wx.showLoading({ title: '清理中' });
        try {
          const docs = await api.request('/api/docs');
          for (const d of docs) {
            await api.request(`/api/docs/${d.id}`, 'DELETE');
          }
          wx.hideLoading();
          wx.showToast({ title: '已清空', icon: 'success' });
        } catch (e) {
          wx.hideLoading();
          wx.showToast({ title: e.message, icon: 'none' });
        }
      },
    });
  },
});
