const fs = require("fs");
const path = require("path");
const zlib = require("zlib");
const QRCode = require("c:/Users/466mo/OneDrive/Desktop/beng_ai_ver/Dukkan/dukaan-ai/mobile/node_modules/qrcode-terminal/vendor/QRCode");

const TARGET_URL = "https://8dfcb15cd68630.app.lhr.life/voice";

// Generate QR Matrix
const qr = new QRCode(0, 1); // 1 = Medium error correction
qr.addData(TARGET_URL);
qr.make();

const count = qr.getModuleCount();
const quietZone = 4;
const totalSize = count + quietZone * 2;

// 1. Generate SVG
const moduleSize = 12;
const svgDimension = totalSize * moduleSize;

let svgPaths = "";
for (let r = 0; r < count; r++) {
  for (let c = 0; c < count; c++) {
    if (qr.isDark(r, c)) {
      const x = (c + quietZone) * moduleSize;
      const y = (r + quietZone) * moduleSize;
      svgPaths += `<rect x="${x}" y="${y}" width="${moduleSize}" height="${moduleSize}" fill="#0f172a" />\n`;
    }
  }
}

const svgContent = `<?xml version="1.0" encoding="utf-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${svgDimension} ${svgDimension}" width="400" height="400">
  <rect width="${svgDimension}" height="${svgDimension}" fill="#ffffff" rx="24" />
  ${svgPaths}
</svg>`;

// 2. Generate PNG (528 x 528 px)
const scale = 16; // 33 * 16 = 528 px
const imgDim = totalSize * scale;

// Raw RGBA scanlines
const rowBytes = 1 + imgDim * 4;
const rawBuffer = Buffer.alloc(imgDim * rowBytes);

for (let y = 0; y < imgDim; y++) {
  const rowOffset = y * rowBytes;
  rawBuffer[rowOffset] = 0; // Filter type: None
  
  const qrY = Math.floor(y / scale) - quietZone;
  
  for (let x = 0; x < imgDim; x++) {
    const pxOffset = rowOffset + 1 + x * 4;
    const qrX = Math.floor(x / scale) - quietZone;
    
    let isBlack = false;
    if (qrY >= 0 && qrY < count && qrX >= 0 && qrX < count) {
      isBlack = qr.isDark(qrY, qrX);
    }
    
    if (isBlack) {
      // Dark slate #0f172a
      rawBuffer[pxOffset] = 15;
      rawBuffer[pxOffset + 1] = 23;
      rawBuffer[pxOffset + 2] = 42;
      rawBuffer[pxOffset + 3] = 255;
    } else {
      // Crisp white #ffffff
      rawBuffer[pxOffset] = 255;
      rawBuffer[pxOffset + 1] = 255;
      rawBuffer[pxOffset + 2] = 255;
      rawBuffer[pxOffset + 3] = 255;
    }
  }
}

function makePng(width, height, rawData) {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; // Bit depth
  ihdr[9] = 6; // Color type 6: RGBA
  ihdr[10] = 0; // Compression
  ihdr[11] = 0; // Filter
  ihdr[12] = 0; // Interlace

  function makeChunk(type, data) {
    const len = data.length;
    const buf = Buffer.alloc(8 + len + 4);
    buf.writeUInt32BE(len, 0);
    buf.write(type, 4, 4, "ascii");
    data.copy(buf, 8);
    const crc = crc32(buf.subarray(4, 8 + len));
    buf.writeUInt32BE(crc, 8 + len);
    return buf;
  }

  // Precomputed CRC32 table
  const crcTable = [];
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) {
      c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
    }
    crcTable[n] = c;
  }

  function crc32(buf) {
    let crc = 0xffffffff;
    for (let i = 0; i < buf.length; i++) {
      crc = crcTable[(crc ^ buf[i]) & 0xff] ^ (crc >>> 8);
    }
    return (crc ^ 0xffffffff) >>> 0;
  }

  const compressed = zlib.deflateSync(rawData, { level: 9 });
  const sig = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  const ihdrChunk = makeChunk("IHDR", ihdr);
  const idatChunk = makeChunk("IDAT", compressed);
  const iendChunk = makeChunk("IEND", Buffer.alloc(0));

  return Buffer.concat([sig, ihdrChunk, idatChunk, iendChunk]);
}

const pngBuffer = makePng(imgDim, imgDim, rawBuffer);

// Save to Artifacts directory & Web public
const artifactDir = "C:/Users/466mo/.gemini/antigravity/brain/e53cab50-e4c4-4270-83ad-0a2b324cede1";
const webPubDir = "c:/Users/466mo/OneDrive/Desktop/beng_ai_ver/Dukkan/dukaan-ai/web/public";

fs.writeFileSync(path.join(artifactDir, "dukaanai_qr.svg"), svgContent);
fs.writeFileSync(path.join(artifactDir, "dukaanai_qr.png"), pngBuffer);

fs.writeFileSync(path.join(webPubDir, "dukaanai_qr.svg"), svgContent);
fs.writeFileSync(path.join(webPubDir, "dukaanai_qr.png"), pngBuffer);

console.log(`Successfully generated QR code (${imgDim}x${imgDim}):`);
console.log(`Artifact PNG: ${path.join(artifactDir, "dukaanai_qr.png")}`);
console.log(`Web public PNG: ${path.join(webPubDir, "dukaanai_qr.png")}`);

