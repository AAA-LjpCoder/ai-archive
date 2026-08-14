// pages/docs/detail.js — 文档详情
const api = require('../../utils/api');

const TYPE_CLASS = {
  md: 'tag-type-md', markdown: 'tag-type-md', pdf: 'tag-type-pdf',
  docx: 'tag-type-docx', doc: 'tag-type-docx', txt: 'tag-type-txt',
  pptx: 'tag-type-pptx', xlsx: 'tag-type-xlsx', xls: 'tag-type-xlsx',
  epub: 'tag-type-epub', html: 'tag-type-html', htm: 'tag-type-html',
  csv: 'tag-type-csv',
};
const TYPE_ICON = {
  md: { cls: 'icon-md', label: 'MD' }, markdown: { cls: 'icon-md', label: 'MD' },
  pdf: { cls: 'icon-pdf', label: 'PDF' },
  docx: { cls: 'icon-docx', label: 'DOC' }, doc: { cls: 'icon-docx', label: 'DOC' },
  txt: { cls: 'icon-txt', label: 'TXT' },
  pptx: { cls: 'icon-pptx', label: 'PPT' },
  xlsx: { cls: 'icon-xlsx', label: 'XLS' }, xls: { cls: 'icon-xlsx', label: 'XLS' },
  epub: { cls: 'icon-epub', label: 'EPUB' },
  html: { cls: 'icon-html', label: 'HTML' }, htm: { cls: 'icon-html', label: 'HTML' },
  csv: { cls: 'icon-csv', label: 'CSV' },
};

Page({
  data: { doc: null, chunks: [] },

  onLoad(options) {
    this.docId = Number(options.id);
    this.load();
  },

  async load() {
    try {
      const [doc, chunks] = await Promise.all([
        api.request(`/api/docs/${this.docId}`),
        api.request(`/api/docs/${this.docId}/chunks?limit=30`),
      ]);
      const icon = TYPE_ICON[doc.type] || { cls: 'icon-txt', label: doc.type.toUpperCase().slice(0, 3) };
      this.setData({
        doc: {
          ...doc,
          size_kb: (doc.size / 1024).toFixed(0),
          type_class: TYPE_CLASS[doc.type] || 'tag-type-txt',
          type_icon_cls: icon.cls,
          type_icon_label: icon.label,
        },
        chunks,
      });
    } catch (e) {
      wx.showToast({ title: e.message, icon: 'none' });
    }
  },

  askThisDoc() {
    if (!this.data.doc || this.data.doc.status !== 'ready') {
      wx.showToast({ title: '文档处理完成后才能提问', icon: 'none' });
      return;
    }
    wx.showLoading({ title: '创建会话' });
    api.request('/api/conversations', 'POST', { mode: 'doc', doc_id: this.docId })
      .then((conv) => {
        wx.hideLoading();
        wx.navigateTo({ url: `/pages/chat/detail?id=${conv.id}&mode=doc` });
      })
      .catch((e) => {
        wx.hideLoading();
        wx.showToast({ title: e.message, icon: 'none' });
      });
  },

  deleteDoc() {
    wx.showModal({
      title: '删除文档',
      content: `确认删除「${this.data.doc.name}」？`,
      success: (res) => {
        if (!res.confirm) return;
        api.request(`/api/docs/${this.docId}`, 'DELETE')
          .then(() => {
            wx.showToast({ title: '已删除', icon: 'success' });
            setTimeout(() => wx.navigateBack(), 600);
          })
          .catch((e) => wx.showToast({ title: e.message, icon: 'none' }));
      },
    });
  },

  statusText(status) {
    return { pending: '排队中', processing: '解析中', ready: '就绪', failed: '失败' }[status] || status;
  },
});
