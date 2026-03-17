const express = require('express');
const cors = require('cors');
const multer = require('multer');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const app = express();

// Ensure this matches your Vite port exactly
app.use(cors({ origin: 'http://localhost:5173' }));

// --- CRITICAL FIX 1: Use path.resolve to find the folder regardless of where you run the script ---
const uploadDir = path.resolve(__dirname, 'uploads');
if (!fs.existsSync(uploadDir)) fs.mkdirSync(uploadDir);

// Serve the folder so http://localhost:5000/uploads/file.png works
app.use('/uploads', express.static(uploadDir));

const storage = multer.diskStorage({
    destination: (req, file, cb) => cb(null, uploadDir),
    filename: (req, file, cb) => cb(null, `room-${Date.now()}${path.extname(file.originalname)}`)
});

const upload = multer({ storage: storage });

app.post('/api/process-room', upload.single('roomImage'), (req, res) => {
    if (!req.file) return res.status(400).json({ error: 'No image uploaded' });

    const tileName = req.body.tileName;
    const imagePath = req.file.path;

    // Use 'python' or 'py' depending on your environment
    const pythonProcess = spawn('python', ['engine.py', imagePath, tileName]);

    let pythonOutput = '';
    let pythonError = '';

    pythonProcess.stdout.on('data', (data) => { pythonOutput += data.toString(); });
    pythonProcess.stderr.on('data', (data) => { pythonError += data.toString(); });

    pythonProcess.on('close', (code) => {
        if (code === 0) {
            // --- CRITICAL FIX 2: Clean hidden characters from Python output ---
            const lines = pythonOutput.trim().split(/\r?\n/);
            const rawFilename = path.basename(lines[lines.length - 1].trim());
            
            // This is the relative path Express needs
            const finalUrl = `http://localhost:5000/uploads/${rawFilename}`;

            console.log(`✅ Python finished. Checking for file: ${rawFilename}`);

            // --- CRITICAL FIX 3: Verify the file actually exists before telling the frontend it's ready ---
            const filePathOnDisk = path.join(uploadDir, rawFilename);
            
            // We wait 300ms to let the OS finish the 'write' operation
            setTimeout(() => {
                if (fs.existsSync(filePathOnDisk)) {
                    console.log("🚀 File found! Sending URL to frontend.");
                    res.json({ success: true, processedUrl: finalUrl });
                } else {
                    console.error("❌ ERROR: Python said it finished, but the file isn't in the uploads folder!");
                    res.status(500).json({ error: "Processed image not found on server." });
                }
            }, 300);

        } else {
            console.error(`❌ Python Error: ${pythonError}`);
            res.status(500).json({ error: "AI Engine failed to process image." });
        }
    });
});

app.listen(5000, () => console.log(`🚀 Server running on http://localhost:5000`));