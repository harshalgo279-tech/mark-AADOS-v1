// frontend/src/utils/sanitize.js
/**
 * HTML Sanitization utility to prevent XSS attacks.
 *
 * Uses a whitelist approach to allow only safe HTML tags and attributes.
 */

// Allowed HTML tags for email content
const ALLOWED_TAGS = new Set([
  'a', 'abbr', 'b', 'blockquote', 'br', 'code',
  'div', 'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr',
  'i', 'img', 'li', 'ol', 'p', 'pre', 'span', 'strong',
  'table', 'tbody', 'td', 'th', 'thead', 'tr', 'u', 'ul',
]);

// Allowed attributes by tag
const ALLOWED_ATTRIBUTES = {
  '*': ['class', 'style', 'id'],
  'a': ['href', 'title', 'target', 'rel'],
  'img': ['src', 'alt', 'title', 'width', 'height'],
  'table': ['border', 'cellpadding', 'cellspacing', 'width'],
  'td': ['colspan', 'rowspan', 'align', 'valign', 'width'],
  'th': ['colspan', 'rowspan', 'align', 'valign', 'width'],
};

// Allowed URL protocols
const ALLOWED_PROTOCOLS = ['http:', 'https:', 'mailto:', 'tel:'];

/**
 * Sanitize an HTML string to prevent XSS attacks.
 *
 * @param {string} html - The HTML string to sanitize
 * @returns {string} - Sanitized HTML string
 */
export function sanitizeHtml(html) {
  if (!html || typeof html !== 'string') {
    return '';
  }

  // Create a temporary DOM element to parse HTML
  const template = document.createElement('template');
  template.innerHTML = html;

  // Recursively sanitize all nodes
  sanitizeNode(template.content);

  return template.innerHTML;
}

/**
 * Recursively sanitize a DOM node and its children.
 */
function sanitizeNode(node) {
  // Get all child nodes (convert to array since we'll be modifying)
  const children = Array.from(node.childNodes);

  for (const child of children) {
    if (child.nodeType === Node.ELEMENT_NODE) {
      const tagName = child.tagName.toLowerCase();

      // Check if tag is allowed
      if (!ALLOWED_TAGS.has(tagName)) {
        // Replace element with its text content
        const textNode = document.createTextNode(child.textContent || '');
        node.replaceChild(textNode, child);
        continue;
      }

      // Sanitize attributes
      sanitizeAttributes(child, tagName);

      // Recursively sanitize children
      sanitizeNode(child);
    } else if (child.nodeType === Node.COMMENT_NODE) {
      // Remove comments
      node.removeChild(child);
    }
  }
}

/**
 * Sanitize attributes on an element.
 */
function sanitizeAttributes(element, tagName) {
  const attributes = Array.from(element.attributes);
  const allowedForTag = ALLOWED_ATTRIBUTES[tagName] || [];
  const allowedForAll = ALLOWED_ATTRIBUTES['*'] || [];

  for (const attr of attributes) {
    const attrName = attr.name.toLowerCase();

    // Check if attribute is allowed
    if (!allowedForTag.includes(attrName) && !allowedForAll.includes(attrName)) {
      element.removeAttribute(attr.name);
      continue;
    }

    // Special handling for href/src attributes
    if (attrName === 'href' || attrName === 'src') {
      if (!isAllowedUrl(attr.value)) {
        element.removeAttribute(attr.name);
        continue;
      }
    }

    // Special handling for style attribute - remove dangerous CSS
    if (attrName === 'style') {
      element.setAttribute('style', sanitizeStyle(attr.value));
    }

    // Force target="_blank" links to have rel="noopener noreferrer"
    if (tagName === 'a' && attrName === 'target' && attr.value === '_blank') {
      element.setAttribute('rel', 'noopener noreferrer');
    }
  }
}

/**
 * Check if a URL is using an allowed protocol.
 */
function isAllowedUrl(url) {
  if (!url) return false;

  try {
    const parsed = new URL(url, window.location.origin);
    return ALLOWED_PROTOCOLS.includes(parsed.protocol);
  } catch {
    // Relative URLs are allowed
    return !url.toLowerCase().startsWith('javascript:');
  }
}

/**
 * Sanitize CSS style string to remove dangerous properties.
 */
function sanitizeStyle(style) {
  if (!style) return '';

  // Dangerous CSS patterns
  const dangerousPatterns = [
    /expression\s*\(/gi,
    /javascript\s*:/gi,
    /behavior\s*:/gi,
    /-moz-binding/gi,
    /url\s*\([^)]*javascript/gi,
  ];

  let sanitized = style;
  for (const pattern of dangerousPatterns) {
    sanitized = sanitized.replace(pattern, '');
  }

  return sanitized;
}

export default sanitizeHtml;
