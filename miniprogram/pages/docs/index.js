// pages/docs/index.js — 文档库
const api = require('../../utils/api');

const TYPE_CLASS = {
  md: 'tag-type-md', markdown: 'tag-type-md', pdf: 'tag-type-pdf',
  docx: 'tag-type-docx', doc: 'tag-type-docx', txt: 'tag-type-txt',
  pptx: 'tag-type-pptx', xlsx: 'tag-type-xlsx', xls: 'tag-type-xlsx',
  epub: 'tag-type-epub', html: 'tag-type-html', htm: 'tag-type-html',
  csv: 'tag-type-csv',
  jpg: 'tag-type-img', jpeg: 'tag-type-img', png: 'tag-type-img',
  webp: 'tag-type-img', bmp: 'tag-type-img', gif: 'tag-type-img',
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
  jpg: { cls: 'icon-img', label: 'IMG' }, jpeg: { cls: 'icon-img', label: 'IMG' },
  png: { cls: 'icon-img', label: 'IMG' }, webp: { cls: 'icon-img', label: 'IMG' },
  bmp: { cls: 'icon-img', label: 'IMG' }, gif: { cls: 'icon-img', label: 'IMG' },
};

Page({
  data: { docs: [], loading: true, totalChunks: 0 },

  onShow() { this.load(); },

  async load() {
    try {
      const docs = await api.request('/api/docs');
      const mapped = docs.map((d) => {
        const icon = TYPE_ICON[d.type] || { cls: 'icon-txt', label: d.type.toUpperCase().slice(0, 3) };
        return {
          ...d,
          size_kb: (d.size / 1024).toFixed(0),
          type_class: TYPE_CLASS[d.type] || 'tag-type-txt',
          type_icon_cls: icon.cls,
          type_icon_label: icon.label,
          anim_delay: (docs.indexOf(d) * 60) + 'ms',
        };
      });
      this.setData({
        docs: mapped,
        totalChunks: mapped.reduce((s, d) => s + (d.chunk_count || 0), 0),
        loading: false,
      });
    } catch (e) {
      this.setData({ loading: false });
      wx.showToast({ title: e.message, icon: 'none' });
    }
  },

  goUpload() { wx.navigateTo({ url: '/pages/docs/upload' }); },
  goDetail(e) { wx.navigateTo({ url: `/pages/docs/detail?id=${e.currentTarget.dataset.id}` }); },

  deleteDoc(id, name) {
    wx.showModal({
      title: '删除文档',
      content: `确认删除「${name}」？向量数据将一并清除。`,
      success: (res) => {
        if (!res.confirm) return;
        api.request(`/api/docs/${id}`, 'DELETE')
          .then(() => {
            wx.showToast({ title: '已删除', icon: 'success' });
            this.load();
          })
          .catch((err) => wx.showToast({ title: err.message, icon: 'none' }));
      },
    });
  },

  // 卡片右侧操作菜单（重命名/删除）
  openOps(e) {
    const { id, name } = e.currentTarget.dataset;
    wx.showActionSheet({
      itemList: ['重命名', '删除'],
      success: (res) => {
        if (res.tapIndex === 0) this.renameDoc(id, name);
        else if (res.tapIndex === 1) this.deleteDoc(id, name);
      },
    });
  },

  renameDoc(id, oldName) {
    wx.showModal({
      title: '重命名文档',
      editable: true,
      placeholderText: oldName,
      success: (res) => {
        if (!res.confirm) return;
        const name = (res.content || '').trim();
        if (!name) {
          wx.showToast({ title: '名称不能为空', icon: 'none' });
          return;
        }
        api.request(`/api/docs/${id}`, 'PATCH', { name })
          .then(() => {
            wx.showToast({ title: '已重命名', icon: 'success' });
            this.load();
          })
          .catch((err) => wx.showToast({ title: err.message, icon: 'none' }));
      },
    });
  },

  statusText(status) {
    return { pending: '排队中', processing: '解析中', ready: '就绪', failed: '失败' }[status] || status;
  },
});
