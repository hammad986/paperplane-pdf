importScripts('/assets/pdf-lib.min.js');

const { PDFDocument, PDFName, PDFString, PDFNumber, StandardFonts, degrees, rgb } = self.PDFLib;

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

function copyDocMetadata(source, target) {
  try {
    const normalize = value => {
      const text = String(value || '').trim();
      return text && text.toLowerCase() !== 'untitled' ? text : '';
    };
    const title = normalize(source.getTitle());
    const author = normalize(source.getAuthor());
    const subject = normalize(source.getSubject());
    const keywords = normalize(source.getKeywords());
    const creator = normalize(source.getCreator());
    const creationDate = source.getCreationDate?.();
    if (title) target.setTitle(title);
    if (author) target.setAuthor(author);
    if (subject) target.setSubject(subject);
    if (keywords) target.setKeywords(keywords.split(',').map(k => k.trim()).filter(Boolean));
    if (creator) target.setCreator(creator);
    if (creationDate instanceof Date && Number.isFinite(creationDate.getTime())) {
      target.setCreationDate(creationDate);
    }
  } catch { /* metadata fields may be absent */ }
}

async function copyPages(document, indices) {
  if (!indices.length) throw new Error('The result must contain at least one page.');
  const result = await PDFDocument.create();
  copyDocMetadata(document, result);
  const pages = await result.copyPages(document, indices);
  pages.forEach(page => result.addPage(page));
  return result.save({ updateMetadata: false });
}

// PDF streams are already compressed. ZIP store mode avoids recompressing
// every file and keeps the result readable by standard ZIP tools.
function zipPages(files, extension = 'pdf', pageNumbers = null) {
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
    const pageNumber = Array.isArray(pageNumbers) ? pageNumbers[index] : index + 1;
    const name = encoder.encode(extension === 'jpg'
      ? `page_${String(pageNumber).padStart(3, '0')}.jpg`
      : `page-${index + 1}.pdf`);
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
  if (operation === 'annotate') {
    const annotations = options?.annotations;
    if (!files.length || files[0].byteLength > 50 * 1024 * 1024 || !Array.isArray(annotations) || !annotations.length || annotations.length > 500) {
      throw new Error('The browser received an invalid or oversized annotation request. Choose Server Processing.');
    }
    const pdf = await PDFDocument.load(files[0]);
    for (const item of annotations) {
      const pageIndex = Number(item.page);
      const rect = Array.isArray(item.rect) ? item.rect.map(Number) : [];
      const subtype = { highlight: 'Highlight', underline: 'Underline', strikeout: 'StrikeOut' }[item.type];
      if (!subtype || !Number.isInteger(pageIndex) || pageIndex < 0 || pageIndex >= pdf.getPageCount()
          || rect.length !== 4 || !rect.every(Number.isFinite) || rect[2] <= rect[0] || rect[3] <= rect[1]) {
        throw new Error('The browser received invalid annotation geometry. Choose Server Processing.');
      }
      const page = pdf.getPage(pageIndex);
      const pageSize = page.getSize();
      const [x1, y1, x2, y2] = rect;
      if (x1 < 0 || y1 < 0 || x2 > pageSize.width || y2 > pageSize.height) {
        throw new Error('The selected text falls outside the PDF page bounds. Choose Server Processing.');
      }
      const context = pdf.context;
      const annotation = context.obj({
        Type: PDFName.of('Annot'), Subtype: PDFName.of(subtype),
        Rect: context.obj(rect), F: PDFNumber.of(4),
      });
      annotation.set(PDFName.of('C'), context.obj([1, 0.8, 0]));
      annotation.set(PDFName.of('CA'), PDFNumber.of(item.type === 'highlight' ? 0.35 : 1));
      annotation.set(PDFName.of('Contents'), PDFString.of(String(item.text || '').slice(0, 2000)));
      annotation.set(PDFName.of('T'), PDFString.of('Paperplane'));
      annotation.set(PDFName.of('P'), page.ref);
      annotation.set(PDFName.of('QuadPoints'), context.obj([x1, y2, x2, y2, x1, y1, x2, y1]));
      page.node.addAnnot(context.register(annotation));
    }
    return { filename: 'annotated.pdf', output: await pdf.save() };
  }
  if (operation === 'grayscale_pages') {
    const pageSizes = options?.pageSizes;
    if (!Array.isArray(pageSizes) || pageSizes.length !== files.length || !files.length || files.length > 100) {
      throw new Error('The browser received an invalid grayscale page set. Choose Server Processing to continue.');
    }
    const totalBytes = files.reduce((sum, bytes) => sum + bytes.byteLength, 0);
    if (totalBytes > 64 * 1024 * 1024) throw new Error('The grayscale result is too large for browser memory. Choose Server Processing.');
    const result = await PDFDocument.create();
    for (let index = 0; index < files.length; index++) {
      const [width, height] = pageSizes[index].map(Number);
      if (![width, height].every(Number.isFinite) || width < 1 || height < 1 || width > 14400 || height > 14400) {
        throw new Error('A grayscale page has invalid dimensions. Choose Server Processing to continue.');
      }
      const image = await result.embedPng(files[index]);
      const page = result.addPage([width, height]);
      page.drawImage(image, { x: 0, y: 0, width, height });
    }
    return { filename: 'grayscale.pdf', output: await result.save() };
  }
  if (operation === 'zip_jpg') {
    if (!files.length || files.length > 200) throw new Error('Convert 1–200 pages in your browser, or choose Server Processing.');
    if (files.reduce((total, bytes) => total + bytes.byteLength, 0) > 256 * 1024 * 1024) {
      throw new Error('The rendered JPGs exceed the browser ZIP limit. Choose Server Processing.');
    }
    const pageNumbers = options?.pageNumbers;
    if (!Array.isArray(pageNumbers) || pageNumbers.length !== files.length || pageNumbers.some(number => !Number.isInteger(number) || number < 1)) {
      throw new Error('The browser received an invalid page selection. Choose the pages again.');
    }
    return { filename: 'pdf-pages-jpg.zip', output: zipPages(files.map(bytes => new Uint8Array(bytes)), 'jpg', pageNumbers) };
  }
  if (operation === 'merge') {
    const result = await PDFDocument.create();
    let copiedMetadata = false;
    for (const bytes of files) {
      const source = await PDFDocument.load(bytes);
      if (!copiedMetadata) {
        copyDocMetadata(source, result);
        copiedMetadata = true;
      }
      const pages = await result.copyPages(source, source.getPageIndices());
      pages.forEach(page => result.addPage(page));
    }
    return { filename: 'merged-PDF.pdf', output: await result.save({ updateMetadata: false }) };
  }

  const pdf = await PDFDocument.load(
    files[0],
    operation === 'metadata' ? { updateMetadata: false } : undefined
  );
  const count = pdf.getPageCount();
  if (operation === 'sign') {
    if (!count) throw new Error('This PDF has no page to sign.');
    const page = pdf.getPage(0);
    const box = page.getCropBox();
    if (box.width < 100 || box.height < 100) {
      throw new Error('This page is too small for a visual signature. Choose Server Processing.');
    }
    const signer = String(options.signerName || 'Signed').trim() || 'Signed';
    const hex = /^#([0-9a-f]{6})$/i.exec(String(options.signatureColor || ''))?.[1] || '243b53';
    const pen = rgb(parseInt(hex.slice(0, 2), 16) / 255,
      parseInt(hex.slice(2, 4), 16) / 255, parseInt(hex.slice(4, 6), 16) / 255);
    const edge = options.markBackground === 'dark' ? rgb(1, 1, 1) : rgb(0, 0, 0);
    const font = await pdf.embedFont(StandardFonts.Helvetica);
    const width = Math.min(200, box.width - 32);
    const height = Math.min(80, box.height - 48);
    const x = box.x + Math.max(16, box.width - width - 40);
    const y = box.y + 30;
    const caption = `${signer} | ${new Date().toISOString().slice(0, 16).replace('T', ' ')} UTC`;
    try { font.encodeText(signer); font.encodeText(caption); }
    catch { throw new Error('This browser signature supports standard-font names. Choose Server Processing for this script.'); }
    page.drawRectangle({ x, y, width, height, borderColor: rgb(0.7, 0.7, 0.7), borderWidth: 0.5 });
    if (files[1]) {
      const mark = await pdf.embedPng(files[1]);
      const scale = Math.min((width - 12) / mark.width, (height - 14) / mark.height);
      const drawWidth = mark.width * scale;
      const drawHeight = mark.height * scale;
      page.drawImage(mark, { x: x + (width - drawWidth) / 2, y: y + (height - drawHeight) / 2,
        width: drawWidth, height: drawHeight });
    } else {
      let fontSize = Math.min(24, Math.max(14, height * 0.4));
      while (fontSize > 8 && font.widthOfTextAtSize(signer, fontSize) > width - 16) fontSize -= 1;
      if (font.widthOfTextAtSize(signer, fontSize) > width - 16) {
        throw new Error('The printed name is too long for this page. Shorten it or choose Server Processing.');
      }
      page.drawText(signer, { x: x + 8, y: y + height * 0.4, size: fontSize, font, color: pen });
      page.drawLine({ start: { x: x + 6, y: y + 6 }, end: { x: x + width - 6, y: y + 6 },
        thickness: 1, color: options.markBackground === 'dark' ? pen : edge });
    }
    let captionSize = 7.5;
    while (captionSize > 5 && font.widthOfTextAtSize(caption, captionSize) > box.width - 20) captionSize -= 0.5;
    if (font.widthOfTextAtSize(caption, captionSize) <= box.width - 20) {
      page.drawText(caption, { x: Math.max(box.x + 10, x), y: y - 11,
        size: captionSize, font, color: rgb(0.4, 0.4, 0.4) });
    }
    return { filename: 'signed-document.pdf', output: await pdf.save() };
  }
  if (operation === 'edit') {
    const text = String(options.text || '').trim();
    const pageNumber = Number(options.page);
    const x = Number(options.x);
    const y = Number(options.y);
    if (!text) throw new Error('Enter text to add.');
    if (!Number.isInteger(pageNumber) || pageNumber < 1 || pageNumber > count) {
      throw new Error('The selected page does not exist.');
    }
    if (![x, y].every(Number.isFinite) || x < 0 || y < 0) {
      throw new Error('Enter valid non-negative text coordinates.');
    }
    const page = pdf.getPage(pageNumber - 1);
    const box = page.getCropBox();
    if (x > box.width || y > box.height) {
      throw new Error('Text coordinates must be inside the selected page.');
    }
    const font = await pdf.embedFont(StandardFonts.Helvetica);
    try { font.encodeText(text); }
    catch { throw new Error('This browser text stamp supports standard-font text. Choose Server Processing for this script.'); }
    page.drawText(text, {
      x: box.x + x, y: box.y + box.height - y,
      size: 14, font, color: rgb(0.1, 0.12, 0.12),
    });
    return { filename: 'text-stamped.pdf', output: await pdf.save() };
  }
  if (operation === 'metadata') {
    const infoDict = pdf.getInfoDict();
    const extractXmpProvenance = () => {
      try {
        const metaRef = pdf.catalog.lookup(PDFName.of('Metadata'));
        if (!metaRef || typeof metaRef.getContents !== 'function') return {};
        const rawBytes = PDFLib.decodePDFRawStream ? PDFLib.decodePDFRawStream(metaRef).decode() : metaRef.getContents();
        const xml = new TextDecoder('utf-8', { fatal: false }).decode(rawBytes);
        const tagVal = re => {
          const m = re.exec(xml);
          return m ? String(m[1] || '').replace(/<[^>]+>/g, '').trim() : '';
        };
        return {
          creator: tagVal(/<xmp:CreatorTool[^>]*>([\s\S]*?)<\/xmp:CreatorTool>/i) || tagVal(/xmp:CreatorTool="([^"]+)"/i),
          producer: tagVal(/<pdf:Producer[^>]*>([\s\S]*?)<\/pdf:Producer>/i) || tagVal(/pdf:Producer="([^"]+)"/i),
          creation_date: tagVal(/<xmp:CreateDate[^>]*>([\s\S]*?)<\/xmp:CreateDate>/i) || tagVal(/xmp:CreateDate="([^"]+)"/i),
          modification_date: tagVal(/<xmp:ModifyDate[^>]*>([\s\S]*?)<\/xmp:ModifyDate>/i) || tagVal(/xmp:ModifyDate="([^"]+)"/i),
        };
      } catch {
        return {};
      }
    };
    const xmpFallback = extractXmpProvenance();
    const prevCreator = pdf.getCreator() || xmpFallback.creator || '';
    const prevProducer = pdf.getProducer() || xmpFallback.producer || '';
    const prevCreationDate = pdf.getCreationDate() || (xmpFallback.creation_date ? new Date(xmpFallback.creation_date) : null);
    const prevModDate = pdf.getModificationDate() || (xmpFallback.modification_date ? new Date(xmpFallback.modification_date) : null);

    const keyMap = { title: ['setTitle', 'Title'], author: ['setAuthor', 'Author'], subject: ['setSubject', 'Subject'] };
    for (const [key, [setter, pdfKey]] of Object.entries(keyMap)) {
      if (!Object.prototype.hasOwnProperty.call(options, key)) continue;
      const val = String(options[key] ?? '').trim();
      if (val) {
        pdf[setter](val);
      } else {
        try { infoDict.delete(PDFName.of(pdfKey)); } catch { pdf[setter](''); }
      }
    }
    if (prevCreator) pdf.setCreator(prevCreator);
    if (prevProducer) pdf.setProducer(prevProducer);
    if (prevCreationDate instanceof Date && Number.isFinite(prevCreationDate.getTime())) {
      pdf.setCreationDate(prevCreationDate);
    }
    if (prevModDate instanceof Date && Number.isFinite(prevModDate.getTime())) {
      pdf.setModificationDate(prevModDate);
    }
    const dateString = date => date instanceof Date && Number.isFinite(date.getTime()) ? date.toISOString() : '';
    const output_metadata = {
      title: pdf.getTitle() || '', author: pdf.getAuthor() || '', subject: pdf.getSubject() || '',
      keywords: pdf.getKeywords() || '',
      creator: pdf.getCreator() || prevCreator || '',
      producer: pdf.getProducer() || prevProducer || '',
      creation_date: dateString(pdf.getCreationDate()) || dateString(prevCreationDate),
      modification_date: dateString(pdf.getModificationDate()) || dateString(prevModDate),
      page_count: count,
    };
    return { filename: 'metadata-updated.pdf', output: await pdf.save({ updateMetadata: false }), output_metadata };
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
    // PDFLib's form.flatten() only burns AcroForm widgets. It leaves regular
    // page annotations (for example Highlight/Underline/StrikeOut) in /Annots,
    // which made browser-local Flatten report success without flattening them.
    // The server path can bake their appearance streams, so fail closed here
    // and let the app offer its explicit temporary-upload confirmation.
    const annotationSubtype = PDFName.of('Subtype');
    const widgetSubtype = PDFName.of('Widget');
    for (const page of pdf.getPages()) {
      const annotations = page.node.Annots();
      if (!annotations) continue;
      for (let index = 0; index < annotations.size(); index++) {
        const reference = annotations.get(index);
        const annotation = pdf.context.lookup(reference);
        if (!annotation || annotation.get(annotationSubtype)?.toString() !== widgetSubtype.toString()) {
          throw new Error('Browser processing cannot flatten visual PDF annotations. Choose Server Processing to bake their appearance into the page.');
        }
      }
    }
    const form = pdf.getForm();
    form.flatten();
    return { filename: 'flattened.pdf', output: await pdf.save() };
  }
  if (operation === 'rotate') {
    pdf.getPages().forEach(page => page.setRotation(degrees(page.getRotation().angle + options.degrees)));
    return { filename: 'rotated.pdf', output: await pdf.save() };
  }
  if (operation === 'watermark') {
    if (options.watermarkImageSelected) {
      const imageBytes = files[1];
      if (!imageBytes?.byteLength) throw new Error('Choose a PNG or JPEG watermark image.');
      if (imageBytes.byteLength > 25 * 1024 * 1024) {
        throw new Error('This watermark image exceeds the 25 MiB browser limit. Choose Server Processing to continue.');
      }
      const imageType = String(options.watermarkImageType || '').toLowerCase();
      let image;
      try {
        if (imageType === 'image/png') image = await pdf.embedPng(imageBytes);
        else if (imageType === 'image/jpeg' || imageType === 'image/jpg') image = await pdf.embedJpg(imageBytes);
        else throw new Error('Unsupported image type');
      } catch {
        throw new Error('This image could not be decoded as PNG or JPEG. Choose another image or use Server Processing.');
      }
      const opacity = Number(options.opacity);
      if (!Number.isFinite(opacity) || opacity < 0.05 || opacity > 0.8) {
        throw new Error('Watermark opacity must be between 0.05 and 0.8.');
      }
      for (const page of pdf.getPages()) {
        const box = page.getCropBox();
        const maxWidth = box.width * 0.45;
        const maxHeight = box.height * 0.45;
        const scale = Math.min(maxWidth / image.width, maxHeight / image.height);
        const width = image.width * scale;
        const height = image.height * scale;
        page.drawImage(image, {
          x: box.x + (box.width - width) / 2,
          y: box.y + (box.height - height) / 2,
          width,
          height,
          opacity,
        });
      }
      return { filename: 'watermarked.pdf', output: await pdf.save() };
    }
    const label = String(options.text || '').trim();
    if (!label) throw new Error('Please provide watermark text.');
    const opacity = Number(options.opacity);
    if (!Number.isFinite(opacity) || opacity < 0.05 || opacity > 0.8) {
      throw new Error('Watermark opacity must be between 0.05 and 0.8.');
    }
    const colorMatch = /^#?([0-9a-f]{6})$/i.exec(String(options.markColor || '#243b53'));
    const colorHex = colorMatch?.[1] || '243b53';
    const color = rgb(parseInt(colorHex.slice(0, 2), 16) / 255,
      parseInt(colorHex.slice(2, 4), 16) / 255, parseInt(colorHex.slice(4, 6), 16) / 255);
    const outline = options.markBackground === 'dark' ? rgb(1, 1, 1) : rgb(0, 0, 0);
    const font = await pdf.embedFont(StandardFonts.HelveticaBold);
    const { pushGraphicsState, popGraphicsState, setFillingColor, setStrokingColor,
      setLineWidth, setGraphicsState, beginText, endText, setFontAndSize, setTextMatrix,
      showText, setTextRenderingMode, TextRenderingMode } = self.PDFLib;
    const opacityState = pdf.context.obj({ Type: 'ExtGState', ca: opacity, CA: opacity });
    const opacityRef = pdf.context.register(opacityState);
    for (const page of pdf.getPages()) {
      const box = page.getCropBox();
      const rotation = ((page.getRotation().angle % 360) + 360) % 360;
      const displayedWidth = rotation === 90 || rotation === 270 ? box.height : box.width;
      const fontSize = Math.min(44, Math.max(20, displayedWidth / 12));
      let encoded;
      try { encoded = font.encodeText(label); }
      catch { throw new Error('This browser watermark supports standard-font text. Choose Server Processing for this script.'); }
      const textWidth = font.widthOfTextAtSize(label, fontSize);
      const angle = (35 + rotation) * Math.PI / 180;
      const cosine = Math.cos(angle);
      const sine = Math.sin(angle);
      const centerX = box.x + box.width / 2;
      const centerY = box.y + box.height / 2;
      const x = centerX - (textWidth / 2) * cosine;
      const y = centerY - (textWidth / 2) * sine;
      const fontKey = page.node.newFontDictionary(font.name, font.ref);
      const opacityKey = page.node.newExtGState(font.name, opacityRef).toString().replace(/^\//, '');
      page.pushOperators(pushGraphicsState(), setGraphicsState(opacityKey), setFillingColor(color),
        setStrokingColor(outline), setLineWidth(Math.max(0.8, fontSize / 18)), beginText(),
        setFontAndSize(fontKey, fontSize), setTextRenderingMode(TextRenderingMode.FillAndOutline),
        setTextMatrix(cosine, sine, -sine, cosine, x, y), showText(encoded), endText(), popGraphicsState());
    }
    return { filename: 'watermarked.pdf', output: await pdf.save() };
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
