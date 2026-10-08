// pages/mine/index.js — 我的
const api = require('../../utils/api');

Page({
  data: {
    quota: null,
    // ICP 备案号（工信部要求显著展示）
    icp: '冀ICP备2026033522号'
  },

  onShow() {
    api.request('/api/quota')
      .then((quota) => this.setData({ quota }))
      .catch(() => {});
  },

  goQuota() { wx.navigateTo({ url: '/pages/mine/quota' }); },
  goPrivacy() { wx.navigateTo({ url: '/pages/mine/privacy' }); },

  // 复制备案号（小程序无法直接跳工信部外链，采用复制+提示）
  copyIcp() {
    wx.setClipboardData({
      data: this.data.icp + '（工信部备案查询：beian.miit.gov.cn）',
      success: () => wx.showToast({ title: '备案号已复制', icon: 'success' })
    });
  },
});
