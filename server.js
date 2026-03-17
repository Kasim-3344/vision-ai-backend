const express = require('express');
const cors = require('cors');
const multer = require('multer');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const app = express();

const PORT = process.env.PORT || 5000;
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const BASE_URL = process.env.RENDER_EXTERNAL_URL || `http://localhost:${PORT}`;

// CORS
app.use(cors({
  origin: FRONTEND_URL,
}));

// Upload folder
const uploadDir = path.resolve(__dirname, 'uploads');
if (!fs.existsSync(uploadDir)) fs.mkdirSync(uploadDir, { recursive: true });

// Static access to uploads
app.use('/uploads', express.static(uploadDir));

// Multer storage
const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, uploadDir),
  filename: (req, file, cb) => cb(null, `room-${Date.now()}${path.extname(file.originalname)}`)
});

const upload = multer({ storage });

// Root route for Render/browser check
app.get('/', (req, res) => {
  res.send('Vision AI backend is running');
});

app.post('/api/process-room', upload.single('roomImage'), (req, res) => {
  if (!req.file) {
    return res.status(400).json({ error: 'No image uploaded' });
  }

  const tileName = req.body.tileName;
  const imagePath = req.file.path;

  const pythonProcess = spawn('python', ['engine.py', imagePath, tileName], {
    cwd: __dirname
  });

  let pythonOutput = '';
  let pythonError = '';

  pythonProcess.stdout.on('data', (data) => {
    pythonOutput += data.toString();
  });

  pythonProcess.stderr.on('data', (data) => {
    pythonError += data.toString();
  });

  pythonProcess.on('close', (code) => {
    if (code === 0) {
      const lines = pythonOutput.trim().split(/\r?\n/);
      const rawFilename = path.basename(lines[lines.length - 1].trim());

      const filePathOnDisk = path.join(uploadDir, rawFilename);
      const finalUrl = `${BASE_URL}/uploads/${rawFilename}`;

      console.log(`✅ Python finished. Checking for file: ${rawFilename}`);

      setTimeout(() => {
        if (fs.existsSync(filePathOnDisk)) {
          console.log('🚀 File found! Sending URL to frontend.');
          return res.json({ success: true, processedUrl: finalUrl });
        } else {
          console.error("❌ ERROR: Python said it finished, but the file isn't in the uploads folder!");
          return res.status(500).json({ error: 'Processed image not found on server.' });
        }
      }, 300);
    } else {
      console.error(`❌ Python Error: ${pythonError}`);
      return res.status(500).json({
        error: 'AI Engine failed to process image.',
        details: pythonError
      });
    }
  });
});

app.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);
});
