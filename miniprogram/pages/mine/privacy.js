// pages/mine/privacy.js — 隐私与数据管理
const api = require('../../utils/api');

Page({
  clearAll() {
    wx.showModal({
      title: '清空全部数据',
      content: '将删除所有文档、向量、会话与问答记录，且不可恢复。确认继续？',
      confirmText: '继续',
      confirmColor: '#B4492E',
      success: (res) => {
        if (!res.confirm) return;
        // 二次确认：需输入「清空」才执行，防误触
        wx.showModal({
          title: '最后确认',
          editable: true,
          placeholderText: '输入「清空」以确认',
          confirmText: '清空',
          confirmColor: '#B4492E',
          success: (res2) => {
            if (!res2.confirm) return;
            if ((res2.content || '').trim() !== '清空') {
              wx.showToast({ title: '输入不匹配，已取消', icon: 'none' });
              return;
            }
            wx.showLoading({ title: '清理中' });
            api.request('/api/me/data', 'DELETE')
              .then(() => {
                wx.hideLoading();
                wx.showToast({ title: '已全部清空', icon: 'success' });
              })
              .catch((e) => {
                wx.hideLoading();
                wx.showToast({ title: e.message, icon: 'none' });
              });
          },
        });
      },
    });
  },
});
