import { Router } from 'express';
import {
    uploadReport,
    getReports,
    getReport,
    updateReportStatusHandler,
    deleteReportHandler,
    getReportDetailsHandler,
} from '../controllers/report.controller.js';
import { authenticate } from '../middleware/auth.js';
import { upload } from '../middleware/upload.js';

const router = Router();

router.post('/upload', authenticate, upload, uploadReport);
router.get('/', authenticate, getReports);
router.get('/:id', authenticate, getReport);
router.get('/:id/details', authenticate, getReportDetailsHandler);
router.patch('/:id/status', authenticate, updateReportStatusHandler);
router.delete('/:id', authenticate, deleteReportHandler);

export default router;