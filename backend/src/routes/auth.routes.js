import { Router } from 'express';
import {
    register,
    login,
    profile,
    googleLogin,
    forgotPassword,
    resetPassword,
} from '../controllers/auth.controller.js';

import { authenticate } from '../middleware/auth.js';

const router = Router();

// Authentication
router.post('/register', register);
router.post('/login', login);
router.post('/google-login', googleLogin);
router.post('/forgot-password', forgotPassword);
router.post('/reset-password', resetPassword);

// User
router.get('/profile', authenticate, profile);

export default router;