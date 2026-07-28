import { Router } from 'express';
import {
    analyze,
    extractClaimsHandler,
    verifyClaimsHandler,
    detectGreenwashingHandler,
    calculateTrustScoreHandler,
} from '../controllers/analyzer.controller.js';
import { authenticate } from '../middleware/auth.js';

const router = Router();

router.post('/analyze/:reportId', authenticate, analyze);

router.post('/extract-claims', authenticate, extractClaimsHandler);

router.post('/verify-claims', authenticate, verifyClaimsHandler);

router.post('/greenwashing', authenticate, detectGreenwashingHandler);

router.post('/trust-score', authenticate, calculateTrustScoreHandler);

export default router;