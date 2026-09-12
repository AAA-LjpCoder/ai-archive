// pages/docs/upload.js — 上传（V3：文档 + 图片 OCR）
const api = require('../../utils/api');

const IMG_EXTS = ['jpg', 'jpeg', 'png', 'webp', 'bmp', 'gif'];
const DOC_EXTS = ['txt', 'md', 'pdf', 'docx', 'pptx', 'xlsx', 'xls', 'epub', 'html', 'htm', 'csv'];
const MAX_SIZE = 20 * 1024 * 1024;

const FORMATS = [
  { name: 'MD', cls: 'fd-md' }, { name: 'PDF', cls: 'fd-pdf' },
  { name: 'DOCX', cls: 'fd-docx' }, { name: 'PPTX', cls: 'fd-pptx' },
  { name: 'XLSX', cls: 'fd-xlsx' }, { name: 'EPUB', cls: 'fd-epub' },
  { name: 'HTML', cls: 'fd-html' }, { name: 'CSV', cls: 'fd-csv' },
  { name: 'TXT', cls: 'fd-txt' }, { name: 'JPG', cls: 'fd-jpg' },
  { name: 'PNG', cls: 'fd-png' },
];

function extOf(name) {
  const m = String(name || '').match(/\.([a-zA-Z0-9]+)$/);
  return m ? m[1].toLowerCase() : '';
}

Page({
  data: { filePath: '', fileName: '', isImage: false, uploading: false, formats: FORMATS },

  // 拍照
  pickFromCamera() {
    this._pickMedia('camera');
  },

  // 相册图片
  pickFromAlbum() {
    this._pickMedia('album');
  },

  _pickMedia(sourceType) {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: [sourceType],
      sizeType: ['compressed'],
      success: (res) => {
        const f = res.tempFiles[0];
        if (!f) return;
        const path = f.tempFilePath;
        let ext = extOf(path) || 'jpg';
        if (!IMG_EXTS.includes(ext)) ext = 'jpg';
        const now = new Date();
        const pad = (n) => (n < 10 ? '0' + n : '' + n);
        const ts = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
        const name = sourceType === 'camera' ? `拍照_${ts}.${ext}` : `图片_${ts}.${ext}`;
        this._accept({ path, size: f.size || 0, name }, false);
      },
      fail: (err) => this._pickFail(err),
    });
  },

  // 选择失败时把真实原因弹出来（隐私授权未声明时原来会“无反应”）
  _pickFail(err) {
    const msg = (err && err.errMsg) || '未知错误';
    if (/cancel/i.test(msg)) return;
    wx.showModal({
      title: '打不开选择器',
      content: msg + '\n\n若提到隐私授权，请到微信公众平台「设置 → 服务内容声明 → 用户隐私保护指引」勾选「收集你选中的照片或视频信息」。',
      showCancel: false,
      confirmText: '知道了',
    });
  },

  // 聊天选择（文档或图片）
  chooseFile() {
    wx.chooseMessageFile({
      count: 1,
      type: 'all',
      success: (res) => {
        const f = res.tempFiles[0];
        if (!f) return;
        this._accept({ path: f.path, size: f.size || 0, name: f.name || '' }, true);
      },
      fail: (err) => this._pickFail(err),
    });
  },

  // 统一校验 + 展示
  _accept(f, allowDoc) {
    const ext = extOf(f.name) || extOf(f.path);
    const isImage = IMG_EXTS.includes(ext);
    const isDoc = DOC_EXTS.includes(ext);
    if (!isImage && !(allowDoc && isDoc)) {
      wx.showToast({
        title: isDoc ? '请用「聊天文件」外的来源选择文档' : '不支持该格式（文档或 jpg/png 图片）',
        icon: 'none',
      });
      return;
    }
    if (f.size > MAX_SIZE) {
      wx.showToast({ title: '文件超过 20MB 限制', icon: 'none' });
      return;
    }
    this.setData({ filePath: f.path, fileName: f.name || '未命名', isImage });
  },

  upload() {
    if (!this.data.filePath || this.data.uploading) return;
    this.setData({ uploading: true });
    wx.showLoading({ title: '上传中' });
    api.uploadFile('/api/docs/upload', this.data.filePath, 'file', { filename: this.data.fileName })
      .then((doc) => {
        wx.hideLoading();
        this.setData({ uploading: false, filePath: '', fileName: '', isImage: false });
        wx.showToast({ title: '上传成功，处理中', icon: 'success' });
        setTimeout(() => wx.navigateBack(), 800);
      })
      .catch((e) => {
        wx.hideLoading();
        this.setData({ uploading: false });
        wx.showToast({ title: e.message || '上传失败', icon: 'none' });
      });
  },
});
