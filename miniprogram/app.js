// app.js — AI档案室
App({
  globalData: {
    // 开发环境：本机 FastAPI；真机调试需改为 https 域名（开发者工具已关闭域名校验）
    baseUrl: 'http://127.0.0.1:8000',
    userOpenid: ''
  },

  onLaunch() {
    // M1 单用户模式：后端固定 dev_user，前端无需登录
  }
})
