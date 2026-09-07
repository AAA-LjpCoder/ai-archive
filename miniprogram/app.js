// app.js — AI档案室
App({
  globalData: {
    // 2026-09-07 M2：HTTPS 已就绪（证书已部署 + 443 放行 + SSE 验证通过）
    baseUrl: 'https://api.ai-archive.site',
    // 旧联调地址备用：http://110.42.233.73:8000（开发者工具需勾选"不校验合法域名" urlCheck:false）
    userOpenid: ''
  },

  onLaunch() {
    // M1 单用户模式：后端固定 dev_user，前端无需登录
  }
})
