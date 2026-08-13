// app.js — AI档案室
App({
  globalData: {
    // 联调环境：腾讯云服务器；开发者工具需勾选"不校验合法域名"（project.config.json urlCheck:false）
    // 上架前 M2 换 https 域名 + ICP 备案
    baseUrl: 'http://122.51.27.182:8000',
    userOpenid: ''
  },

  onLaunch() {
    // M1 单用户模式：后端固定 dev_user，前端无需登录
  }
})
