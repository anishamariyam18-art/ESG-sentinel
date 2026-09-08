import multer from 'multer';
import path from 'path';
import fs from 'fs';
import crypto from 'crypto';
import config from '../config/env.js';
import logger from '../config/logger.js';

const UPLOAD_DIR = path.resolve(config.upload.path);

const ensureUploadDirExists = () => {
    if (!fs.existsSync(UPLOAD_DIR)) {
        fs.mkdirSync(UPLOAD_DIR, { recursive: true });
        logger.info(`Created upload directory at ${UPLOAD_DIR}`);
    }
};

ensureUploadDirExists();

const generateUniqueFilename = (originalname) => {
    const extension = path.extname(originalname).toLowerCase();
    const timestamp = Date.now();
    const randomString = crypto.randomBytes(8).toString('hex');
    return `${timestamp}-${randomString}${extension}`;
};

const storage = multer.diskStorage({
    destination: (req, file, cb) => {
        ensureUploadDirExists();
        cb(null, UPLOAD_DIR);
    },
    filename: (req, file, cb) => {
        const uniqueFilename = generateUniqueFilename(file.originalname);
        const destinationPath = path.join(UPLOAD_DIR, uniqueFilename);

        if (fs.existsSync(destinationPath)) {
            return cb(new Error('A file with the generated name already exists'));
        }

        cb(null, uniqueFilename);
    },
});

const fileFilter = (req, file, cb) => {
    const extension = path.extname(file.originalname).toLowerCase();

    const isPdf =
        extension === '.pdf' &&
        (
            file.mimetype === 'application/pdf' ||
            file.mimetype === 'application/octet-stream'
        );

    if (!isPdf) {
        const error = new Error('Only PDF files are allowed');
        error.statusCode = 400;
        return cb(error, false);
    }

    cb(null, true);
};

const multerUpload = multer({
    storage,
    fileFilter,
    limits: {
        fileSize: config.upload.maxFileSize,
    },
});

const handleUploadErrors = (uploadFn) => {
    return (req, res, next) => {
        uploadFn(req, res, (err) => {
            if (err instanceof multer.MulterError) {
                let message = 'File upload failed';

                if (err.code === 'LIMIT_FILE_SIZE') {
                    message = `File size exceeds the maximum allowed limit of ${config.upload.maxFileSize} bytes`;
                }

                return res.status(400).json({
                    success: false,
                    message,
                });
            }

            if (err) {
                return res.status(err.statusCode || 400).json({
                    success: false,
                    message: err.message || 'File upload failed',
                });
            }

            next();
        });
    };
};

const upload = handleUploadErrors(multerUpload.single('file'));

export { upload };