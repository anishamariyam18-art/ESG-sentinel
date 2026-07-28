import fs from 'fs';
import path from 'path';
import crypto from 'crypto';

const fileExists = async(filePath) => {
    try {
        await fs.promises.access(filePath, fs.constants.F_OK);
        return true;
    } catch {
        return false;
    }
};

const getFileSize = async(filePath) => {
    const exists = await fileExists(filePath);

    if (!exists) {
        const error = new Error('File does not exist');
        error.statusCode = 404;
        throw error;
    }

    const stats = await fs.promises.stat(filePath);
    return stats.size;
};

const deleteFile = async(filePath) => {
    const exists = await fileExists(filePath);

    if (!exists) {
        return false;
    }

    await fs.promises.unlink(filePath);
    return true;
};

const getFileExtension = (filename) => {
    return path.extname(filename).toLowerCase();
};

const generateSafeFilename = (originalname) => {
    const extension = getFileExtension(originalname);
    const timestamp = Date.now();
    const randomString = crypto.randomBytes(8).toString('hex');
    return `${timestamp}-${randomString}${extension}`;
};

const getFileMetadata = ({ originalname, filename, filePath, size }) => {
    return {
        originalFilename: originalname,
        storedFilename: filename,
        path: filePath,
        size,
        extension: getFileExtension(originalname),
    };
};

export {
    fileExists,
    getFileSize,
    deleteFile,
    getFileExtension,
    generateSafeFilename,
    getFileMetadata,
};