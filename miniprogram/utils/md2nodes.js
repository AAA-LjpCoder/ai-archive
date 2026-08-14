// utils/md2nodes.js — Markdown → rich-text nodes（AI 回答渲染 V2）
// 增强：代码语法高亮（深色主题）、表格转 div 网格、金色引用块、任务列表
const MarkdownIt = require('./markdown-it.min.js');

const md = new MarkdownIt({
  html: false,      // 防注入：AI 输出按纯文本处理
  linkify: true,
  breaks: true,     // 换行生效
  typographer: false,
});

// 标签 → 内联样式
const TAG_STYLE = {
  p: 'margin:10rpx 0;line-height:1.75;',
  strong: 'font-weight:bold;color:#146B5A;',
  b: 'font-weight:bold;color:#146B5A;',
  em: 'font-style:italic;',
  i: 'font-style:italic;',
  del: 'text-decoration:line-through;color:#9B9488;',
  code: 'font-family:Menlo,Consolas,monospace;background:#E3EFEA;color:#0F5B4C;padding:2rpx 8rpx;border-radius:6rpx;font-size:24rpx;white-space:pre-wrap;',
  a: 'color:#2383E2;text-decoration:underline;',
  blockquote: 'border-left:6rpx solid #B7791F;background:#FBF6EC;padding:16rpx 20rpx;color:#7A7266;margin:14rpx 0;border-radius:0 12rpx 12rpx 0;',
  h1: 'font-size:36rpx;font-weight:bold;margin:24rpx 0 10rpx;color:#146B5A;',
  h2: 'font-size:33rpx;font-weight:bold;margin:20rpx 0 10rpx;color:#146B5A;',
  h3: 'font-size:30rpx;font-weight:bold;margin:16rpx 0 8rpx;color:#2D2A26;',
  h4: 'font-size:28rpx;font-weight:bold;margin:14rpx 0 8rpx;color:#2D2A26;',
  h5: 'font-size:28rpx;font-weight:bold;margin:12rpx 0 6rpx;',
  h6: 'font-size:28rpx;font-weight:bold;margin:12rpx 0 6rpx;',
  hr: 'border:none;border-top:2rpx solid #E5DFD2;margin:20rpx 0;',
};

// 代码块深色主题
const CODE_BG = '#26302D';
const CODE_DEFAULT = '#E8E6E1';
const CODE_KEYWORD = '#7FD1AE';
const CODE_STRING = '#E8B87A';
const CODE_COMMENT = '#7D8A85';
const CODE_NUMBER = '#B8A6F0';

// 表格网格样式
const TABLE_STYLE = 'display:flex;flex-direction:column;border:1rpx solid #E5DFD2;border-radius:14rpx;overflow:hidden;margin:14rpx 0;';
const TR_STYLE = 'display:flex;';
const TH_STYLE = 'flex:1;min-width:0;padding:12rpx 16rpx;font-weight:600;background:#E3EFEA;color:#0F5B4C;font-size:24rpx;word-break:break-all;border-bottom:1rpx solid #E5DFD2;';
const TD_STYLE = 'flex:1;min-width:0;padding:12rpx 16rpx;font-size:24rpx;word-break:break-all;border-bottom:1rpx solid #F0EBE1;';

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

// 代码语法高亮 → token 列表 [{text, cls}]
function highlightCode(code) {
  const tokens = [];
  const re = /(\/\/[^\n]*|#[^\n]*|\/\*[\s\S]*?\*\/|"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`[^`]*`|\b(?:def|class|if|elif|else|return|import|from|for|while|function|const|let|var|async|await|try|except|finally|with|as|in|not|and|or|lambda|pass|break|continue|None|True|False|print|self|new|export|default)\b|\b\d+(?:\.\d+)?\b)/g;
  let last = 0;
  let m;
  while ((m = re.exec(code))) {
    if (m.index > last) tokens.push({ text: code.slice(last, m.index), cls: 'pl' });
    const t = m[0];
    let cls = 'kw';
    if (t.startsWith('//') || t.startsWith('#') || t.startsWith('/*')) cls = 'cm';
    else if (t.startsWith('"') || t.startsWith("'") || t.startsWith('`')) cls = 'st';
    else if (/^\d/.test(t)) cls = 'nu';
    tokens.push({ text: t, cls });
    last = m.index + t.length;
  }
  if (last < code.length) tokens.push({ text: code.slice(last), cls: 'pl' });
  return tokens;
}

const CODE_COLOR = { pl: CODE_DEFAULT, kw: CODE_KEYWORD, st: CODE_STRING, cm: CODE_COMMENT, nu: CODE_NUMBER };

// 简单 HTML 解析器：html → rich-text nodes
function htmlToNodes(html) {
  const root = { children: [] };
  const stack = [root];
  const listStack = []; // {type: 'ul'|'ol', n}
  let i = 0;
  const len = html.length;

  const current = () => stack[stack.length - 1];
  const push = (node) => current().children.push(node);

  let inPre = false;
  let codeBuf = '';
  const isWhitespace = (s) => /^\s*$/.test(s);

  while (i < len) {
    const lt = html.indexOf('<', i);
    if (lt === -1) {
      const tail = html.slice(i);
      if (inPre) codeBuf += decodeEntities(tail);
      else if (tail && !isWhitespace(tail)) push(makeText(decodeEntities(tail)));
      break;
    }
    if (lt > i) {
      const seg = html.slice(i, lt);
      if (inPre) codeBuf += decodeEntities(seg);
      else if (seg && !isWhitespace(seg)) push(makeText(decodeEntities(seg)));
    }
    const gt = html.indexOf('>', lt);
    if (gt === -1) break;
    const tagStr = html.slice(lt + 1, gt);
    i = gt + 1;

    if (tagStr.startsWith('!--')) {
      const end = html.indexOf('-->', i);
      i = end === -1 ? len : end + 3;
      continue;
    }

    // 闭合标签
    if (tagStr.startsWith('/')) {
      const name = tagStr.slice(1).trim().toLowerCase();
      if (name === 'pre') {
        inPre = false;
        // 代码块：深色背景 + 语法高亮
        const tokens = highlightCode(codeBuf);
        const children = [];
        for (const t of tokens) {
          children.push(t.cls === 'pl'
            ? makeText(t.text)
            : { name: 'text', attrs: { style: `color:${CODE_COLOR[t.cls]};` }, children: [makeText(t.text)] });
        }
        const preNode = {
          name: 'div',
          attrs: { style: `font-family:Menlo,Consolas,monospace;background:${CODE_BG};color:${CODE_DEFAULT};padding:22rpx 24rpx;border-radius:14rpx;margin:14rpx 0;font-size:24rpx;line-height:1.7;white-space:pre-wrap;word-break:break-all;` },
          children,
        };
        push(preNode);
        codeBuf = '';
        continue;
      }
      if (inPre && name === 'code') continue; // 代码块内 <code> 闭合跳过
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

    // 代码块入口（不占位，内容累积到 codeBuf，闭合时再生成节点）
    if (tagName === 'pre') {
      inPre = true;
      codeBuf = '';
      continue;
    }
    if (inPre && tagName === 'code') continue; // 内容直接进 codeBuf

    // 表格 → div 网格（rich-text 对 table 支持差）
    if (tagName === 'table') {
      const node = { name: 'div', attrs: { style: TABLE_STYLE }, children: [] };
      push(node);
      stack.push(node);
      continue;
    }
    if (tagName === 'thead' || tagName === 'tbody' || tagName === 'tfoot') continue; // 扁平化
    if (tagName === 'tr') {
      const node = { name: 'div', attrs: { style: TR_STYLE }, children: [] };
      push(node);
      stack.push(node);
      continue;
    }
    if (tagName === 'th' || tagName === 'td') {
      const node = { name: 'div', attrs: { style: tagName === 'th' ? TH_STYLE : TD_STYLE }, children: [] };
      push(node);
      stack.push(node);
      continue;
    }

    // 列表：ul/ol 计数，li 转缩进文本块
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
        attrs: { style: 'margin:6rpx 0;padding-left:28rpx;text-indent:-28rpx;line-height:1.75;' },
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
