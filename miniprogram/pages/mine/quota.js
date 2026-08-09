// pages/mine/quota.js — 额度详情
const api = require('../../utils/api');

Page({
  data: { quota: null },

  onShow() {
    api.request('/api/quota')
      .then((quota) => this.setData({ quota }))
      .catch((e) => wx.showToast({ title: e.message, icon: 'none' }));
  },

  watchAd() {
    // M3 接入激励视频广告组件；当前直接调 reward 接口（开发阶段）
    api.request('/api/quota/reward?kind=asks&amount=10', 'POST')
      .then(() => {
        wx.showToast({ title: '+10 轮问答', icon: 'success' });
        this.onShow();
      })
      .catch((e) => wx.showToast({ title: e.message, icon: 'none' }));
  },
});
