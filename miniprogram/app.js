// app.js — AI档案室
App({
  globalData: {
    // 2026-09-07 M2：HTTPS 已就绪（证书已部署 + 443 放行 + SSE 验证通过）
    baseUrl: 'https://api.ai-archive.site',
    // 旧联调地址备用：http://110.42.233.73:8000（开发者工具需勾选"不校验合法域名" urlCheck:false）
    userOpenid: '',
    token: ''
  },

  onLaunch() {
    this.ensureLogin();
  },

  // 微信登录：wx.login → 后端换 token
  // dev 后端未配 WECHAT_APP_SECRET 时返回 503 → 静默跳过（auth 层自动回落 dev_user，免登录自测）
  ensureLogin(force) {
    const cached = !force && wx.getStorageSync('token');
    if (cached) {
      this.globalData.token = cached;
      const openid = wx.getStorageSync('openid');
      if (openid) this.globalData.userOpenid = openid;
      return Promise.resolve(true);
    }
    return new Promise((resolve) => {
      wx.login({
        success: (res) => {
          if (!res.code) return resolve(false);
          wx.request({
            url: this.globalData.baseUrl + '/api/auth/login',
            method: 'POST',
            data: { code: res.code },
            header: { 'content-type': 'application/json' },
            success: (r) => {
              if (r.statusCode === 200 && r.data && r.data.token) {
                this.globalData.token = r.data.token;
                this.globalData.userOpenid = r.data.openid || '';
                wx.setStorageSync('token', r.data.token);
                wx.setStorageSync('openid', r.data.openid || '');
                resolve(true);
              } else {
                // 503（未配置密钥）/其他：dev 模式免登录，静默
                resolve(false);
              }
            },
            fail: () => resolve(false),
            complete: () => {},
          });
        },
        fail: () => resolve(false),
      });
    });
  }
})
