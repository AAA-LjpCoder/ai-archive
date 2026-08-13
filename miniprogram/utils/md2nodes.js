// utils/md2nodes.js — Markdown → rich-text nodes（AI 回答渲染）
const MarkdownIt = require('./markdown-it.min.js');

const md = new MarkdownIt({
  html: false,      // 防注入：AI 输出按纯文本处理
  linkify: true,
  breaks: true,     // 换行生效
  typographer: false,
});

// 标签 → 内联样式
const TAG_STYLE = {
  p: 'margin:8rpx 0;line-height:1.7;',
  strong: 'font-weight:bold;',
  b: 'font-weight:bold;',
  em: 'font-style:italic;',
  i: 'font-style:italic;',
  del: 'text-decoration:line-through;',
  code: 'font-family:Menlo,Consolas,monospace;background:#F3EFE9;padding:2rpx 8rpx;border-radius:6rpx;font-size:24rpx;white-space:pre-wrap;',
  pre: 'font-family:Menlo,Consolas,monospace;background:#F7F5F0;padding:20rpx;border-radius:12rpx;margin:12rpx 0;font-size:24rpx;line-height:1.6;white-space:pre-wrap;',
  a: 'color:#2383E2;text-decoration:underline;',
  blockquote: 'border-left:6rpx solid #C9BCA4;padding-left:20rpx;color:#8A8075;margin:12rpx 0;',
  h1: 'font-size:36rpx;font-weight:bold;margin:20rpx 0 10rpx;',
  h2: 'font-size:33rpx;font-weight:bold;margin:18rpx 0 10rpx;',
  h3: 'font-size:30rpx;font-weight:bold;margin:16rpx 0 8rpx;',
  h4: 'font-size:28rpx;font-weight:bold;margin:14rpx 0 8rpx;',
  h5: 'font-size:28rpx;font-weight:bold;margin:12rpx 0 6rpx;',
  h6: 'font-size:28rpx;font-weight:bold;margin:12rpx 0 6rpx;',
  hr: 'border:none;border-top:2rpx solid #EFEBE4;margin:16rpx 0;',
};

function decodeEntities(s) {
  return s
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&#(\d+);/g, (m, d) => String.fromCharCode(Number(d)));
}

function makeText(text) {
  return { type: 'text', text };
}

// 简单 HTML 解析器：html → rich-text nodes
function htmlToNodes(html) {
  const root = { children: [] };
  const stack = [root];
  const listStack = []; // {type: 'ul'|'ol', n}
  let i = 0;
  const len = html.length;

  const current = () => stack[stack.length - 1];
  const push = (node) => current().children.push(node);

  // 是否在代码块内（保留空白）
  let inPre = false;
  const isWhitespace = (s) => /^\s*$/.test(s);

  while (i < len) {
    const lt = html.indexOf('<', i);
    if (lt === -1) {
      const tail = html.slice(i);
      if (tail && (inPre || !isWhitespace(tail))) push(makeText(decodeEntities(tail)));
      break;
    }
    if (lt > i) {
      const seg = html.slice(i, lt);
      if (seg && (inPre || !isWhitespace(seg))) push(makeText(decodeEntities(seg)));
    }
    const gt = html.indexOf('>', lt);
    if (gt === -1) break;
    const tagStr = html.slice(lt + 1, gt);
    i = gt + 1;

    // 注释
    if (tagStr.startsWith('!--')) {
      const end = html.indexOf('-->', i);
      i = end === -1 ? len : end + 3;
      continue;
    }

    // 闭合标签
    if (tagStr.startsWith('/')) {
      const name = tagStr.slice(1).trim().toLowerCase();
      if (name === 'pre') inPre = false;
      if (stack.length > 1) {
        stack.pop();
        if (name === 'ul' || name === 'ol' || name === 'li') listStack.pop();
      }
      continue;
    }

    const selfClose = tagStr.endsWith('/');
    const tagName = tagStr.split(/[\s/]/)[0].toLowerCase();
    if (selfClose || tagName === 'br' || tagName === 'img' || tagName === 'hr') {
      if (tagName === 'br') push({ name: 'br', attrs: {}, children: [] });
      if (tagName === 'hr') push({ name: 'div', attrs: { style: TAG_STYLE.hr }, children: [] });
      continue;
    }

    // 列表：ul/ol 计数，li 转缩进文本块（rich-text 不支持原生列表符号）
    if (tagName === 'ul' || tagName === 'ol') {
      listStack.push({ type: tagName, n: 0 });
      continue;
    }
    if (tagName === 'li') {
      const list = listStack[listStack.length - 1];
      if (list) list.n += 1;
      const prefix = list && list.type === 'ol' ? `${list.n}. ` : '• ';
      const liNode = {
        name: 'div',
        attrs: { style: 'margin:6rpx 0;padding-left:28rpx;text-indent:-28rpx;line-height:1.7;' },
        children: [makeText(prefix)],
      };
      push(liNode);
      stack.push(liNode);
      listStack.push({ type: 'li-tmp', n: 0 });
      continue;
    }

    // 普通标签
    const styleMatch = tagStr.match(/style=["']([^"']*)["']/);
    let style = TAG_STYLE[tagName] || '';
    if (styleMatch) style += styleMatch[1];
    if (tagName === 'pre') inPre = true;

    const node = { name: tagName, attrs: {}, children: [] };
    if (style) node.attrs.style = style;
    push(node);
    stack.push(node);
  }
  return root.children;
}

// 入口：markdown 文本 → nodes 数组
function mdToNodes(src) {
  if (!src) return [];
  const html = md.render(src);
  return htmlToNodes(html);
}

module.exports = { mdToNodes };
