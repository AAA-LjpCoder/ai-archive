// pages/mine/index.js — 我的
const api = require('../../utils/api');

Page({
  data: {
    quota: null,
    // TODO: 替换为实际 ICP 备案号（腾讯云控制台可查，格式：冀ICP备2026033522号）
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
