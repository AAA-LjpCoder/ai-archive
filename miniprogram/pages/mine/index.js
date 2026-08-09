// pages/mine/index.js — 我的
const api = require('../../utils/api');

Page({
  data: { quota: null },

  onShow() {
    api.request('/api/quota')
      .then((quota) => this.setData({ quota }))
      .catch(() => {});
  },

  goQuota() { wx.navigateTo({ url: '/pages/mine/quota' }); },
  goPrivacy() { wx.navigateTo({ url: '/pages/mine/privacy' }); },
});
