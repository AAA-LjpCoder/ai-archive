// pages/docs/upload.js — 上传
const api = require('../../utils/api');

const FORMATS = [
  { name: 'MD', cls: 'fd-md' }, { name: 'PDF', cls: 'fd-pdf' },
  { name: 'DOCX', cls: 'fd-docx' }, { name: 'PPTX', cls: 'fd-pptx' },
  { name: 'XLSX', cls: 'fd-xlsx' }, { name: 'EPUB', cls: 'fd-epub' },
  { name: 'HTML', cls: 'fd-html' }, { name: 'CSV', cls: 'fd-csv' },
  { name: 'TXT', cls: 'fd-txt' },
];

Page({
  data: { filePath: '', fileName: '', uploading: false, formats: FORMATS },

  chooseFile() {
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      extension: ['txt', 'md', 'pdf', 'docx', 'doc', 'pptx', 'xlsx', 'xls', 'epub', 'html', 'htm', 'csv'],
      success: (res) => {
        const f = res.tempFiles[0];
        if (f.size > 20 * 1024 * 1024) {
          wx.showToast({ title: '文件超过 20MB 限制', icon: 'none' });
          return;
        }
        this.setData({ filePath: f.path, fileName: f.name });
      },
    });
  },

  upload() {
    if (!this.data.filePath || this.data.uploading) return;
    this.setData({ uploading: true });
    wx.showLoading({ title: '上传中' });
    api.uploadFile('/api/docs/upload', this.data.filePath, 'file', { filename: this.data.fileName })
      .then((doc) => {
        wx.hideLoading();
        this.setData({ uploading: false, filePath: '', fileName: '' });
        wx.showToast({ title: '上传成功，处理中', icon: 'success' });
        setTimeout(() => wx.navigateBack(), 800);
      })
      .catch((e) => {
        wx.hideLoading();
        this.setData({ uploading: false });
        wx.showToast({ title: e.message, icon: 'none' });
      });
  },
});
