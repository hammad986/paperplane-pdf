importScripts('/assets/pdf-lib.min.js');

const { PDFDocument, degrees } = self.PDFLib;

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
  if (operation === 'rotate') {
    pdf.getPages().forEach(page => page.setRotation(degrees(page.getRotation().angle + options.degrees)));
    return { filename: 'rotated.pdf', output: await pdf.save() };
  }
  if (operation === 'split' && options.splitMode === 'all_pages') {
    if (count > 1000) throw new Error('For a ZIP over 1,000 pages, choose Server Mode.');
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
      ? 'This PDF needs a password. Choose Server Mode and enter the password, or unlock the PDF first.'
      : (error.message || 'Browser PDF processing failed.');
    self.postMessage({ error: message });
  }
};
