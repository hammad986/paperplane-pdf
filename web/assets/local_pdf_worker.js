importScripts('/assets/pdf-lib.min.js');

const { PDFDocument, StandardFonts, degrees, rgb } = self.PDFLib;

function pageIndices(input, count) {
  const indices = [];
  for (const part of input.split(',')) {
    const match = /^(\d+)(?:\s*-\s*(\d+))?$/.exec(part.trim());
    if (!match) throw new Error('Enter valid page numbers or ranges.');
    const first = Number(match[1]);
    const last = Number(match[2] || match[1]);
    if (first < 1 || last < first || last > count) throw new Error('A page or range is outside this PDF.');
    for (let index = first - 1; index < last; index++) indices.push(index);
    if (indices.length > count) throw new Error('Choose each page at most once.');
  }
  if (new Set(indices).size !== indices.length) throw new Error('Choose each page at most once.');
  return indices;
}

async function copyPages(document, indices) {
  if (!indices.length) throw new Error('The result must contain at least one page.');
  const result = await PDFDocument.create();
  const pages = await result.copyPages(document, indices);
  pages.forEach(page => result.addPage(page));
  return result.save();
}

// PDF streams are already compressed. ZIP store mode avoids recompressing
// every file and keeps the result readable by standard ZIP tools.
function zipPages(files) {
  const encoder = new TextEncoder();
  const crcTable = Uint32Array.from({ length: 256 }, (_, byte) => {
    let crc = byte;
    for (let step = 0; step < 8; step++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
    return crc;
  });
  const content = [];
  const central = [];
  let offset = 0;
  let directorySize = 0;
  for (const [index, data] of files.entries()) {
    const name = encoder.encode('page-' + (index + 1) + '.pdf');
    let crc = 0xffffffff;
    for (const byte of data) crc = (crc >>> 8) ^ crcTable[(crc ^ byte) & 255];
    crc ^= 0xffffffff;
    const header = new DataView(new ArrayBuffer(30));
    const directory = new DataView(new ArrayBuffer(46));
    header.setUint32(0, 0x04034b50, true);
    directory.setUint32(0, 0x02014b50, true);
    header.setUint16(4, 20, true);
    directory.setUint16(4, 20, true);
    directory.setUint16(6, 20, true);
    header.setUint16(12, 33, true);
    directory.setUint16(14, 33, true);
    header.setUint32(14, crc, true);
    directory.setUint32(16, crc, true);
    header.setUint32(18, data.length, true);
    header.setUint32(22, data.length, true);
    directory.setUint32(20, data.length, true);
    directory.setUint32(24, data.length, true);
    header.setUint16(26, name.length, true);
    directory.setUint16(28, name.length, true);
    directory.setUint32(42, offset, true);
    content.push(header.buffer, name, data);
    central.push(directory.buffer, name);
    offset += 30 + name.length + data.length;
    directorySize += 46 + name.length;
  }
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true);
  end.setUint16(8, files.length, true);
  end.setUint16(10, files.length, true);
  end.setUint32(12, directorySize, true);
  end.setUint32(16, offset, true);
  return new Blob([...content, ...central, end.buffer], { type: 'application/zip' });
}

async function transform({ operation, files, options }) {
  if (operation === 'merge') {
    const result = await PDFDocument.create();
    for (const bytes of files) {
      const source = await PDFDocument.load(bytes);
      const pages = await result.copyPages(source, source.getPageIndices());
      pages.forEach(page => result.addPage(page));
    }
    return { filename: 'merged-PDF.pdf', output: await result.save() };
  }

  const pdf = await PDFDocument.load(files[0]);
  const count = pdf.getPageCount();
  if (operation === 'metadata') {
    for (const [key, setter] of Object.entries({title: 'setTitle', author: 'setAuthor', subject: 'setSubject'})) {
      if (Object.prototype.hasOwnProperty.call(options, key)) pdf[setter](String(options[key] || ''));
    }
    const dateString = date => date instanceof Date && Number.isFinite(date.getTime()) ? date.toISOString() : '';
    const output_metadata = {
      title: pdf.getTitle() || '', author: pdf.getAuthor() || '', subject: pdf.getSubject() || '',
      keywords: pdf.getKeywords() || '', creator: pdf.getCreator() || '', producer: pdf.getProducer() || '',
      creation_date: dateString(pdf.getCreationDate()), modification_date: dateString(pdf.getModificationDate()),
      page_count: count,
    };
    return { filename: 'metadata-updated.pdf', output: await pdf.save(), output_metadata };
  }
  if (operation === 'forms') {
    let fields = options.fields;
    if (typeof fields === 'string') {
      try { fields = JSON.parse(fields); }
      catch { throw new Error('Provide form fields as a valid JSON object.'); }
    }
    if (!fields || typeof fields !== 'object' || Array.isArray(fields) || !Object.keys(fields).length) {
      throw new Error('Provide at least one form field as a valid JSON object.');
    }
    const form = pdf.getForm();
    for (const [name, rawValue] of Object.entries(fields)) {
      const field = form.getField(name);
      const value = rawValue == null ? '' : String(rawValue);
      if (field instanceof PDFLib.PDFTextField) field.setText(value);
      else if (field instanceof PDFLib.PDFCheckBox) {
        const checked = rawValue === true || rawValue === 1 || ['true', 'yes', 'on', '1'].includes(value.toLowerCase());
        if (checked) field.check(); else field.uncheck();
      } else if (field instanceof PDFLib.PDFDropdown || field instanceof PDFLib.PDFRadioGroup) {
        field.select(value);
      } else if (field instanceof PDFLib.PDFOptionList) {
        field.select(Array.isArray(rawValue) ? rawValue.map(String) : value);
      } else {
        throw new Error(`The field “${name}” uses a type that browser processing cannot fill. Choose Server Processing.`);
      }
    }
    return { filename: 'filled-forms.pdf', output: await pdf.save() };
  }
  if (operation === 'flatten') {
    const form = pdf.getForm();
    form.flatten();
    return { filename: 'flattened.pdf', output: await pdf.save() };
  }
  if (operation === 'rotate') {
    pdf.getPages().forEach(page => page.setRotation(degrees(page.getRotation().angle + options.degrees)));
    return { filename: 'rotated.pdf', output: await pdf.save() };
  }
  if (operation === 'page_numbers') {
    if (!count) throw new Error('This PDF has no pages to number.');
    const firstPage = Math.max(1, Math.min(count, Number(options.startPage) || 1));
    const firstNumber = Math.max(1, Number(options.startNumber) || 1);
    const format = ['Page {n} of {total}', 'Page {n}', '{n}'].includes(options.format)
      ? options.format : 'Page {n} of {total}';
    const match = /^#?([0-9a-f]{6})$/i.exec(String(options.markColor || '#243b53'));
    const hex = match ? match[1] : '243b53';
    const color = rgb(parseInt(hex.slice(0, 2), 16) / 255,
      parseInt(hex.slice(2, 4), 16) / 255, parseInt(hex.slice(4, 6), 16) / 255);
    const outline = options.markBackground === 'dark' ? rgb(1, 1, 1) : rgb(0, 0, 0);
    const font = await pdf.embedFont(StandardFonts.Helvetica);
    const parts = String(options.position || 'Footer center').split(' ');
    const vertical = parts[0] === 'Header' ? 'header' : 'footer';
    const horizontal = ['left', 'right'].includes((parts[1] || '').toLowerCase()) ? parts[1].toLowerCase() : 'center';
    for (let index = firstPage - 1; index < count; index++) {
      const number = firstNumber + index - firstPage + 1;
      const label = format.replace('{n}', String(number)).replace('{total}', String(firstNumber + count - firstPage));
      const page = pdf.getPage(index);
      const box = page.getCropBox();
      const angle = ((page.getRotation().angle % 360) + 360) % 360;
      const width = angle === 90 || angle === 270 ? box.height : box.width;
      const height = angle === 90 || angle === 270 ? box.width : box.height;
      const size = 10;
      const margin = 24;
      const textWidth = font.widthOfTextAtSize(label, size);
      const x = horizontal === 'left' ? margin : horizontal === 'right' ? Math.max(margin, width - margin - textWidth) : Math.max(0, (width - textWidth) / 2);
      const y = vertical === 'header' ? height - margin - size : margin;
      const point = angle === 90 ? [box.x + box.width - y, box.y + x]
        : angle === 180 ? [box.x + box.width - x, box.y + box.height - y]
        : angle === 270 ? [box.x + y, box.y + box.height - x]
        : [box.x + x, box.y + y];
      const fontKey = page.node.newFontDictionary(font.name, font.ref);
      const rad = angle * Math.PI / 180;
      const { pushGraphicsState, popGraphicsState, setFillingColor, setStrokingColor,
        setLineWidth, beginText, endText, setFontAndSize, setTextMatrix, showText,
        setTextRenderingMode, TextRenderingMode } = self.PDFLib;
      page.pushOperators(pushGraphicsState(), setFillingColor(color), setStrokingColor(outline),
        setLineWidth(1), beginText(), setFontAndSize(fontKey, size),
        setTextRenderingMode(TextRenderingMode.FillAndOutline),
        setTextMatrix(Math.cos(rad), Math.sin(rad), -Math.sin(rad), Math.cos(rad), ...point),
        showText(font.encodeText(label)), endText(), popGraphicsState());
    }
    return { filename: 'page-numbered.pdf', output: await pdf.save() };
  }
  if (operation === 'crop') {
    const margins = Object.fromEntries(['left', 'top', 'right', 'bottom'].map(side => {
      const margin = Number(options[side] || 0);
      if (!Number.isFinite(margin) || margin < 0) throw new Error('Crop margins must be zero or a positive number.');
      return [side, margin];
    }));
    for (const page of pdf.getPages()) {
      const box = page.getCropBox();
      // Margins are entered relative to the displayed page, while CropBox
      // coordinates use the unrotated PDF axes.
      const rotation = ((page.getRotation().angle % 360) + 360) % 360;
      const mapped = rotation === 90 ? {left: margins.top, right: margins.bottom, top: margins.right, bottom: margins.left}
        : rotation === 180 ? {left: margins.right, right: margins.left, top: margins.bottom, bottom: margins.top}
        : rotation === 270 ? {left: margins.bottom, right: margins.top, top: margins.left, bottom: margins.right}
        : margins;
      const width = box.width - mapped.left - mapped.right;
      const height = box.height - mapped.top - mapped.bottom;
      if (width <= 0 || height <= 0) throw new Error('Crop margins must leave a visible area on every page.');
      page.setCropBox(box.x + mapped.left, box.y + mapped.bottom, width, height);
    }
    return { filename: 'cropped.pdf', output: await pdf.save() };
  }
  if (operation === 'split' && options.splitMode === 'all_pages') {
    if (count > 1000) throw new Error('For a ZIP over 1,000 pages, choose Server Processing.');
    const pages = [];
    for (let index = 0; index < count; index++) pages.push(await copyPages(pdf, [index]));
    return { filename: 'split-pages.zip', output: zipPages(pages) };
  }
  const selected = pageIndices(options.pages, count);
  if (operation === 'remove') {
    const removed = new Set(selected);
    const kept = pdf.getPageIndices().filter(index => !removed.has(index));
    return { filename: 'removed-pages.pdf', output: await copyPages(pdf, kept) };
  }
  if (operation === 'organize' && selected.length !== count) throw new Error('Enter each page exactly once to set the order.');
  return {
    filename: operation === 'organize' ? 'organized.pdf' : 'extracted-pages.pdf',
    output: await copyPages(pdf, selected),
  };
}

self.onmessage = async event => {
  try {
    const result = await transform(event.data);
    self.postMessage(result, result.output instanceof Uint8Array ? [result.output.buffer] : []);
  } catch (error) {
    const message = /encrypted/i.test(error.message || '')
      ? 'This PDF needs a password. Choose Server Processing and enter the password, or unlock the PDF first.'
      : (error.message || 'Browser PDF processing failed.');
    self.postMessage({ error: message });
  }
};
